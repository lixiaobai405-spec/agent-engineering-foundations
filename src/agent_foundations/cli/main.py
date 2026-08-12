import asyncio
import os
from pathlib import Path
from typing import Annotated

import typer
import uvicorn
from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import ValidationError
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
from agent_foundations.evals.replay import EvalInputError, run_offline_evaluate
from agent_foundations.evals.reporting import write_report_atomic
from agent_foundations.planning.controller import PlanController
from agent_foundations.planning.execution import ExecutionFactJournal
from agent_foundations.planning.tools import (
    PlanningToolExecutor,
    build_planning_registered_tools,
    build_planning_tools,
)
from agent_foundations.providers.openai_compatible import OpenAICompatibleProvider
from agent_foundations.runtime.agent import AgentConfig, PlanningMode
from agent_foundations.runtime.loop import AgentLoop
from agent_foundations.runtime.redaction import Redactor
from agent_foundations.runtime.sinks import (
    CompositeEventSink,
    JsonlEventSink,
    LiveEventSink,
)
from agent_foundations.runtime.tool_execution import DirectToolCallExecutor, ToolCallExecutor
from agent_foundations.runtime.trace import EventSink
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.registry import (
    ToolRegistry,
    build_readonly_filesystem_registered_tools,
)
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


def build_tool_registry(
    root: Path,
    *,
    controller: PlanController | None = None,
    journal: ExecutionFactJournal | None = None,
) -> ToolRegistry:
    policy = PathPolicy(root)
    registered = list(build_readonly_filesystem_registered_tools(policy))
    if controller is not None and journal is not None:
        registered.extend(build_planning_registered_tools(controller, journal))
    return ToolRegistry(registered)


def build_planning_tool_executor(
    controller: PlanController,
    journal: ExecutionFactJournal,
    downstream: ToolCallExecutor | None = None,
) -> PlanningToolExecutor:
    planning_tools_list = build_planning_tools(controller, journal)
    planning_tools = {tool.name: tool for tool in planning_tools_list}
    return PlanningToolExecutor(
        downstream or DirectToolCallExecutor(),
        controller,
        journal,
        planning_tools,
    )


def build_runtime(
    root: Path,
    trace_dir: Path,
    viewer_url: str | None,
    planning_mode: PlanningMode = PlanningMode.DISABLED,
) -> AgentLoop:
    api_key, _model = require_model_credentials()
    controller = PlanController()
    journal = ExecutionFactJournal()
    tool_executor: ToolCallExecutor
    plan_controller: PlanController | None
    if planning_mode == PlanningMode.REQUIRED:
        registry = build_tool_registry(root, controller=controller, journal=journal)
        tool_executor = build_planning_tool_executor(controller, journal)
        plan_controller = controller
        config = AgentConfig(planning_mode=planning_mode)
    else:
        registry = build_tool_registry(root)
        tool_executor = DirectToolCallExecutor()
        plan_controller = None
        config = AgentConfig()
    redactor = Redactor(root, secrets=(api_key,))
    sinks: list[EventSink] = [JsonlEventSink(trace_dir, redactor)]
    if viewer_url:
        sinks.append(LiveEventSink(viewer_url, redactor))
    return AgentLoop(
        provider=build_provider(),
        registry=registry,
        context_builder=ContextBuilder(ContextBudget()),
        event_sink=CompositeEventSink(sinks),
        config=config,
        tool_executor=tool_executor,
        plan_controller=plan_controller,
    )


def build_provider() -> OpenAICompatibleProvider:
    api_key, model = require_model_credentials()
    base_url = os.getenv("AGENT_BASE_URL", "https://api.openai.com/v1")
    client = AsyncOpenAI(
        api_key=api_key, base_url=base_url, timeout=60.0, max_retries=2,
    )
    return OpenAICompatibleProvider(client, model=model)


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
    planning_mode: Annotated[
        PlanningMode,
        typer.Option(
            "--planning-mode",
            help="Planning mode: disabled keeps Phase 1 behavior; required enables plan tools",
        ),
    ] = PlanningMode.DISABLED,
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
                planning_mode=planning_mode,
            ).run(resolved, query),
        )
    except Exception as exc:
        console.print(f"Agent failed: {exc}", style="red")
        raise typer.Exit(code=1) from exc
    render_result(console, result)


@app.command()
def evaluate(
    task_set: Annotated[
        Path,
        typer.Option(help="Offline eval task set JSON path"),
    ],
    responses: Annotated[
        Path,
        typer.Option(help="Offline response fixture JSON path"),
    ],
    output: Annotated[
        Path,
        typer.Option(help="Atomic JSON report output path"),
    ],
    runtime_revision: Annotated[
        str,
        typer.Option(help="Explicit runtime revision label recorded in the report"),
    ],
) -> None:
    """Run offline replay evals without model credentials or network access."""
    fixture_root = task_set.resolve().parent.parent
    try:
        report, exit_code = asyncio.run(
            run_offline_evaluate(
                task_set_path=task_set.resolve(),
                responses_path=responses.resolve(),
                fixture_root=fixture_root,
                runtime_revision=runtime_revision,
                registry_factory=build_tool_registry,
            )
        )
    except (EvalInputError, FileNotFoundError, ValueError, ValidationError) as exc:
        console.print(str(exc), style="red")
        raise typer.Exit(code=2) from exc

    write_report_atomic(report, output.resolve())
    if exit_code != 0:
        raise typer.Exit(code=exit_code)


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
