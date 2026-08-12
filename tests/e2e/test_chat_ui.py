from __future__ import annotations

import asyncio
import re
import socket
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
import uvicorn
from playwright.sync_api import Page, expect, sync_playwright

from agent_foundations.chat.approvals import ApprovalCoordinator
from agent_foundations.chat.events import ChatEventBroker
from agent_foundations.chat.models import ChatEventType
from agent_foundations.chat.repository import ConversationRepository
from agent_foundations.chat.runner import ConversationRunner
from agent_foundations.chat.supervisor import RunSupervisor
from agent_foundations.context.budget import ContextBudget
from agent_foundations.context.builder import ContextBuilder
from agent_foundations.domain.errors import FakeModelExhaustedError
from agent_foundations.domain.model import ModelRequest, ModelResponse
from agent_foundations.domain.tool import ToolCall
from agent_foundations.providers.fake import FakeModelProvider
from agent_foundations.runtime.agent import AgentConfig
from agent_foundations.runtime.loop import AgentLoop
from agent_foundations.runtime.redaction import Redactor
from agent_foundations.runtime.tool_execution import ToolCallExecutor
from agent_foundations.runtime.trace import EventSink
from agent_foundations.viewer.app import CHAT_BUILD_DIR, create_app
from tests.unit.tools.registry_helpers import readonly_tool_registry

SAMPLE_PROJECT = Path(__file__).resolve().parents[1] / "fixtures" / "sample_project"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _restore_asyncio_for_pytest() -> None:
    policy = asyncio.WindowsProactorEventLoopPolicy()
    asyncio.set_event_loop_policy(policy)
    asyncio.set_event_loop(policy.new_event_loop())


def _require_chat_api() -> Any:
    from agent_foundations.chat.api import ChatServices
    from agent_foundations.chat.tool_execution import ApprovalAwareToolExecutor

    return ChatServices, ApprovalAwareToolExecutor


class RecordingBroker(ChatEventBroker):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[Any] = []

    async def publish(self, event: Any) -> None:
        self.events.append(event)
        await super().publish(event)


class GatedFakeModelProvider(FakeModelProvider):
    def __init__(
        self,
        responses: list[ModelResponse],
        release: asyncio.Event,
    ) -> None:
        super().__init__(responses)
        self._release = release

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if len(self.requests) == 1:
            await self._release.wait()
        if not self._responses:
            raise FakeModelExhaustedError("fake model response script is exhausted")
        return self._responses.popleft()


class SecondRequestGatedFakeModelProvider(FakeModelProvider):
    def __init__(
        self,
        responses: list[ModelResponse],
        release: asyncio.Event,
    ) -> None:
        super().__init__(responses)
        self._release = release

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if len(self.requests) == 2:
            await self._release.wait()
        if not self._responses:
            raise FakeModelExhaustedError("fake model response script is exhausted")
        return self._responses.popleft()


def _run_async(coro: Any) -> Any:
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coro).result()


def _build_chat_app(
    tmp_path: Path,
    provider: FakeModelProvider,
) -> tuple[Any, ConversationRepository, RecordingBroker]:
    ChatServices, ApprovalAwareToolExecutor = _require_chat_api()
    database_path = tmp_path / "state" / "chat.sqlite3"
    repository = ConversationRepository(database_path)
    broker = RecordingBroker()
    supervisor = RunSupervisor()
    coordinator = ApprovalCoordinator(repository, broker)

    def runtime_factory(
        conversation: Any,
        event_sink: EventSink,
        tool_executor: ToolCallExecutor,
    ) -> AgentLoop:
        return AgentLoop(
            provider=provider,
            registry=readonly_tool_registry(Path(conversation.project_root)),
            context_builder=ContextBuilder(ContextBudget()),
            event_sink=event_sink,
            config=AgentConfig(max_steps=8),
            tool_executor=tool_executor,
        )

    runner = ConversationRunner(
        repository=repository,
        broker=broker,
        runtime_factory=runtime_factory,
        trace_dir=tmp_path / "traces",
        redactor_factory=lambda conversation: Redactor(Path(conversation.project_root)),
        tool_executor_factory=lambda conversation, _session_id: ApprovalAwareToolExecutor(
            conversation,
            coordinator,
        ),
    )
    services = ChatServices(
        repository=repository,
        broker=broker,
        runner=runner,
        supervisor=supervisor,
        coordinator=coordinator,
    )
    return create_app(tmp_path / "traces", chat_services=services), repository, broker


@pytest.fixture
def require_chat_build() -> None:
    if not (CHAT_BUILD_DIR / "index.html").is_file():
        pytest.skip("Chat UI build is missing; run npm run build:chat first")


def _start_server(app: Any) -> tuple[uvicorn.Server, threading.Thread, int]:
    port = free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"),
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started
    return server, thread, port


def _stop_server(server: uvicorn.Server, thread: threading.Thread) -> None:
    server.should_exit = True
    thread.join(timeout=15)
    _restore_asyncio_for_pytest()


def _create_conversation_ui(
    page: Page,
    *,
    title: str,
    project_root: Path,
    permission_mode: str,
) -> None:
    page.get_by_role("button", name="New conversation").click()
    page.get_by_label("Title").fill(title)
    page.get_by_label("Project root").fill(str(project_root))
    page.get_by_label("Permission mode").select_option(permission_mode)
    page.get_by_role("button", name="Create conversation").click()
    expect(page.get_by_role("heading", level=1, name=title)).to_be_visible()


def _send_message(page: Page, text: str) -> None:
    page.locator("#chat-message-input").fill(text)
    page.get_by_role("button", name="Send message").click()


def _assert_locator_in_viewport(page: Page, locator: Any) -> None:
    box = locator.bounding_box()
    assert box is not None
    viewport = page.viewport_size
    assert viewport is not None
    assert box["x"] >= 0
    assert box["y"] >= 0
    assert box["x"] + box["width"] <= viewport["width"]
    assert box["y"] + box["height"] <= viewport["height"]


def _tool_messages_serialized(provider: FakeModelProvider) -> str:
    return " ".join(
        message.content
        for request in provider.requests
        for message in request.messages
        if message.content
    )


@pytest.fixture
def browser_page(require_chat_build: None) -> Iterator[Page]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page()
            yield page
        finally:
            browser.close()


def test_chat_multi_turn_reload_trace_and_narrow_viewport(
    tmp_path: Path,
    browser_page: Page,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_credential = "FAKE_PROVIDER_" + "CREDENTIAL_9F31"
    monkeypatch.setenv("OPENAI_API_KEY", fake_credential)
    release = asyncio.Event()
    provider = SecondRequestGatedFakeModelProvider(
        [
            ModelResponse(
                tool_calls=(
                    ToolCall(id="turn1-tool", name="list_directory", arguments={"path": "."}),
                ),
            ),
            ModelResponse(
                content=(
                    "# Turn one answer\n\n"
                    "- structured item\n\n"
                    "| file | result |\n| - | - |\n| README.md | found |\n\n"
                    "Use `read_file`.\n\n"
                    "```python\nprint(\"hello\")\n```"
                ),
            ),
            ModelResponse(content="Turn two answer"),
        ],
        release,
    )
    app, _repository, _broker = _build_chat_app(tmp_path, provider)
    server, thread, port = _start_server(app)
    try:
        browser_page.add_init_script(
            "window.__copiedCode = ''; "
            "Object.defineProperty(navigator, 'clipboard', {value: {"
            "writeText: async (text) => { window.__copiedCode = text; }"
            "}});",
        )
        browser_page.goto(f"http://127.0.0.1:{port}/chat")
        _create_conversation_ui(
            browser_page,
            title="Sample study",
            project_root=SAMPLE_PROJECT,
            permission_mode="PROJECT_READ_ONLY",
        )
        _send_message(browser_page, "Summarize the sample project")
        activity_toggle = browser_page.get_by_role(
            "button",
            name=re.compile(r"1 tool activity", re.IGNORECASE),
        )
        expect(activity_toggle).to_be_visible(timeout=15_000)
        expect(activity_toggle).to_have_attribute("aria-expanded", "true")
        expect(browser_page.get_by_text("list_directory")).to_be_visible()
        activity_toggle.click()
        expect(activity_toggle).to_have_attribute("aria-expanded", "false")

        release.set()
        expect(browser_page.get_by_role("heading", name="Turn one answer")).to_be_visible(
            timeout=15_000,
        )
        expect(browser_page.locator(".message-markdown ul")).to_contain_text(
            "structured item",
        )
        expect(browser_page.get_by_role("table")).to_be_visible()
        expect(browser_page.get_by_text("read_file", exact=True)).to_be_visible()
        expect(browser_page.get_by_text("python", exact=True)).to_be_visible()
        browser_page.get_by_role("button", name="Copy code").click()
        assert browser_page.evaluate("window.__copiedCode") == 'print("hello")\n'
        expect(activity_toggle).to_have_attribute("aria-expanded", "false")
        expect(browser_page.get_by_text("Tool requested")).to_have_count(0)
        expect(browser_page.locator(".activity-card")).to_have_count(0)
        expect(browser_page.get_by_text("tool.call.completed", exact=True)).to_have_count(0)

        trace_link = browser_page.get_by_role(
            "link",
            name="Open trace for this turn",
        ).first
        expect(trace_link).to_be_visible(timeout=15_000)
        trace_href = trace_link.get_attribute("href")
        assert trace_href is not None
        browser_page.goto(f"http://127.0.0.1:{port}{trace_href}")
        trace_query = parse_qs(urlparse(trace_href).query)
        conversation_id = trace_query["conversation_id"][0]
        session_id = trace_query["session_id"][0]
        selected_turn = browser_page.locator(f"[data-session-id='{session_id}']")
        expect(selected_turn).to_be_attached(timeout=15_000)
        expect(selected_turn).to_have_attribute("aria-current", "true")
        expect(
            browser_page.locator(
                f"[data-conversation-id='{conversation_id}']",
            ),
        ).to_have_attribute("open", "")
        expect(browser_page.locator("#timeline")).to_contain_text("tool.call.completed")
        browser_page.goto(f"http://127.0.0.1:{port}/chat")
        browser_page.get_by_role("button", name=re.compile(r"Sample study")).click()

        _send_message(browser_page, "What did we discuss before?")
        expect(browser_page.get_by_text("Turn two answer")).to_be_visible(timeout=15_000)
        assert len(provider.requests) >= 2
        serialized_history = " ".join(
            message.content
            for message in provider.requests[1].messages
            if message.content
        )
        assert "Summarize the sample project" in serialized_history

        browser_page.reload()
        expect(browser_page.get_by_text("Summarize the sample project")).to_be_visible(
            timeout=15_000,
        )
        expect(browser_page.get_by_role("heading", name="Turn one answer")).to_be_visible(
            timeout=15_000,
        )
        expect(browser_page.get_by_text("Turn two answer")).to_be_visible(timeout=15_000)
        expect(
            browser_page.get_by_role("link", name="Open trace for this turn"),
        ).to_have_count(2)
        reloaded_activity_toggle = browser_page.get_by_role(
            "button",
            name=re.compile(r"1 tool activity", re.IGNORECASE),
        )
        expect(reloaded_activity_toggle).to_have_attribute("aria-expanded", "false")

        browser_page.set_viewport_size({"width": 390, "height": 844})
        browser_page.goto(f"http://127.0.0.1:{port}/chat")
        open_conversations = browser_page.get_by_role(
            "button",
            name="Open conversations",
        )
        expect(open_conversations).to_be_visible(timeout=15_000)
        expect(
            browser_page.get_by_role("button", name="New conversation"),
        ).not_to_be_visible()
        open_conversations.click()
        expect(
            browser_page.get_by_role("button", name="Close conversations"),
        ).to_be_visible()
        expect(
            browser_page.get_by_role("button", name="Close conversation drawer"),
        ).to_be_visible()
        new_conversation_button = browser_page.get_by_role(
            "button",
            name="New conversation",
        )
        expect(new_conversation_button).to_be_visible()
        expect(new_conversation_button).to_be_in_viewport()
        browser_page.get_by_role("button", name=re.compile(r"Sample study")).click()
        expect(open_conversations).to_be_visible()
        message_input = browser_page.locator("#chat-message-input")
        send_button = browser_page.get_by_role("button", name="Send message")
        expect(message_input).to_be_visible(timeout=15_000)
        expect(send_button).to_be_visible(timeout=15_000)
        overflow = browser_page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth",
        )
        assert overflow is True
        timeline_overflow = browser_page.locator(".chat-timeline").evaluate(
            "element => getComputedStyle(element).overflowY",
        )
        assert timeline_overflow == "visible"
        _assert_locator_in_viewport(browser_page, message_input)
        _assert_locator_in_viewport(browser_page, send_button)

        conversations_response = browser_page.request.get(
            f"http://127.0.0.1:{port}/api/chat/conversations",
        )
        assert fake_credential not in conversations_response.text()
        conversations = _run_async(_repository.list_conversations())
        conversation_id_for_scan = conversations[0].conversation_id
        for suffix in ("messages", "runs", "activities", "state"):
            response = browser_page.request.get(
                f"http://127.0.0.1:{port}/api/chat/conversations/"
                f"{conversation_id_for_scan}/{suffix}",
            )
            assert fake_credential not in response.text()
        assert fake_credential not in browser_page.locator("body").inner_text()
        assert fake_credential.encode() not in (tmp_path / "state" / "chat.sqlite3").read_bytes()
        for trace_file in (tmp_path / "traces").glob("*.jsonl"):
            assert fake_credential.encode() not in trace_file.read_bytes()
        for asset in CHAT_BUILD_DIR.rglob("*"):
            if asset.is_file():
                assert fake_credential.encode() not in asset.read_bytes()
    finally:
        _stop_server(server, thread)


def test_chat_reload_during_running_recovers_before_completion(
    tmp_path: Path,
    browser_page: Page,
) -> None:
    release = asyncio.Event()
    provider = GatedFakeModelProvider(
        [
            ModelResponse(content="Recovered running answer"),
        ],
        release,
    )
    app, _repository, _broker = _build_chat_app(tmp_path, provider)
    server, thread, port = _start_server(app)
    try:
        browser_page.goto(f"http://127.0.0.1:{port}/chat")
        _create_conversation_ui(
            browser_page,
            title="Running reload",
            project_root=SAMPLE_PROJECT,
            permission_mode="PROJECT_READ_ONLY",
        )
        _send_message(browser_page, "Hold while running")
        expect(browser_page.get_by_role("button", name="Send message")).to_be_disabled(
            timeout=15_000,
        )
        browser_page.reload()
        expect(browser_page.get_by_role("button", name="Send message")).to_be_disabled(
            timeout=15_000,
        )
        expect(browser_page.get_by_label("Permission mode")).to_be_disabled(timeout=15_000)
        release.set()
        expect(browser_page.get_by_text("Recovered running answer")).to_be_visible(
            timeout=15_000,
        )
        expect(browser_page.get_by_role("button", name="Send message")).to_be_enabled(
            timeout=15_000,
        )
    finally:
        _stop_server(server, thread)


def test_chat_ask_access_approve_once_repeat_and_deny(
    tmp_path: Path,
    browser_page: Page,
) -> None:
    project = tmp_path / "isolated-project"
    project.mkdir()
    external = tmp_path / "external-read.txt"
    external.write_text("external fixture\n", encoding="utf-8")
    provider = FakeModelProvider(
        [
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="approve-call-1",
                        name="read_file",
                        arguments={"path": str(external)},
                    ),
                ),
            ),
            ModelResponse(content="Approved once answer"),
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="approve-call-2",
                        name="read_file",
                        arguments={"path": str(external)},
                    ),
                ),
            ),
            ModelResponse(content="Denied on repeat answer"),
        ],
    )
    app, _repository, broker = _build_chat_app(tmp_path, provider)
    server, thread, port = _start_server(app)
    approval_ids: list[str] = []
    try:
        browser_page.goto(f"http://127.0.0.1:{port}/chat")
        _create_conversation_ui(
            browser_page,
            title="Ask access",
            project_root=project,
            permission_mode="ASK_FOR_ACCESS",
        )
        _send_message(browser_page, "Read the external fixture")
        first_card = browser_page.get_by_role("article", name="Approval request")
        expect(first_card).to_be_visible(timeout=15_000)
        first_activity_row = first_card.locator("xpath=ancestor::li[1]")
        expect(first_activity_row).to_contain_text("read_file")
        expect(first_card.locator("xpath=ancestor::section[1]")).to_have_class(
            re.compile(r"tool-activity-group"),
        )
        browser_page.get_by_role("button", name="Approve once", disabled=False).click()
        expect(browser_page.get_by_text("Approved once answer")).to_be_visible(
            timeout=15_000,
        )
        expect(browser_page.get_by_role("button", name="Send message")).to_be_enabled(
            timeout=30_000,
        )

        for event in broker.events:
            if event.type is ChatEventType.APPROVAL_REQUESTED:
                approval_ids.append(str(event.data["approval_id"]))

        _send_message(browser_page, "Read the external fixture again")
        expect(browser_page.get_by_role("button", name="Send message")).to_be_disabled(
            timeout=15_000,
        )
        expect(browser_page.get_by_role("article", name="Approval request")).to_have_count(
            1,
            timeout=15_000,
        )
        repeat_card = browser_page.get_by_role("article", name="Approval request")
        repeat_card.get_by_role("button", name="Deny", disabled=False).click()
        expect(browser_page.get_by_text("Denied on repeat answer")).to_be_visible(
            timeout=15_000,
        )
        assert "access_denied" in _tool_messages_serialized(provider)
        expect(browser_page.get_by_role("button", name="Send message")).to_be_enabled(
            timeout=30_000,
        )

        for event in broker.events:
            if event.type is ChatEventType.APPROVAL_REQUESTED:
                approval_id = str(event.data["approval_id"])
                if approval_id not in approval_ids:
                    approval_ids.append(approval_id)

        assert len(set(approval_ids)) >= 2
    finally:
        _stop_server(server, thread)


def test_chat_ask_access_deny_allows_completion(
    tmp_path: Path,
    browser_page: Page,
) -> None:
    project = tmp_path / "deny-project"
    project.mkdir()
    external = tmp_path / "deny-external.txt"
    external.write_text("deny fixture\n", encoding="utf-8")
    provider = FakeModelProvider(
        [
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="deny-call",
                        name="read_file",
                        arguments={"path": str(external)},
                    ),
                ),
            ),
            ModelResponse(content="Denied but finished"),
        ],
    )
    app, _repository, _broker = _build_chat_app(tmp_path, provider)
    server, thread, port = _start_server(app)
    try:
        browser_page.goto(f"http://127.0.0.1:{port}/chat")
        _create_conversation_ui(
            browser_page,
            title="Deny access",
            project_root=project,
            permission_mode="ASK_FOR_ACCESS",
        )
        _send_message(browser_page, "Read the external fixture for deny")
        deny_card = browser_page.get_by_role("article", name="Approval request").last
        expect(deny_card).to_be_visible(timeout=15_000)
        deny_card.get_by_role("button", name="Deny", disabled=False).click()
        expect(browser_page.get_by_text("Denied but finished")).to_be_visible(
            timeout=15_000,
        )
        assert "access_denied" in _tool_messages_serialized(provider)
    finally:
        _stop_server(server, thread)


def test_chat_reload_waiting_approval_reconstructs_card(
    tmp_path: Path,
    browser_page: Page,
) -> None:
    project = tmp_path / "reload-project"
    project.mkdir()
    external = tmp_path / "reload-external.txt"
    external.write_text("reload external\n", encoding="utf-8")
    provider = FakeModelProvider(
        [
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="reload-call",
                        name="read_file",
                        arguments={"path": str(external)},
                    ),
                ),
            ),
            ModelResponse(content="Reload approved answer"),
        ],
    )
    app, repository, _broker = _build_chat_app(tmp_path, provider)
    server, thread, port = _start_server(app)
    try:
        browser_page.goto(f"http://127.0.0.1:{port}/chat")
        _create_conversation_ui(
            browser_page,
            title="Reload approval",
            project_root=project,
            permission_mode="ASK_FOR_ACCESS",
        )
        _send_message(browser_page, "Need reload approval")
        card = browser_page.get_by_role("article", name="Approval request")
        expect(card).to_be_visible(timeout=15_000)
        conversation_id = _run_async(repository.list_conversations())[0].conversation_id
        _latest_run, pending = _run_async(repository.get_conversation_state(conversation_id))
        assert pending is not None
        approval_id = pending.approval_id
        canonical_external = pending.canonical_path
        expect(card.get_by_text("read_file")).to_be_visible()
        expect(card.get_by_text(canonical_external)).to_be_visible()
        expect(
            card.locator(".approval-card__meta").get_by_text("read", exact=True),
        ).to_be_visible()
        expect(
            card.locator(".approval-card__meta").get_by_text("external exact path"),
        ).to_be_visible()
        expect(browser_page.get_by_role("button", name="Send message")).to_be_disabled()
        expect(browser_page.get_by_label("Permission mode")).to_be_disabled()

        browser_page.reload()
        browser_page.wait_for_load_state("networkidle")
        expect(
            browser_page.get_by_role("button", name=re.compile(r"Reload approval")),
        ).to_be_visible(timeout=15_000)
        browser_page.get_by_role("button", name=re.compile(r"Reload approval")).click()
        reloaded_card = browser_page.get_by_role("article", name="Approval request")
        expect(reloaded_card).to_be_visible(timeout=15_000)
        expect(reloaded_card.get_by_text("read_file")).to_be_visible()
        expect(reloaded_card.get_by_text(canonical_external)).to_be_visible()
        expect(
            reloaded_card.locator(".approval-card__meta").get_by_text("read", exact=True),
        ).to_be_visible()
        expect(
            reloaded_card.locator(".approval-card__meta").get_by_text("external exact path"),
        ).to_be_visible()
        expect(browser_page.get_by_role("button", name="Send message")).to_be_disabled()
        expect(browser_page.get_by_label("Permission mode")).to_be_disabled()
        with browser_page.expect_request(
            lambda request: (
                request.method == "POST"
                and request.url.endswith(f"/api/chat/approvals/{approval_id}/decision")
            ),
        ) as decision_request:
            reloaded_card.get_by_role("button", name="Approve once", disabled=False).click()
        assert decision_request.value.post_data_json == {"decision": "approve"}
        expect(browser_page.get_by_text("Reload approved answer")).to_be_visible(
            timeout=15_000,
        )
        _latest_run_after, pending_after = _run_async(
            repository.get_conversation_state(conversation_id),
        )
        assert pending_after is None
        assert _latest_run_after is not None
        assert _latest_run_after.status.value in {"running", "completed"}
    finally:
        _stop_server(server, thread)


def test_chat_service_restart_invalidates_waiting_approval(
    tmp_path: Path,
    browser_page: Page,
) -> None:
    project = tmp_path / "restart-project"
    project.mkdir()
    external = tmp_path / "restart-external.txt"
    external.write_text("restart external\n", encoding="utf-8")
    provider = FakeModelProvider(
        [
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="restart-call",
                        name="read_file",
                        arguments={"path": str(external)},
                    ),
                ),
            ),
            ModelResponse(content="Should not finish before restart"),
        ],
    )
    app, repository, _broker = _build_chat_app(tmp_path, provider)
    server, thread, port = _start_server(app)
    conversation_id: str | None = None
    approval_id: str | None = None
    try:
        browser_page.goto(f"http://127.0.0.1:{port}/chat")
        _create_conversation_ui(
            browser_page,
            title="Restart semantics",
            project_root=project,
            permission_mode="ASK_FOR_ACCESS",
        )
        _send_message(browser_page, "Need restart approval")
        card = browser_page.get_by_role("article", name="Approval request")
        expect(card).to_be_visible(timeout=15_000)
        conversations = _run_async(repository.list_conversations())
        conversation_id = conversations[0].conversation_id
        latest_run, pending = _run_async(repository.get_conversation_state(conversation_id))
        assert latest_run is not None
        assert pending is not None
        approval_id = pending.approval_id
    finally:
        _stop_server(server, thread)

    app2, repository2, _broker2 = _build_chat_app(tmp_path, provider)
    server2, thread2, port2 = _start_server(app2)
    try:
        latest_run, pending = _run_async(repository2.get_conversation_state(conversation_id))
        assert latest_run is not None
        assert latest_run.status.value == "interrupted"
        assert pending is None
        interrupted_activities = _run_async(
            repository2.list_tool_activities(conversation_id),
        )
        assert len(interrupted_activities) == 1
        assert interrupted_activities[0].status.value == "interrupted"
        browser_page.goto(f"http://127.0.0.1:{port2}/chat")
        expect(
            browser_page.get_by_role("button", name=re.compile(r"Restart semantics")),
        ).to_be_visible(timeout=15_000)
        browser_page.get_by_role("button", name=re.compile(r"Restart semantics")).click()
        expect(browser_page.get_by_role("article", name="Approval request")).to_have_count(0)
        expect(browser_page.get_by_role("button", name="Send message")).to_be_enabled(
            timeout=15_000,
        )
        response = browser_page.request.post(
            f"http://127.0.0.1:{port2}/api/chat/approvals/{approval_id}/decision",
            data='{"decision":"approve"}',
            headers={"Content-Type": "application/json"},
        )
        assert response.status in {409, 404}
    finally:
        _stop_server(server2, thread2)
