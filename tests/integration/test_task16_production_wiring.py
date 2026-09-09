from __future__ import annotations

import asyncio
import hashlib
import sqlite3
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from agent_foundations.chat.models import (
    ApprovalDecision,
    PermissionMode,
    PolicyDecision,
    RunStatus,
)
from agent_foundations.chat.repository import ConversationRepository
from agent_foundations.chat.tool_execution import FilesystemAccessController
from agent_foundations.domain.model import ModelResponse
from agent_foundations.domain.tool import ToolCall
from agent_foundations.execution.models import ExecutionResult
from agent_foundations.providers.fake import FakeModelProvider
from agent_foundations.security.approvals import AuthorizationApproval, AuthorizationStatus
from agent_foundations.security.capabilities import CapabilityConsumer, CapabilityIssuer
from agent_foundations.security.models import (
    PermissionProfile,
    PermissionProfileName,
    PolicyRequest,
    PolicyResource,
    ResourceScope,
    default_allowed_tools,
)
from agent_foundations.security.policy import PolicyEngine
from agent_foundations.security.repository import (
    AuthorizationCorruptStateError,
    AuthorizationRepository,
)
from agent_foundations.tools.filesystem.read_file import READ_FILE_MANIFEST
from agent_foundations.tools.patch.applier import (
    apply_prepared_patch_atomically,
    prepare_patch,
)
from agent_foundations.tools.patch.models import BaselineEntry
from agent_foundations.tools.patch.validator import parse_and_validate_patch


@pytest.mark.asyncio
async def test_external_read_policy_uses_versioned_profile_as_authority(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    external_file = tmp_path / "outside.txt"
    external_file.write_text("outside\n", encoding="utf-8")
    repository = ConversationRepository(tmp_path / "state.sqlite3")
    await repository.initialize()
    conversation = await repository.create_conversation(
        title="Profile authority",
        project_root=project_root,
        permission_profile=PermissionProfileName.ASK_ALWAYS,
    )
    conversation = conversation.model_copy(
        update={"permission_mode": PermissionMode.PROJECT_READ_ONLY},
    )

    decision = FilesystemAccessController().decide(
        conversation,
        str(external_file),
    )

    assert decision.decision is PolicyDecision.ASK


@pytest.mark.asyncio
async def test_production_chat_composition_exposes_and_persists_patch_proposal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_foundations.cli import main

    project_root = tmp_path / "project"
    project_root.mkdir()
    readme = project_root / "README.md"
    readme.write_text("# Before\n", encoding="utf-8", newline="\n")
    baseline = hashlib.sha256(readme.read_bytes()).hexdigest()
    diff = """diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-# Before
+# After
"""
    provider = FakeModelProvider(
        [
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="validate-call",
                        name="validate_patch",
                        arguments={
                            "diff": diff,
                            "baselines": [
                                {"path": "README.md", "sha256": baseline},
                            ],
                        },
                    ),
                ),
            ),
            ModelResponse(content="Patch proposal is ready."),
        ],
    )
    monkeypatch.setenv("AGENT_API_KEY", "test-placeholder")
    monkeypatch.setenv("AGENT_MODEL", "test-model")
    monkeypatch.setattr(main, "build_provider", lambda: provider)
    database_path = tmp_path / "chat.sqlite3"
    services = main.build_chat_services(tmp_path)
    await services.repository.initialize()
    conversation = await services.repository.create_conversation(
        title="Controlled patch",
        project_root=project_root,
        permission_profile=PermissionProfileName.ASK_ALWAYS,
    )
    session_id = str(uuid4())
    message, _run = await services.repository.begin_run(
        conversation.conversation_id,
        content="Prepare the patch",
        session_id=session_id,
    )

    await services.runner.run_turn(
        conversation.conversation_id,
        session_id,
        message.message_id,
        message.content,
    )

    exposed_tools = {tool.name for tool in provider.requests[0].tools}
    assert {"validate_patch", "apply_patch"} <= exposed_tools
    with sqlite3.connect(database_path) as connection:
        durable_count = connection.execute(
            "SELECT COUNT(*) FROM durable_runs WHERE run_id = ?",
            (session_id,),
        ).fetchone()[0]
        proposal_count = connection.execute(
            "SELECT COUNT(*) FROM patch_proposals WHERE run_id = ?",
            (session_id,),
        ).fetchone()[0]
    assert durable_count == 1
    assert proposal_count == 1
    assert readme.read_text(encoding="utf-8") == "# Before\n"


@pytest.mark.asyncio
async def test_production_chat_runs_approval_capability_ledger_and_patch_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_foundations.chat.models import ApprovalDecision
    from agent_foundations.cli import main

    project_root = tmp_path / "project"
    project_root.mkdir()
    readme = project_root / "README.md"
    readme.write_text("before\n", encoding="utf-8", newline="\n")
    baseline = hashlib.sha256(readme.read_bytes()).hexdigest()
    diff = """diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-before
+after
"""
    patch = parse_and_validate_patch(
        diff,
        (BaselineEntry(path="README.md", sha256=baseline),),
        project_root,
    )
    provider = FakeModelProvider(
        [
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="validate-call",
                        name="validate_patch",
                        arguments={
                            "diff": diff,
                            "baselines": [
                                {"path": "README.md", "sha256": baseline},
                            ],
                        },
                    ),
                ),
            ),
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="apply-call",
                        name="apply_patch",
                        arguments={"patch_id": patch.patch_id},
                    ),
                ),
            ),
            ModelResponse(content="Patch applied through the controlled path."),
        ],
    )

    class LocalSandboxBoundary:
        calls = 0

        def __init__(self, root: Path) -> None:
            self._root = root

        async def execute(self, request: object) -> ExecutionResult:
            from agent_foundations.execution.models import ExecutionRequest

            assert isinstance(request, ExecutionRequest)
            assert request.mount_mode == "project_write"
            type(self).calls += 1
            prepared = prepare_patch(patch, self._root)
            apply_prepared_patch_atomically(prepared, self._root)
            return ExecutionResult(
                execution_id=request.execution_id,
                exit_code=0,
                stdout=b'{"status":"applied"}\n',
                stderr=b"",
                timed_out=False,
                cancelled=False,
                output_truncated=False,
            )

        async def cancel(self, execution_id: str) -> None:
            del execution_id

    monkeypatch.setenv("AGENT_API_KEY", "test-placeholder")
    monkeypatch.setenv("AGENT_MODEL", "test-model")
    monkeypatch.setattr(main, "build_provider", lambda: provider)
    monkeypatch.setattr(main, "DockerBackend", LocalSandboxBoundary)
    database_path = tmp_path / "chat.sqlite3"
    services = main.build_chat_services(tmp_path)
    await services.repository.initialize()
    conversation = await services.repository.create_conversation(
        title="Apply controlled patch",
        project_root=project_root,
        permission_profile=PermissionProfileName.ASK_ALWAYS,
    )
    session_id = str(uuid4())
    message, _run = await services.repository.begin_run(
        conversation.conversation_id,
        content="Apply the patch",
        session_id=session_id,
    )
    run_task = __import__("asyncio").create_task(
        services.runner.run_turn(
            conversation.conversation_id,
            session_id,
            message.message_id,
            message.content,
        ),
    )
    approval = None
    for _ in range(200):
        _latest, approval = await services.repository.get_conversation_state(
            conversation.conversation_id,
        )
        if approval is not None:
            break
        await __import__("asyncio").sleep(0.01)
    assert approval is not None

    await services.coordinator.resolve(
        approval.approval_id,
        ApprovalDecision.APPROVE,
    )
    await run_task

    assert readme.read_text(encoding="utf-8") == "after\n"
    assert LocalSandboxBoundary.calls == 1
    with sqlite3.connect(database_path) as connection:
        capability_count = connection.execute(
            "SELECT COUNT(*) FROM capabilities WHERE run_id = ? AND consumed_at IS NOT NULL",
            (session_id,),
        ).fetchone()[0]
        committed_effects = connection.execute(
            "SELECT COUNT(*) FROM side_effects WHERE run_id = ? AND status = 'committed'",
            (session_id,),
        ).fetchone()[0]
    assert capability_count == 1
    assert committed_effects == 1


@pytest.mark.asyncio
async def test_production_chat_write_deny_leaves_no_effect_or_backend_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_foundations.cli import main

    project_root = tmp_path / "project"
    project_root.mkdir()
    readme = project_root / "README.md"
    readme.write_text("before\n", encoding="utf-8", newline="\n")
    baseline = hashlib.sha256(readme.read_bytes()).hexdigest()
    diff = """diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-before
+denied
"""
    patch = parse_and_validate_patch(
        diff,
        (BaselineEntry(path="README.md", sha256=baseline),),
        project_root,
    )
    provider = FakeModelProvider(
        [
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="deny-validate-call",
                        name="validate_patch",
                        arguments={
                            "diff": diff,
                            "baselines": [{"path": "README.md", "sha256": baseline}],
                        },
                    ),
                ),
            ),
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="deny-apply-call",
                        name="apply_patch",
                        arguments={"patch_id": patch.patch_id},
                    ),
                ),
            ),
            ModelResponse(content="The requested patch was denied."),
        ],
    )

    class BackendMustNotRun:
        calls = 0

        def __init__(self, root: Path) -> None:
            del root

        async def execute(self, request: object) -> ExecutionResult:
            del request
            type(self).calls += 1
            raise AssertionError("denied write must not reach the backend")

        async def cancel(self, execution_id: str) -> None:
            del execution_id

    monkeypatch.setenv("AGENT_API_KEY", "test-placeholder")
    monkeypatch.setenv("AGENT_MODEL", "test-model")
    monkeypatch.setattr(main, "build_provider", lambda: provider)
    monkeypatch.setattr(main, "DockerBackend", BackendMustNotRun)
    database_path = tmp_path / "chat.sqlite3"
    services = main.build_chat_services(tmp_path)
    await services.repository.initialize()
    conversation = await services.repository.create_conversation(
        title="Deny controlled patch",
        project_root=project_root,
        permission_profile=PermissionProfileName.ASK_ALWAYS,
    )
    session_id = str(uuid4())
    message, _run = await services.repository.begin_run(
        conversation.conversation_id,
        content="Do not apply without approval",
        session_id=session_id,
    )
    run_task = asyncio.create_task(
        services.runner.run_turn(
            conversation.conversation_id,
            session_id,
            message.message_id,
            message.content,
        ),
    )
    approval = None
    for _ in range(200):
        _latest, approval = await services.repository.get_conversation_state(
            conversation.conversation_id,
        )
        if approval is not None:
            break
        await asyncio.sleep(0.01)
    assert approval is not None

    await services.coordinator.resolve(approval.approval_id, ApprovalDecision.DENY)
    await run_task

    assert readme.read_text(encoding="utf-8") == "before\n"
    assert BackendMustNotRun.calls == 0
    with sqlite3.connect(database_path) as connection:
        committed_effects = connection.execute(
            "SELECT COUNT(*) FROM side_effects WHERE run_id = ? AND status = 'committed'",
            (session_id,),
        ).fetchone()[0]
        consumed_capabilities = connection.execute(
            "SELECT COUNT(*) FROM capabilities WHERE run_id = ? AND consumed_at IS NOT NULL",
            (session_id,),
        ).fetchone()[0]
    assert committed_effects == 0
    assert consumed_capabilities == 0


@pytest.mark.asyncio
async def test_profile_version_change_invalidates_old_capability_and_requires_new_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_foundations.cli import main

    project_root = tmp_path / "project"
    project_root.mkdir()
    external = tmp_path / "outside.txt"
    external.write_text("outside\n", encoding="utf-8")
    provider = FakeModelProvider(
        [
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="new-profile-read",
                        name="read_file",
                        arguments={"path": str(external)},
                    ),
                ),
            ),
            ModelResponse(content="New profile approval completed."),
        ],
    )
    monkeypatch.setenv("AGENT_API_KEY", "test-placeholder")
    monkeypatch.setenv("AGENT_MODEL", "test-model")
    monkeypatch.setattr(main, "build_provider", lambda: provider)
    database_path = tmp_path / "chat.sqlite3"
    services = main.build_chat_services(tmp_path)
    await services.repository.initialize()
    conversation = await services.repository.create_conversation(
        title="Profile re-confirmation",
        project_root=project_root,
        permission_profile=PermissionProfileName.ASK_ALWAYS,
    )

    old_run_id = str(uuid4())
    _old_message, old_run = await services.repository.begin_run(
        conversation.conversation_id,
        content="Seed the old profile authorization",
        session_id=old_run_id,
    )
    await services.repository.transition_run(
        old_run.session_id,
        RunStatus.QUEUED,
        RunStatus.RUNNING,
    )
    await services.repository.complete_run(old_run.session_id, "Old run complete")

    authorization_repository = AuthorizationRepository.from_path(database_path)
    old_profile = PermissionProfile(
        name=PermissionProfileName.ASK_ALWAYS,
        version=conversation.profile_version,
        allowed_tools=default_allowed_tools(PermissionProfileName.ASK_ALWAYS),
    )
    old_request = PolicyRequest(
        profile_version=old_profile.version,
        run_id=old_run_id,
        tool_call_id="old-profile-read",
        tool_name="read_file",
        manifest=READ_FILE_MANIFEST,
        resource=PolicyResource(
            kind="project_path",
            scope=ResourceScope.EXTERNAL_EXACT_PATH,
            identifier=str(external.resolve(strict=True)),
        ),
        operation="read",
    )
    old_outcome = PolicyEngine().decide(old_profile, old_request)
    assert old_outcome.decision.value == PolicyDecision.ASK.value
    approval_service = AuthorizationApproval(
        authorization_repository,
        old_profile.name,
    )
    pending = await approval_service.request(old_request)
    approved = approval_service.decide(pending, AuthorizationStatus.APPROVED)
    old_capability = await CapabilityIssuer(
        authorization_repository,
        old_profile.name,
        ttl=timedelta(minutes=5),
    ).issue(old_request, old_outcome, approved)

    changed = await services.repository.update_conversation(
        conversation.conversation_id,
        permission_profile=PermissionProfileName.RISK_BASED,
    )
    changed = await services.repository.update_conversation(
        conversation.conversation_id,
        permission_profile=PermissionProfileName.ASK_ALWAYS,
    )
    assert changed.profile_version == 3
    old_authorization = await authorization_repository.get_authorization(
        old_capability.authorization_id,
    )
    assert old_authorization.status is AuthorizationStatus.INVALIDATED

    new_run_id = str(uuid4())
    new_execution = old_request.model_copy(
        update={
            "profile_version": changed.profile_version,
            "run_id": new_run_id,
            "tool_call_id": "new-profile-read",
        },
    )
    with pytest.raises(AuthorizationCorruptStateError):
        await CapabilityConsumer(authorization_repository).consume(
            old_capability.capability_id,
            new_execution,
        )

    message, _new_run = await services.repository.begin_run(
        conversation.conversation_id,
        content="Read under the changed profile",
        session_id=new_run_id,
    )
    run_task = asyncio.create_task(
        services.runner.run_turn(
            conversation.conversation_id,
            new_run_id,
            message.message_id,
            message.content,
        ),
    )
    new_approval = None
    for _ in range(200):
        _latest, new_approval = await services.repository.get_conversation_state(
            conversation.conversation_id,
        )
        if new_approval is not None:
            break
        await asyncio.sleep(0.01)
    assert new_approval is not None
    assert new_approval.approval_id != old_capability.authorization_id

    new_authorization = await authorization_repository.get_authorization(
        new_approval.approval_id,
    )
    assert new_authorization.profile_version == changed.profile_version
    assert new_authorization.status is AuthorizationStatus.PENDING

    await services.coordinator.resolve(
        new_approval.approval_id,
        ApprovalDecision.APPROVE,
    )
    await run_task
    resolved = await authorization_repository.get_authorization(
        new_approval.approval_id,
    )
    assert resolved.status is AuthorizationStatus.APPROVED
    assert await authorization_repository.find_capability_for_execution(
        new_run_id,
        "new-profile-read",
    ) is not None
