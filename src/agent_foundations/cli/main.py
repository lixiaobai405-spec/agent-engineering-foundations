import asyncio
import inspect
import os
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Annotated, Any

import typer
import uvicorn
from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import ValidationError
from rich.console import Console

from agent_foundations.chat.api import ChatServices
from agent_foundations.chat.approvals import ApprovalCoordinator
from agent_foundations.chat.data_root import (
    chat_data_layout,
    leftover_legacy_paths,
    leftover_warning,
    resolve_data_root,
)
from agent_foundations.chat.events import ChatEventBroker
from agent_foundations.chat.repository import ConversationRepository
from agent_foundations.chat.runner import ConversationRunner
from agent_foundations.chat.supervisor import RunSupervisor
from agent_foundations.chat.tool_execution import (
    ApprovalAwareToolExecutor,
    ChatControlledToolExecutor,
)
from agent_foundations.cli.renderer import render_result
from agent_foundations.command_output.store import ArtifactRootError
from agent_foundations.context.budget import ContextBudget
from agent_foundations.context.builder import ContextBuilder
from agent_foundations.domain.model import ModelProvider
from agent_foundations.durable.effects import SideEffectLedger
from agent_foundations.durable.repository import DurableRunRepository
from agent_foundations.evals.replay import EvalInputError, run_offline_evaluate
from agent_foundations.evals.reporting import write_report_atomic
from agent_foundations.execution.docker import DockerBackend
from agent_foundations.planning.controller import PlanController
from agent_foundations.planning.execution import ExecutionFactJournal
from agent_foundations.planning.tools import (
    PlanningToolExecutor,
    build_planning_registered_tools,
    build_planning_tools,
)
from agent_foundations.providers.openai_compatible import OpenAICompatibleProvider
from agent_foundations.providers.resilient import ResilientModelProvider, RetryPolicy
from agent_foundations.runtime.agent import AgentConfig, PlanningMode
from agent_foundations.runtime.coding_budget import CHAT_CODING_BUDGET, CHAT_MAX_STEPS
from agent_foundations.runtime.coding_prompt import CONTROLLED_CODING_AGENT_PROMPT
from agent_foundations.runtime.loop import AgentLoop
from agent_foundations.runtime.provider_attempt_budget import ProviderAttemptBudget
from agent_foundations.runtime.rate_limit import TokenBucketRateLimiter
from agent_foundations.runtime.redaction import Redactor
from agent_foundations.runtime.sinks import (
    CompositeEventSink,
    JsonlEventSink,
    LiveEventSink,
)
from agent_foundations.runtime.tool_execution import DirectToolCallExecutor, ToolCallExecutor
from agent_foundations.runtime.trace import EventSink
from agent_foundations.security.approvals import (
    AuthorizationApproval,
    AuthorizationDecision,
)
from agent_foundations.security.capabilities import CapabilityConsumer, CapabilityIssuer
from agent_foundations.security.models import (
    PermissionProfile,
    default_allowed_tools,
)
from agent_foundations.security.policy import PolicyEngine
from agent_foundations.security.repository import AuthorizationRepository
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.patch.apply_patch import (
    ControlledPatchExecutor,
    build_apply_patch_registered_tool,
)
from agent_foundations.tools.patch.execution import PatchProposalExecutor
from agent_foundations.tools.patch.repository import PatchProposalRepository
from agent_foundations.tools.registry import (
    ToolRegistry,
    build_standard_registered_tools,
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
    include_validate_patch: bool = False,
    include_apply_patch: bool = False,
    include_run_command: bool = False,
    include_command_output: bool = False,
    include_git_read: bool = False,
    git_backend_factory: Callable[[Path], Any] | None = None,
) -> ToolRegistry:
    policy = PathPolicy(root)
    registered = list(
        build_standard_registered_tools(
            policy,
            include_validate_patch=include_validate_patch,
        ),
    )
    if controller is not None and journal is not None:
        registered.extend(build_planning_registered_tools(controller, journal))
    if include_apply_patch:
        registered.append(build_apply_patch_registered_tool())
    if include_run_command:
        from agent_foundations.tools.command.run_command import (
            build_run_command_registered_tool,
        )

        registered.append(build_run_command_registered_tool())
    if include_command_output:
        from agent_foundations.tools.command.read_output import (
            build_read_command_output_registered_tool,
        )
        from agent_foundations.tools.command.search_output import (
            build_search_command_output_registered_tool,
        )

        registered.append(build_read_command_output_registered_tool())
        registered.append(build_search_command_output_registered_tool())
    if include_git_read:
        from agent_foundations.execution.docker import DockerBackend
        from agent_foundations.runtime.redaction import Redactor
        from agent_foundations.tools.git.service import GitReadService
        from agent_foundations.tools.registry import build_git_read_registered_tools

        factory = git_backend_factory or DockerBackend
        service = GitReadService(
            root,
            factory(root),
            policy,
            Redactor(root),
        )
        registered.extend(build_git_read_registered_tools(service, policy))
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


def build_provider() -> ModelProvider:
    api_key, model = require_model_credentials()
    base_url = os.getenv("AGENT_BASE_URL", "https://api.openai.com/v1")
    client = AsyncOpenAI(
        api_key=api_key, base_url=base_url, timeout=60.0, max_retries=0,
    )
    inner = OpenAICompatibleProvider(client, model=model)
    return ResilientModelProvider(
        inner,
        policy=RetryPolicy(),
        budget=ProviderAttemptBudget(),
        limiter=TokenBucketRateLimiter(),
    )


def _phase2d_sandbox_manifest() -> Any:
    from agent_foundations.execution.sandbox_manifest import SandboxManifest

    repo_root = Path(__file__).resolve().parents[3]
    return SandboxManifest.load_pinned(repo_root)


def build_chat_services(data_root: Path) -> ChatServices:
    api_key, _model = require_model_credentials()
    layout = chat_data_layout(data_root)
    state_db = layout.data_root / "chat.sqlite3"
    trace_dir = layout.data_root / "traces"
    repository = ConversationRepository(state_db)
    durable_repository = DurableRunRepository(state_db)
    patch_repository = PatchProposalRepository.from_path(state_db)
    authorization_repository = AuthorizationRepository.from_path(state_db)
    from agent_foundations.command_output.access import (
        CommandOutputAccessExecutor,
        CommandOutputDownloadTicketStore,
    )
    from agent_foundations.command_output.repository import CommandArtifactRepository
    from agent_foundations.command_output.retention import ArtifactRetentionSweeper
    from agent_foundations.command_output.store import CommandArtifactStore
    from agent_foundations.tools.command.config import default_project_command_manifest
    from agent_foundations.tools.command.run_command import ControlledCommandExecutor
    from agent_foundations.tools.patch.models import compute_project_root_fingerprint

    artifact_repository = CommandArtifactRepository.from_path(state_db)
    artifact_store = CommandArtifactStore(
        layout.data_root / "command-output",
        repository=artifact_repository,
    )
    retention = ArtifactRetentionSweeper(artifact_store, artifact_repository)
    tickets = CommandOutputDownloadTicketStore()
    broker = ChatEventBroker()
    supervisor = RunSupervisor()
    coordinator = ApprovalCoordinator(
        repository,
        broker,
        authorization_repository=authorization_repository,
    )

    def runtime_factory(
        conversation: object,
        event_sink: EventSink,
        tool_executor: ToolCallExecutor,
    ) -> AgentLoop:
        from agent_foundations.chat.models import Conversation

        assert isinstance(conversation, Conversation)
        root = Path(conversation.project_root)
        allowed_tools = default_allowed_tools(conversation.permission_profile)
        allow_command = "run_command" in allowed_tools
        controller = PlanController()
        journal = ExecutionFactJournal()
        return AgentLoop(
            provider=build_provider(),
            registry=build_tool_registry(
                root,
                controller=controller,
                journal=journal,
                include_validate_patch=True,
                include_apply_patch="apply_patch" in allowed_tools,
                include_run_command=allow_command,
                include_command_output=allow_command,
                include_git_read=True,
            ),
            context_builder=ContextBuilder(ContextBudget()),
            event_sink=event_sink,
            config=AgentConfig(
                max_steps=CHAT_MAX_STEPS,
                planning_mode=PlanningMode.DISABLED,
                system_prompt=CONTROLLED_CODING_AGENT_PROMPT,
                coding_budget=CHAT_CODING_BUDGET,
            ),
            tool_executor=build_planning_tool_executor(
                controller,
                journal,
                downstream=tool_executor,
            ),
            plan_controller=controller,
        )

    def tool_executor_factory(
        conversation: object,
        _session_id: str,
    ) -> ToolCallExecutor:
        from agent_foundations.chat.models import Conversation

        assert isinstance(conversation, Conversation)
        base = ApprovalAwareToolExecutor(conversation, coordinator)
        proposal = PatchProposalExecutor(base, patch_repository)
        profile = PermissionProfile(
            name=conversation.permission_profile,
            version=conversation.profile_version,
            allowed_tools=default_allowed_tools(conversation.permission_profile),
        )
        root = Path(conversation.project_root)
        sandbox_manifest = _phase2d_sandbox_manifest()
        command_manifest = default_project_command_manifest(
            project_fingerprint=compute_project_root_fingerprint(root),
            sandbox=sandbox_manifest,
        )

        def docker_backend_factory(workspace: Any) -> Any:
            try:
                accepts_manifest = (
                    "sandbox_manifest" in inspect.signature(DockerBackend).parameters
                )
            except (TypeError, ValueError):
                accepts_manifest = False
            if accepts_manifest:
                return DockerBackend(
                    workspace,
                    sandbox_manifest=sandbox_manifest,
                )
            return DockerBackend(workspace)

        def controlled_factory(
            decider: Callable[
                [AuthorizationDecision],
                AuthorizationDecision,
            ]
            | None,
        ) -> ToolCallExecutor:
            return ControlledPatchExecutor(
                proposal,
                patch_repository,
                profile,
                PolicyEngine(),
                AuthorizationApproval(
                    authorization_repository,
                    profile.name,
                ),
                CapabilityIssuer(
                    authorization_repository,
                    profile.name,
                    ttl=timedelta(minutes=5),
                ),
                CapabilityConsumer(authorization_repository),
                SideEffectLedger(durable_repository),
                backend_factory=lambda workspace: docker_backend_factory(workspace),
                approval_decider=decider,
            )

        def controlled_command_factory(
            decider: Callable[
                [AuthorizationDecision],
                AuthorizationDecision,
            ]
            | None,
        ) -> ToolCallExecutor:
            return ControlledCommandExecutor(
                proposal,
                profile,
                PolicyEngine(),
                AuthorizationApproval(
                    authorization_repository,
                    profile.name,
                ),
                CapabilityIssuer(
                    authorization_repository,
                    profile.name,
                    ttl=timedelta(minutes=5),
                ),
                CapabilityConsumer(authorization_repository),
                SideEffectLedger(durable_repository),
                command_manifest=command_manifest,
                artifact_store=artifact_store,
                retention=retention,
                backend_factory=lambda workspace: docker_backend_factory(workspace),
                approval_decider=decider,
                controller_root=layout.data_root / "controller",
            )

        output_executor = CommandOutputAccessExecutor(
            artifact_store,
            artifact_repository,
            profile=profile,
            policy=PolicyEngine(),
            issuer=CapabilityIssuer(
                authorization_repository,
                profile.name,
                ttl=timedelta(minutes=5),
            ),
            consumer=CapabilityConsumer(authorization_repository),
            project_root=root,
            downstream=proposal,
        )
        return ChatControlledToolExecutor(
            proposal,
            conversation,
            coordinator,
            controlled_factory,
            controlled_command_factory=controlled_command_factory,
            output_executor=output_executor,
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
        tool_executor_factory=tool_executor_factory,
        durable_repository=durable_repository,
    )
    return ChatServices(
        repository=repository,
        broker=broker,
        runner=runner,
        supervisor=supervisor,
        coordinator=coordinator,
        patch_repository=patch_repository,
        command_artifact_store=artifact_store,
        command_artifact_repository=artifact_repository,
        command_output_tickets=tickets,
        durable_repository=durable_repository,
        retention=retention,
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
    data_root: Annotated[
        Path | None,
        typer.Option("--data-root", help="Local Chat data root"),
    ] = None,
    port: Annotated[int, typer.Option(min=1024, max=65535)] = 8765,
) -> None:
    """Serve the local Chat control plane and Trace Viewer."""
    load_cli_env()
    require_model_credentials()
    try:
        resolved = resolve_data_root(explicit=data_root)
    except ArtifactRootError as exc:
        console.print(str(exc), style="red")
        raise typer.Exit(code=2) from exc
    leftover = leftover_legacy_paths(Path.cwd())
    if leftover:
        console.print(leftover_warning(leftover, resolved), style="yellow")
    services = build_chat_services(resolved)
    traces = chat_data_layout(resolved).traces
    console.print(f"http://127.0.0.1:{port}")
    uvicorn.run(
        create_app(traces, chat_services=services),
        host="127.0.0.1",
        port=port,
    )


if __name__ == "__main__":
    app()
