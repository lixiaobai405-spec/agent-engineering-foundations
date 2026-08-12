from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import ConfigDict, model_validator

from agent_foundations.context.budget import ContextBudget
from agent_foundations.context.builder import ContextBuilder
from agent_foundations.domain._model import ValidatedCopyModel
from agent_foundations.domain.errors import FakeModelExhaustedError
from agent_foundations.domain.model import ModelResponse
from agent_foundations.evals.models import EvalTask, EvalTaskSet
from agent_foundations.evals.reporting import EvalReport
from agent_foundations.evals.runner import EvalObservation, OfflineEvalRunner
from agent_foundations.planning.controller import PlanController
from agent_foundations.planning.execution import ExecutionFactJournal
from agent_foundations.planning.tools import PlanningToolExecutor, build_planning_tools
from agent_foundations.providers.fake import FakeModelProvider
from agent_foundations.runtime.agent import AgentConfig, PlanningMode
from agent_foundations.runtime.loop import AgentLoop
from agent_foundations.runtime.tool_execution import DirectToolCallExecutor
from agent_foundations.runtime.trace import InMemoryEventSink
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.registry import ToolRegistry, build_replay_registered_tools

PHASE1_PROMPT_VERSION = "phase-1-v1"
READONLY_TOOL_SET: tuple[str, ...] = ("list_directory", "read_file", "search_text")
PLANNING_TOOL_SET: tuple[str, ...] = ("set_plan", "update_plan_step", "replan")
PHASE2A_TOOL_SET: tuple[str, ...] = READONLY_TOOL_SET + PLANNING_TOOL_SET


class EvalInputError(Exception):
    """Invalid offline eval inputs such as response scripts or fixture mismatch."""


class ResponseScript(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True)

    task_id: str
    responses: tuple[ModelResponse, ...]

    @model_validator(mode="after")
    def validate_non_empty_responses(self) -> ResponseScript:
        if not self.responses:
            raise ValueError("responses must not be empty")
        return self


class ResponseFixture(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1]
    fixture_id: str
    fixture_version: str
    scripts: tuple[ResponseScript, ...]


def tool_set_for_task_set(task_set: EvalTaskSet) -> tuple[str, ...]:
    if any("planning-required" in task.tags for task in task_set.tasks):
        return PHASE2A_TOOL_SET
    return READONLY_TOOL_SET


def build_replay_registry(
    project_root: Path,
    *,
    planning_required: bool,
    controller: PlanController,
    journal: ExecutionFactJournal,
) -> ToolRegistry:
    policy = PathPolicy(project_root)
    return ToolRegistry(
        build_replay_registered_tools(
            policy,
            planning_required=planning_required,
            controller=controller,
            journal=journal,
        ),
    )


def build_replay_tool_executor(
    planning_required: bool,
    controller: PlanController,
    journal: ExecutionFactJournal,
) -> DirectToolCallExecutor | PlanningToolExecutor:
    if not planning_required:
        return DirectToolCallExecutor()
    planning_tools_list = build_planning_tools(controller, journal)
    planning_tools = {tool.name: tool for tool in planning_tools_list}
    return PlanningToolExecutor(
        DirectToolCallExecutor(),
        controller,
        journal,
        planning_tools,
    )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_eval_environment(
    task_set_path: Path,
    responses_path: Path,
) -> tuple[tuple[str, str], ...]:
    return (
        ("python", sys.version.split()[0]),
        ("platform", sys.platform),
        ("task_set_sha256", sha256_file(task_set_path)),
        ("response_fixture_sha256", sha256_file(responses_path)),
    )


def load_response_fixture(path: Path) -> ResponseFixture:
    raw = json.loads(path.read_text(encoding="utf-8"))
    schema_version = raw.get("schema_version")
    if schema_version != 1:
        raise ValueError(f"unsupported schema_version: {schema_version!r}")

    fixture = ResponseFixture.model_validate(raw)
    seen_task_ids: set[str] = set()
    for script in fixture.scripts:
        if script.task_id in seen_task_ids:
            raise ValueError(f"duplicate task_id: {script.task_id}")
        seen_task_ids.add(script.task_id)
    return fixture


def validate_response_fixture(fixture: ResponseFixture, task_set: EvalTaskSet) -> None:
    task_ids = {task.task_id for task in task_set.tasks}
    script_ids = {script.task_id for script in fixture.scripts}
    missing = sorted(task_ids - script_ids)
    if missing:
        raise ValueError(f"missing response script for task_id: {missing[0]}")
    extra = sorted(script_ids - task_ids)
    if extra:
        raise ValueError(f"extra response script for task_id: {extra[0]}")


def _build_observation(
    result: object,
    sink: InMemoryEventSink,
    consumed_responses: tuple[ModelResponse, ...],
) -> EvalObservation:
    from agent_foundations.runtime.agent import AgentResult

    assert isinstance(result, AgentResult)
    tool_names = tuple(
        str(event.payload["name"])
        for event in sink.events
        if event.event_type == "tool.call.requested" and "name" in event.payload
    )
    error_code: str | None = None
    for event in sink.events:
        if event.event_type == "tool.call.failed":
            result_payload = event.payload.get("result")
            if isinstance(result_payload, Mapping):
                code = result_payload.get("error_code")
                if code:
                    error_code = str(code)
    input_tokens = sum(response.usage.input_tokens for response in consumed_responses)
    output_tokens = sum(response.usage.output_tokens for response in consumed_responses)
    return EvalObservation(
        answer=result.answer,
        steps=result.steps,
        tool_names=tool_names,
        error_code=error_code,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_ms=0.0,
    )


class ReplayEvalAgent:
    def __init__(
        self,
        scripts: Mapping[str, ResponseScript],
        registry_factory: Callable[[Path], ToolRegistry],
    ) -> None:
        self._scripts = dict(scripts)
        self._registry_factory = registry_factory

    async def run(self, task: EvalTask, project_root: Path) -> EvalObservation:
        script = self._scripts[task.task_id]
        responses = list(script.responses)
        provider = FakeModelProvider(responses)
        sink = InMemoryEventSink()
        planning_required = "planning-required" in task.tags
        controller = PlanController()
        journal = ExecutionFactJournal()
        registry = (
            build_replay_registry(
                project_root,
                planning_required=planning_required,
                controller=controller,
                journal=journal,
            )
            if planning_required
            else self._registry_factory(project_root)
        )
        tool_executor = build_replay_tool_executor(
            planning_required,
            controller,
            journal,
        )
        config = AgentConfig(
            max_steps=task.max_steps,
            planning_mode=(
                PlanningMode.REQUIRED if planning_required else PlanningMode.DISABLED
            ),
        )
        loop = AgentLoop(
            provider=provider,
            registry=registry,
            context_builder=ContextBuilder(ContextBudget()),
            event_sink=sink,
            config=config,
            tool_executor=tool_executor,
            plan_controller=controller if planning_required else None,
        )
        try:
            result = await loop.run(project_root, task.prompt)
        except FakeModelExhaustedError as exc:
            raise EvalInputError("response script exhausted") from exc

        if provider._responses:
            raise EvalInputError("response script has remaining responses")

        consumed_count = len(responses) - len(provider._responses)
        consumed = tuple(responses[:consumed_count])
        return _build_observation(result, sink, consumed)


async def run_offline_evaluate(
    *,
    task_set_path: Path,
    responses_path: Path,
    fixture_root: Path,
    runtime_revision: str,
    clock: Callable[[], datetime] | None = None,
    registry_factory: Callable[[Path], ToolRegistry],
) -> tuple[EvalReport, int]:
    from agent_foundations.evals.task_sets import load_task_set

    task_set = load_task_set(task_set_path, fixture_root=fixture_root)
    response_fixture = load_response_fixture(responses_path)
    validate_response_fixture(response_fixture, task_set)

    scripts = {script.task_id: script for script in response_fixture.scripts}
    agent = ReplayEvalAgent(scripts, registry_factory=registry_factory)
    runner = OfflineEvalRunner(
        fixture_root=fixture_root,
        prompt_version=PHASE1_PROMPT_VERSION,
        response_fixture_version=response_fixture.fixture_version,
        tool_set=tool_set_for_task_set(task_set),
        runtime_revision=runtime_revision,
        environment=build_eval_environment(task_set_path, responses_path),
        clock=clock or (lambda: datetime.now(UTC)),
    )
    report = await runner.run(task_set, agent)
    if report.summary.failed_tasks > 0:
        return report, 1
    return report, 0
