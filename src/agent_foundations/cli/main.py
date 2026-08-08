import asyncio
import os
from pathlib import Path
from typing import Annotated

import typer
import uvicorn
from dotenv import load_dotenv
from openai import AsyncOpenAI
from rich.console import Console

from agent_foundations.chat.api import ChatServices
from agent_foundations.chat.approvals import ApprovalCoordinator
from agent_foundations.chat.events import ChatEventBroker
from agent_foundations.chat.repository import ConversationRepository
from agent_foundations.chat.runner import ConversationRunner
from agent_foundations.chat.supervisor import RunSupervisor
from agent_foundations.chat.tool_execution import ApprovalAwareToolExecutor
from agent_foundations.cli.renderer import render_result
from agent_foundations.context.budget import ContextBudget
from agent_foundations.context.builder import ContextBuilder
from agent_foundations.providers.openai_compatible import OpenAICompatibleProvider
from agent_foundations.runtime.agent import AgentConfig
from agent_foundations.runtime.loop import AgentLoop
from agent_foundations.runtime.redaction import Redactor
from agent_foundations.runtime.sinks import (
    CompositeEventSink,
    JsonlEventSink,
    LiveEventSink,
)
from agent_foundations.runtime.tool_execution import ToolCallExecutor
from agent_foundations.runtime.trace import EventSink
from agent_foundations.tools.filesystem.list_directory import ListDirectoryTool
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.filesystem.read_file import ReadFileTool
from agent_foundations.tools.filesystem.search_text import SearchTextTool
from agent_foundations.tools.registry import ToolRegistry
from agent_foundations.viewer.app import create_app

app = typer.Typer(no_args_is_help=True, rich_markup_mode=None)
console = Console()


@app.callback()
def cli() -> None:
    """Run the read-only Agent CLI."""


def load_cli_env() -> None:
    """Load AGENT_* variables from the current working directory .env file."""
    env_path = Path.cwd() / ".env"
    if env_path.is_file():
        load_dotenv(dotenv_path=env_path, override=False)


def require_model_credentials() -> tuple[str, str]:
    missing = [
        name
        for name in ("AGENT_API_KEY", "AGENT_MODEL")
        if not (os.getenv(name) or "").strip()
    ]
    if missing:
        console.print(
            f"Missing environment variables: {', '.join(missing)}", style="red",
        )
        raise typer.Exit(code=2)
    return os.environ["AGENT_API_KEY"], os.environ["AGENT_MODEL"]


def build_tool_registry(root: Path) -> ToolRegistry:
    policy = PathPolicy(root)
    return ToolRegistry([
        ListDirectoryTool(policy),
        ReadFileTool(policy),
        SearchTextTool(policy),
    ])


def build_provider() -> OpenAICompatibleProvider:
    api_key, model = require_model_credentials()
    base_url = os.getenv("AGENT_BASE_URL", "https://api.openai.com/v1")
    client = AsyncOpenAI(
        api_key=api_key, base_url=base_url, timeout=60.0, max_retries=2,
    )
    return OpenAICompatibleProvider(client, model=model)


def build_runtime(
    root: Path,
    trace_dir: Path,
    viewer_url: str | None,
) -> AgentLoop:
    api_key, _model = require_model_credentials()
    registry = build_tool_registry(root)
    redactor = Redactor(root, secrets=(api_key,))
    sinks: list[EventSink] = [JsonlEventSink(trace_dir, redactor)]
    if viewer_url:
        sinks.append(LiveEventSink(viewer_url, redactor))
    return AgentLoop(
        provider=build_provider(),
        registry=registry,
        context_builder=ContextBuilder(ContextBudget()),
        event_sink=CompositeEventSink(sinks),
        config=AgentConfig(),
    )


def build_chat_services(trace_dir: Path, state_db: Path) -> ChatServices:
    api_key, _model = require_model_credentials()
    repository = ConversationRepository(state_db)
    broker = ChatEventBroker()
    supervisor = RunSupervisor()
    coordinator = ApprovalCoordinator(repository, broker)

    def runtime_factory(
        conversation: object,
        event_sink: EventSink,
        tool_executor: ToolCallExecutor,
    ) -> AgentLoop:
        from agent_foundations.chat.models import Conversation

        assert isinstance(conversation, Conversation)
        root = Path(conversation.project_root)
        return AgentLoop(
            provider=build_provider(),
            registry=build_tool_registry(root),
            context_builder=ContextBuilder(ContextBudget()),
            event_sink=event_sink,
            config=AgentConfig(),
            tool_executor=tool_executor,
        )

    runner = ConversationRunner(
        repository=repository,
        broker=broker,
        runtime_factory=runtime_factory,
        trace_dir=trace_dir,
        redactor_factory=lambda conversation: Redactor(
            Path(conversation.project_root),
            secrets=(api_key,),
        ),
        tool_executor_factory=lambda conversation, _session_id: (
            ApprovalAwareToolExecutor(conversation, coordinator)
        ),
    )
    return ChatServices(
        repository=repository,
        broker=broker,
        runner=runner,
        supervisor=supervisor,
        coordinator=coordinator,
    )


@app.command()
def analyze(
    root: Path,
    query: str,
    trace_dir: Annotated[
        Path,
        typer.Option(help="Local JSONL trace directory"),
    ] = Path("traces"),
    viewer_url: Annotated[
        str | None,
        typer.Option(help="Optional local viewer URL"),
    ] = None,
) -> None:
    """Analyze a local project without modifying it."""
    load_cli_env()
    require_model_credentials()
    try:
        resolved = root.resolve()
        result = asyncio.run(
            build_runtime(
                resolved,
                trace_dir.resolve(),
                viewer_url,
            ).run(resolved, query),
        )
    except Exception as exc:
        console.print(f"Agent failed: {exc}", style="red")
        raise typer.Exit(code=1) from exc
    render_result(console, result)


@app.command()
def viewer(
    trace_dir: Annotated[
        Path,
        typer.Option(help="Local JSONL trace directory"),
    ] = Path("traces"),
    port: Annotated[int, typer.Option(min=1024, max=65535)] = 8765,
) -> None:
    """Serve the local read-only Trace Viewer."""
    console.print(f"http://127.0.0.1:{port}")
    uvicorn.run(create_app(trace_dir.resolve()), host="127.0.0.1", port=port)


@app.command()
def chat(
    state_db: Annotated[
        Path,
        typer.Option(help="Local SQLite chat state database"),
    ] = Path(".agent-foundations/chat.sqlite3"),
    trace_dir: Annotated[
        Path,
        typer.Option(help="Local JSONL trace directory"),
    ] = Path("traces"),
    port: Annotated[int, typer.Option(min=1024, max=65535)] = 8765,
) -> None:
    """Serve the local Chat control plane and Trace Viewer."""
    load_cli_env()
    require_model_credentials()
    services = build_chat_services(trace_dir.resolve(), state_db.resolve())
    console.print(f"http://127.0.0.1:{port}")
    uvicorn.run(
        create_app(trace_dir.resolve(), chat_services=services),
        host="127.0.0.1",
        port=port,
    )


if __name__ == "__main__":
    app()
