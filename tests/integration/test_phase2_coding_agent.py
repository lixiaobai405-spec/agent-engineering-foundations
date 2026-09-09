from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest

from agent_foundations.chat.models import ChatEventType
from agent_foundations.domain.model import ModelResponse
from agent_foundations.domain.tool import ToolCall
from agent_foundations.durable.models import DurableRunStatus
from agent_foundations.durable.repository import DurableRunRepository
from agent_foundations.execution.fake import FakeBackend
from agent_foundations.execution.models import ByteStreamSink, ExecutionRequest, ExecutionResult
from agent_foundations.planning.controller import PlanController
from agent_foundations.planning.execution import ExecutionFactJournal
from agent_foundations.providers.fake import FakeModelProvider
from agent_foundations.security.models import PermissionProfileName, default_allowed_tools
from agent_foundations.tools.patch.applier import (
    apply_prepared_patch_atomically,
    prepare_patch,
)
from agent_foundations.tools.patch.models import BaselineEntry
from agent_foundations.tools.patch.validator import parse_and_validate_patch
from tests.unit.tools.patch_test_helpers import sha256_bytes

PHASE2_CODING_FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "phase2_coding_project"
)
PHASE2_TASK_SET = (
    Path(__file__).resolve().parents[1] / "fixtures" / "evals" / "phase-2-tasks-v1.json"
)
PHASE2_RESPONSES = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "evals"
    / "phase-2-responses-v1.json"
)
SECRET = "fixture-secret-raw-output-task20"
NODE_ID = "tests/test_fail.py::test_boom"
FIXED_TEST = "def test_boom() -> None:\n    assert True\n"
_GIT_WRITE_SUBCOMMANDS = frozenset(
    {
        "add",
        "commit",
        "push",
        "reset",
        "checkout",
        "clean",
        "restore",
        "rebase",
        "merge",
        "submodule",
    }
)
_NON_GOAL_TOOLS = frozenset(
    {
        "mcp",
        "memory",
        "skills",
        "hooks",
        "sub_agent",
        "browser",
        "run_shell",
        "git_commit",
        "git_push",
        "git_add",
        "network",
        "install_package",
        "HOST_FULL_ACCESS",
        "TrustedHostExecutor",
    }
)
_STEP2_COVERAGE = (
    ("approve/deny/cancel", "tests/unit/chat/test_approvals.py"),
    ("crash/lease takeover", "tests/unit/durable/test_lease.py"),
    ("profile version change", "tests/integration/test_chat_approval_flow.py"),
    ("command timeout", "tests/integration/test_execution_backend.py"),
    ("artifact write failure", "tests/integration/test_command_artifact_lifecycle.py"),
    ("parser partial", "tests/unit/command_output"),
    ("targeted reproduction", "tests/integration/test_command_feedback_agent_flow.py"),
    ("git read-only", "tests/integration/test_git_read_tools.py"),
    ("compaction/rehydration", "tests/unit/context/test_compaction.py"),
    ("provider attempt restart", "tests/integration/test_provider_retry_recovery.py"),
)
_FAIL_JUNIT = f"""<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="2" failures="1" errors="0" skipped="0">
    <!-- {SECRET} -->
    <testcase classname="tests.test_fail" name="test_boom" time="0.01">
      <failure message="assert False">AssertionError</failure>
    </testcase>
    <testcase classname="tests.test_ok" name="test_ok" time="0.01"/>
  </testsuite>
</testsuites>
"""
_PASS_JUNIT = f"""<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="2" failures="0" errors="0" skipped="0">
    <!-- {SECRET} -->
    <testcase classname="tests.test_fail" name="test_boom" time="0.01"/>
    <testcase classname="tests.test_ok" name="test_ok" time="0.01"/>
  </testsuite>
</testsuites>
"""
_DIFF = """diff --git a/tests/test_fail.py b/tests/test_fail.py
--- a/tests/test_fail.py
+++ b/tests/test_fail.py
@@ -1,2 +1,2 @@
 def test_boom() -> None:
-    assert False  # noqa: B011
+    assert True
"""

_monkeypatch: ContextVar[pytest.MonkeyPatch] = ContextVar("phase2_coding_monkeypatch")


@dataclass(frozen=True)
class Phase2CorrectionResult:
    status: DurableRunStatus
    targeted_reproduction_count: int
    affected_regression_passed: bool
    raw_output_exposed_to_model: bool
    git_writes: tuple[str, ...]


def test_phase2_coding_project_fixture_exists() -> None:
    assert PHASE2_CODING_FIXTURE.is_dir(), "phase2_coding_project fixture is missing"
    assert (PHASE2_CODING_FIXTURE / "tests" / "test_fail.py").is_file()
    assert (PHASE2_CODING_FIXTURE / "tests" / "test_ok.py").is_file()
    assert (PHASE2_CODING_FIXTURE / "pyproject.toml").is_file()


def test_phase2_eval_fixtures_exist() -> None:
    assert PHASE2_TASK_SET.is_file(), "phase-2-tasks-v1.json is missing"
    assert PHASE2_RESPONSES.is_file(), "phase-2-responses-v1.json is missing"


def test_step2_coverage_matrix_files_exist() -> None:
    for _label, relative in _STEP2_COVERAGE:
        path = Path(relative)
        assert path.exists(), f"missing Step 2 coverage evidence path: {relative}"


def test_phase2_registry_excludes_non_goals() -> None:
    assert "HOST_FULL_ACCESS" not in {item.value for item in PermissionProfileName}
    for profile in PermissionProfileName:
        allowed = set(default_allowed_tools(profile))
        overlap = allowed & _NON_GOAL_TOOLS
        assert not overlap, f"{profile.value} exposes non-goal tools: {sorted(overlap)}"


@pytest.fixture
def temporary_git_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    assert PHASE2_CODING_FIXTURE.is_dir(), "phase2_coding_project fixture is missing"
    destination = tmp_path / "phase2_coding_project"
    shutil.copytree(PHASE2_CODING_FIXTURE, destination)
    isolated_home = tmp_path / "isolated-home"
    isolated_xdg = tmp_path / "isolated-xdg"
    isolated_home.mkdir()
    isolated_xdg.mkdir()
    gitconfig = isolated_home / "gitconfig"
    gitconfig.write_text(
        "[user]\n\tname = fixture\n\temail = fixture@example.test\n",
        encoding="utf-8",
    )
    env = {
        "HOME": str(isolated_home),
        "USERPROFILE": str(isolated_home),
        "XDG_CONFIG_HOME": str(isolated_xdg),
        "GIT_CONFIG_GLOBAL": str(gitconfig),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_SYSTEM": "NUL",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    subprocess.run(
        ["git", "init"],
        cwd=destination,
        check=True,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "add", "."],
        cwd=destination,
        check=True,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "fixture"],
        cwd=destination,
        check=True,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
    )
    _monkeypatch.set(monkeypatch)
    return destination.resolve()


def _collect_git_writes(requests: list[ExecutionRequest]) -> tuple[str, ...]:
    writes: list[str] = []
    for request in requests:
        argv = request.argv
        if not argv or argv[0] != "git":
            continue
        tokens = [token for token in argv[1:] if not token.startswith("-")]
        if tokens and tokens[0] in _GIT_WRITE_SUBCOMMANDS:
            writes.append(" ".join(argv))
    return tuple(writes)


def _serialize_model_input(provider: FakeModelProvider) -> str:
    chunks: list[str] = []
    for request in provider.requests:
        chunks.append(request.model_dump_json())
        for message in request.messages:
            chunks.append(message.content or "")
        for tool in request.tools:
            chunks.append(tool.name)
    return "\n".join(chunks)


async def run_scripted_phase2_correction_flow(
    project: Path,
    *,
    docker_backend_cls: type[Any] | None = None,
    collector_timeout: float = 30,
) -> Phase2CorrectionResult:
    from agent_foundations.cli import main

    monkeypatch = _monkeypatch.get()
    fail_path = project / "tests" / "test_fail.py"
    baseline = sha256_bytes(fail_path.read_bytes())
    patch = parse_and_validate_patch(
        _DIFF,
        (BaselineEntry(path="tests/test_fail.py", sha256=baseline),),
        project,
    )
    requests: list[ExecutionRequest] = []

    class DualBackend:
        def __init__(self, workspace: Path) -> None:
            self._workspace = workspace

        def _pytest_result(self, request: ExecutionRequest) -> ExecutionResult:
            fail_file = self._workspace / "tests" / "test_fail.py"
            failing = "assert False" in fail_file.read_text(encoding="utf-8")
            stdout = (_FAIL_JUNIT if failing else _PASS_JUNIT).encode("utf-8")
            return ExecutionResult(
                execution_id=request.execution_id,
                exit_code=1 if failing else 0,
                stdout=stdout,
                stderr=b"",
                timed_out=False,
                cancelled=False,
                output_truncated=False,
            )

        def _git_result(self, request: ExecutionRequest) -> ExecutionResult:
            stdout = b""
            if "status" in request.argv:
                stdout = b" M tests/test_fail.py\0"
            elif "diff" in request.argv:
                stdout = _DIFF.encode("utf-8")
            elif "log" in request.argv:
                stdout = b"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\tfixture\n"
            return ExecutionResult(
                execution_id=request.execution_id,
                exit_code=0,
                stdout=stdout,
                stderr=b"",
                timed_out=False,
                cancelled=False,
                output_truncated=False,
            )

        async def execute(
            self,
            request: object,
            *,
            output_sink: ByteStreamSink | None = None,
        ) -> ExecutionResult:
            assert isinstance(request, ExecutionRequest)
            requests.append(request)
            if request.mount_mode == "project_write":
                prepared = prepare_patch(patch, self._workspace)
                apply_prepared_patch_atomically(prepared, self._workspace)
                return ExecutionResult(
                    execution_id=request.execution_id,
                    exit_code=0,
                    stdout=b'{"status":"applied"}\n',
                    stderr=b"",
                    timed_out=False,
                    cancelled=False,
                    output_truncated=False,
                )
            if request.argv and request.argv[0] == "git":
                return self._git_result(request)
            return await FakeBackend(result_factory=self._pytest_result).execute(
                request,
                output_sink=output_sink,
            )

        async def cancel(self, execution_id: str) -> None:
            del execution_id

    provider = FakeModelProvider(
        [
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="call-set-plan",
                        name="set_plan",
                        arguments={
                            "goal": "Fix the failing pytest node and confirm regression",
                            "steps": [
                                {
                                    "step_id": "inspect",
                                    "description": "Read the failing test",
                                },
                                {
                                    "step_id": "repair",
                                    "description": "Apply a patch and re-run gates",
                                },
                            ],
                        },
                    ),
                ),
            ),
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="call-read-fail",
                        name="read_file",
                        arguments={"path": "tests/test_fail.py"},
                    ),
                ),
            ),
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="call-full-gate",
                        name="run_command",
                        arguments={
                            "gate_id": "manifest.python.pytest",
                            "target": "tests",
                            "flags": ["-q"],
                            "cwd": ".",
                            "timeout_seconds": 30,
                        },
                    ),
                ),
            ),
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="call-failed-node",
                        name="run_command",
                        arguments={
                            "gate_id": "manifest.python.pytest",
                            "target": NODE_ID,
                            "flags": ["-q"],
                            "cwd": ".",
                            "timeout_seconds": 30,
                        },
                    ),
                ),
            ),
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="call-validate",
                        name="validate_patch",
                        arguments={
                            "diff": _DIFF,
                            "baselines": [
                                {"path": "tests/test_fail.py", "sha256": baseline},
                            ],
                        },
                    ),
                ),
            ),
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="call-apply",
                        name="apply_patch",
                        arguments={"patch_id": patch.patch_id},
                    ),
                ),
            ),
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="call-targeted-green",
                        name="run_command",
                        arguments={
                            "gate_id": "manifest.python.pytest",
                            "target": NODE_ID,
                            "flags": ["-q"],
                            "cwd": ".",
                            "timeout_seconds": 30,
                        },
                    ),
                ),
            ),
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="call-affected-regression",
                        name="run_command",
                        arguments={
                            "gate_id": "manifest.python.pytest",
                            "target": "tests",
                            "flags": ["-q"],
                            "cwd": ".",
                            "timeout_seconds": 30,
                        },
                    ),
                ),
            ),
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="call-git-diff",
                        name="git_diff",
                        arguments={},
                    ),
                ),
            ),
            ModelResponse(content="Targeted green and affected regression passed."),
        ],
    )
    controller = PlanController()
    journal = ExecutionFactJournal()
    original_registry = main.build_tool_registry

    def patched_registry(root: Path, **kwargs: Any) -> Any:
        kwargs.setdefault("controller", controller)
        kwargs.setdefault("journal", journal)
        return original_registry(root, **kwargs)

    monkeypatch.setenv("AGENT_API_KEY", "test-placeholder")
    monkeypatch.setenv("AGENT_MODEL", "test-model")
    monkeypatch.setattr(main, "build_provider", lambda: provider)
    if docker_backend_cls is None:
        monkeypatch.setattr(main, "DockerBackend", DualBackend)
    else:
        recorded_backend = docker_backend_cls

        class RequestRecordingBackend:
            def __init__(
                self,
                workspace: Path,
                *,
                sandbox_manifest: Any | None = None,
                process_factory: Any = None,
                cleanup_factory: Any = None,
            ) -> None:
                kwargs: dict[str, Any] = {}
                if sandbox_manifest is not None:
                    kwargs["sandbox_manifest"] = sandbox_manifest
                if process_factory is not None:
                    kwargs["process_factory"] = process_factory
                if cleanup_factory is not None:
                    kwargs["cleanup_factory"] = cleanup_factory
                self._inner = recorded_backend(workspace, **kwargs)

            async def execute(
                self,
                request: object,
                *,
                output_sink: ByteStreamSink | None = None,
            ) -> ExecutionResult:
                assert isinstance(request, ExecutionRequest)
                requests.append(request)
                result = await self._inner.execute(request, output_sink=output_sink)
                return cast(ExecutionResult, result)

            async def cancel(self, execution_id: str) -> None:
                await self._inner.cancel(execution_id)

            @property
            def active_execution_ids(self) -> tuple[str, ...]:
                return tuple(self._inner.active_execution_ids)

        monkeypatch.setattr(main, "DockerBackend", RequestRecordingBackend)
    monkeypatch.setattr(main, "build_tool_registry", patched_registry)

    database_path = project.parent / "chat.sqlite3"
    services = main.build_chat_services(project.parent)
    await services.repository.initialize()
    conversation = await services.repository.create_conversation(
        title="Phase 2 correction",
        project_root=project,
        permission_profile=PermissionProfileName.PROJECT_FULL_ACCESS,
    )
    session_id = str(uuid4())
    message, _run = await services.repository.begin_run(
        conversation.conversation_id,
        content="Fix the failing gate using CommandFeedback",
        session_id=session_id,
    )
    sse_text: list[str] = []

    async def collect_sse() -> None:
        async for event in services.broker.subscribe(conversation.conversation_id):
            sse_text.append(event.model_dump_json())
            if event.type in {ChatEventType.RUN_COMPLETED, ChatEventType.RUN_FAILED}:
                return

    collector = asyncio.create_task(collect_sse())
    await asyncio.sleep(0)
    await services.runner.run_turn(
        conversation.conversation_id,
        session_id,
        message.message_id,
        message.content,
    )
    await asyncio.wait_for(collector, timeout=collector_timeout)

    write_index = next(
        (
            index
            for index, request in enumerate(requests)
            if request.mount_mode == "project_write"
        ),
        len(requests),
    )
    targeted_reproduction_count = sum(
        1
        for request in requests[:write_index]
        if NODE_ID in request.argv
    )
    post_apply_full = [
        request
        for request in requests[write_index:]
        if "pytest" in request.argv
        and "tests" in request.argv
        and NODE_ID not in request.argv
    ]
    affected_regression_passed = (
        fail_path.read_text(encoding="utf-8") == FIXED_TEST
        and bool(post_apply_full)
    )

    model_blob = _serialize_model_input(provider)
    sqlite_blob = database_path.read_bytes()
    exposed = (
        SECRET in model_blob
        or SECRET.encode() in sqlite_blob
        or SECRET in "\n".join(sse_text)
    )

    durable = DurableRunRepository(database_path)
    await durable.initialize()
    durable_run = await durable.get_run(session_id)
    return Phase2CorrectionResult(
        status=durable_run.status,
        targeted_reproduction_count=targeted_reproduction_count,
        affected_regression_passed=affected_regression_passed,
        raw_output_exposed_to_model=exposed,
        git_writes=_collect_git_writes(requests),
    )


@pytest.mark.asyncio
async def test_phase2_agent_recovers_from_structured_command_feedback(
    temporary_git_project: Path,
) -> None:
    result = await run_scripted_phase2_correction_flow(temporary_git_project)
    assert result.status is DurableRunStatus.COMPLETED
    assert result.targeted_reproduction_count == 1
    assert result.affected_regression_passed is True
    assert result.raw_output_exposed_to_model is False
    assert result.git_writes == ()


@dataclass(frozen=True)
class Phase2DockerCorrectionResult:
    correction: Phase2CorrectionResult
    docker_argvs: tuple[tuple[str, ...], ...]
    snapshot_wrote_host: bool


async def run_scripted_phase2_docker_correction_flow(
    project: Path,
) -> Phase2DockerCorrectionResult:
    from agent_foundations.cli.main import _phase2d_sandbox_manifest
    from agent_foundations.execution import docker as docker_mod

    conftest = project / "conftest.py"
    if conftest.exists():
        conftest.unlink()
    pinned = _phase2d_sandbox_manifest()
    docker_argvs: list[tuple[str, ...]] = []
    snapshot_wrote_host = False
    fail_path = project / "tests" / "test_fail.py"
    original_fail = fail_path.read_text(encoding="utf-8")
    seen_project_write = False

    class RecordingDockerBackend:
        def __init__(
            self,
            workspace: Path,
            *,
            sandbox_manifest: Any | None = None,
            process_factory: Any = None,
            cleanup_factory: Any = None,
        ) -> None:
            async def record_and_spawn(argv: tuple[str, ...]) -> Any:
                docker_argvs.append(argv)
                spawn = process_factory or docker_mod._spawn_docker
                return await spawn(argv)

            self._inner = docker_mod.DockerBackend(
                workspace,
                sandbox_manifest=sandbox_manifest or pinned,
                process_factory=record_and_spawn,
                cleanup_factory=cleanup_factory or docker_mod._spawn_docker,
            )

        async def execute(
            self,
            request: object,
            *,
            output_sink: ByteStreamSink | None = None,
        ) -> ExecutionResult:
            nonlocal snapshot_wrote_host, seen_project_write
            assert isinstance(request, ExecutionRequest)
            result = await self._inner.execute(request, output_sink=output_sink)
            if request.mount_mode == "project_write":
                seen_project_write = True
            elif request.mount_mode == "snapshot" and not seen_project_write:
                if fail_path.read_text(encoding="utf-8") != original_fail:
                    snapshot_wrote_host = True
                if (project / ".pytest_cache").exists():
                    snapshot_wrote_host = True
            return result

        async def cancel(self, execution_id: str) -> None:
            await self._inner.cancel(execution_id)

        @property
        def active_execution_ids(self) -> tuple[str, ...]:
            return tuple(self._inner.active_execution_ids)

    correction = await run_scripted_phase2_correction_flow(
        project,
        docker_backend_cls=RecordingDockerBackend,
        collector_timeout=180,
    )
    return Phase2DockerCorrectionResult(
        correction=correction,
        docker_argvs=tuple(docker_argvs),
        snapshot_wrote_host=snapshot_wrote_host,
    )


@pytest.mark.docker
@pytest.mark.asyncio
async def test_phase2_agent_recovers_from_structured_command_feedback_in_docker(
    temporary_git_project: Path,
    pytestconfig: pytest.Config,
) -> None:
    if pytestconfig.getoption("-m") != "docker":
        pytest.skip("requires explicit -m docker authorization")
    from agent_foundations.cli.main import _phase2d_sandbox_manifest

    pinned = _phase2d_sandbox_manifest()
    placeholder = f"sha256:{'c' * 64}"
    assert pinned.python.final_image_id != placeholder
    result = await run_scripted_phase2_docker_correction_flow(temporary_git_project)
    assert result.correction.status is DurableRunStatus.COMPLETED
    assert result.correction.targeted_reproduction_count == 1
    assert result.correction.affected_regression_passed is True
    assert result.correction.raw_output_exposed_to_model is False
    assert result.correction.git_writes == ()
    assert result.snapshot_wrote_host is False
    snapshot_argvs = [
        argv
        for argv in result.docker_argvs
        if len(argv) > 1 and argv[1] == "run"
    ]
    assert snapshot_argvs, "scripted correction must launch docker run, not DualBackend"
    joined = [" ".join(argv) for argv in snapshot_argvs]
    assert all("--network none" in text for text in joined)
    assert all("--user 65532:65532" in text for text in joined)
    assert any(pinned.python.final_image_id in text for text in joined)
    assert all(placeholder not in text for text in joined)
