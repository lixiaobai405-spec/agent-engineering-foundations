import asyncio
import socket
import threading
import time
from pathlib import Path

import uvicorn
from playwright.sync_api import expect, sync_playwright

from agent_foundations.runtime.trace import TraceEvent
from agent_foundations.viewer.app import create_app


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _restore_asyncio_for_pytest() -> None:
    """Reset the main-thread event loop after uvicorn/playwright on Windows."""
    policy = asyncio.WindowsProactorEventLoopPolicy()
    asyncio.set_event_loop_policy(policy)
    asyncio.set_event_loop(policy.new_event_loop())


def test_viewer_loads_history_and_shows_event_detail(tmp_path: Path) -> None:
    event = TraceEvent(
        session_id="browser-session",
        step_id=2,
        event_type="tool.call.completed",
        status="completed",
        summary="read_file completed",
        payload={"result": {"content": "auth.py line 1"}},
    )
    (tmp_path / "browser-session.jsonl").write_text(
        event.model_dump_json() + "\n",
        encoding="utf-8",
    )
    (tmp_path / "unavailable-session.jsonl").write_text(
        "not valid jsonl\n",
        encoding="utf-8",
    )
    for index in range(10):
        overflow_event = TraceEvent(
            session_id=f"overflow-session-{index}",
            step_id=0,
            event_type="user.message",
            status="completed",
            summary=f"Overflow navigation run {index}",
        )
        (tmp_path / f"{overflow_event.session_id}.jsonl").write_text(
            overflow_event.model_dump_json() + "\n",
            encoding="utf-8",
        )
    port = free_port()
    server = uvicorn.Server(
        uvicorn.Config(create_app(tmp_path), host="127.0.0.1", port=port, log_level="error"),
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page()
                page.goto(f"http://127.0.0.1:{port}/")
                standalone_runs = page.locator("#standalone-runs")
                expect(standalone_runs).to_be_attached(timeout=10_000)
                expect(standalone_runs).not_to_have_attribute("open", "")
                unavailable = page.locator(
                    "[data-session-id='unavailable-session']",
                )
                expect(unavailable).to_be_disabled()
                expect(unavailable).to_contain_text("Trace unavailable")

                standalone_runs.locator("summary").click()
                expect(standalone_runs).to_have_attribute("open", "")
                navigation = page.locator("#trace-navigation")
                dimensions = navigation.evaluate(
                    "element => ({"
                    "clientHeight: element.clientHeight, "
                    "scrollHeight: element.scrollHeight"
                    "})",
                )
                assert dimensions["scrollHeight"] > dimensions["clientHeight"]
                navigation.hover()
                page.mouse.wheel(0, 500)
                page.wait_for_function(
                    "document.getElementById('trace-navigation').scrollTop > 0",
                )

                standalone_runs.locator("summary").click()
                expect(standalone_runs).not_to_have_attribute("open", "")
                standalone_runs.locator("summary").click()
                expect(standalone_runs).to_have_attribute("open", "")

                page.goto(f"http://127.0.0.1:{port}/?session_id=browser-session")
                selected_turn = page.locator("[data-session-id='browser-session']")
                expect(selected_turn).to_be_attached(timeout=10_000)
                expect(page.locator("#standalone-runs")).to_have_attribute("open", "")
                expect(selected_turn).to_have_attribute("aria-current", "true")
                expect(selected_turn).to_contain_text("read_file completed")
                expect(selected_turn).to_contain_text("browser-")
                expect(page.locator("#timeline")).to_contain_text("tool.call.completed")
                page.get_by_role("button", name="Tool Result").click()
                expect(page.locator("#detail")).to_contain_text("auth.py line 1")
            finally:
                browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        _restore_asyncio_for_pytest()
