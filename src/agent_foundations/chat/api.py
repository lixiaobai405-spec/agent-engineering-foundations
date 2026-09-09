from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent_foundations.chat.approvals import ApprovalCoordinator, approval_view_fields
from agent_foundations.chat.durable_checkpoint import (
    execution_plan_to_chat_view,
    load_latest_conversation_plan,
)
from agent_foundations.chat.errors import ChatConflictError, ChatNotFoundError
from agent_foundations.chat.events import ChatEventBroker, encode_chat_sse
from agent_foundations.chat.lifecycle import log_sse_cancelled, log_sse_failed
from agent_foundations.chat.models import (
    AccessOperation,
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
    ChatEvent,
    ChatMessage,
    ChatToolActivity,
    Conversation,
    PermissionMode,
    RunRecord,
    RunStatus,
    new_id,
)
from agent_foundations.chat.repository import ConversationRepository
from agent_foundations.chat.runner import ConversationRunner
from agent_foundations.chat.supervisor import RunSupervisor
from agent_foundations.command_output.retention import ArtifactRetentionSweeper
from agent_foundations.durable.repository import DurableRunRepository
from agent_foundations.security.models import PermissionProfileName
from agent_foundations.tools.patch.repository import (
    PatchProposalRepository,
    PatchRepositoryError,
)

ARTIFACT_SWEEP_INTERVAL_SECONDS = 3600.0


@dataclass(frozen=True)
class ChatServices:
    repository: ConversationRepository
    broker: ChatEventBroker
    runner: ConversationRunner
    supervisor: RunSupervisor
    coordinator: ApprovalCoordinator
    patch_repository: PatchProposalRepository | None = None
    command_artifact_store: object | None = None
    command_artifact_repository: object | None = None
    command_output_tickets: object | None = None
    durable_repository: DurableRunRepository | None = None
    retention: ArtifactRetentionSweeper | None = None
    artifact_sweep_interval_seconds: float = ARTIFACT_SWEEP_INTERVAL_SECONDS


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateConversationRequest(_StrictModel):
    title: str = Field(min_length=1, max_length=120)
    project_root: str
    permission_mode: PermissionMode | None = None
    permission_profile: PermissionProfileName | None = None

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title must not be empty")
        return value

    @field_validator("project_root")
    @classmethod
    def project_root_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("project_root must not be empty")
        return value


class PatchConversationRequest(_StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    permission_mode: PermissionMode | None = None
    permission_profile: PermissionProfileName | None = None

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("title must not be empty")
        return value


class PostMessageRequest(_StrictModel):
    query: str = Field(min_length=1)

    @field_validator("query")
    @classmethod
    def query_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be empty")
        return value


class ApprovalDecisionRequest(_StrictModel):
    decision: ApprovalDecision


class PendingApprovalState(_StrictModel):
    approval_id: str
    conversation_id: str
    session_id: str
    tool_call_id: str
    tool_name: str
    canonical_path: str
    operation: str
    resource_kind: str
    scope: str
    policy_decision: str
    status: ApprovalStatus
    requested_at: str


class PatchFileSummary(_StrictModel):
    path: str
    operation: str
    hunk_count: int
    baseline_status: str
    summary: str = Field(max_length=240)


class PatchPreviewState(_StrictModel):
    patch_id: str
    files: list[PatchFileSummary]


class ConversationPlanStep(_StrictModel):
    step_id: str
    status: str
    description: str


class ConversationPlanState(_StrictModel):
    plan_id: str
    version: int
    goal: str
    replan_count: int
    max_replans: int
    steps: list[ConversationPlanStep]


class ConversationStateResponse(_StrictModel):
    latest_run: RunRecord | None
    pending_approval: PendingApprovalState | None
    patch_preview: PatchPreviewState | None
    plan: ConversationPlanState | None = None


def _pending_approval_state(
    approval: ApprovalRequest,
) -> PendingApprovalState:
    operation, resource_kind, scope, policy_decision = approval_view_fields(approval)
    return PendingApprovalState(
        approval_id=approval.approval_id,
        conversation_id=approval.conversation_id,
        session_id=approval.session_id,
        tool_call_id=approval.tool_call_id,
        tool_name=approval.tool_name,
        canonical_path=approval.canonical_path,
        operation=operation,
        resource_kind=resource_kind,
        scope=scope,
        policy_decision=policy_decision,
        status=ApprovalStatus.PENDING,
        requested_at=approval.requested_at.isoformat(),
    )


async def _patch_preview_state(
    services: ChatServices,
    approval: ApprovalRequest | None,
) -> PatchPreviewState | None:
    patch_repository = services.patch_repository
    if (
        approval is None
        or approval.operation is not AccessOperation.APPLY
        or patch_repository is None
        or not approval.canonical_path.startswith("patch:")
    ):
        return None
    patch_id = approval.canonical_path.removeprefix("patch:")
    try:
        patch = await patch_repository.get(approval.session_id, patch_id)
        conversation = await services.repository.get_conversation(
            approval.conversation_id,
        )
    except (ValueError, ChatNotFoundError, PatchRepositoryError):
        return None
    return await asyncio.to_thread(
        _build_patch_preview,
        Path(conversation.project_root),
        patch,
    )


def _build_patch_preview(project_root: Path, patch: object) -> PatchPreviewState:
    from agent_foundations.tools.patch.models import ValidatedPatch

    assert isinstance(patch, ValidatedPatch)
    root = project_root.resolve(strict=True)
    files: list[PatchFileSummary] = []
    for file in patch.files:
        target = root.joinpath(*file.path.split("/"))
        if file.operation.value == "create":
            baseline_status = "new" if not target.exists() else "stale"
        else:
            baseline_status = "stale"
            try:
                if (
                    not target.is_symlink()
                    and target.is_file()
                    and file.baseline_sha256 is not None
                    and hashlib.sha256(target.read_bytes()).hexdigest()
                    == file.baseline_sha256
                ):
                    baseline_status = "matched"
            except OSError:
                pass
        files.append(
            PatchFileSummary(
                path=file.path,
                operation=file.operation.value,
                hunk_count=file.hunk_count,
                baseline_status=baseline_status,
                summary=f"+{file.add_line_count} -{file.remove_line_count}",
            ),
        )
    return PatchPreviewState(patch_id=patch.patch_id, files=files)


def _stable_http_error(exc: ChatNotFoundError | ChatConflictError) -> HTTPException:
    if isinstance(exc, ChatNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="conflict")


def _validation_http_error(message: str) -> HTTPException:
    return HTTPException(status_code=422, detail=message)


_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "testclient", "testserver"})


def _origin_allowed(request: Request) -> bool:
    origin = request.headers.get("origin", "")
    if not origin:
        return False
    lowered = origin.lower()
    return (
        lowered.startswith("http://127.0.0.1")
        or lowered.startswith("http://localhost")
        or lowered.startswith("http://[::1]")
        or lowered.startswith("http://testserver")
    )


def _client_is_loopback(request: Request) -> bool:
    host = request.client.host if request.client is not None else ""
    return host in _LOOPBACK_HOSTS


def _require_local_user(request: Request, *, require_origin: bool) -> None:
    if not _client_is_loopback(request):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ARTIFACT_SCOPE_DENIED")
    origin = request.headers.get("origin", "")
    if require_origin and not _origin_allowed(request):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ARTIFACT_SCOPE_DENIED")
    if origin and not _origin_allowed(request):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ARTIFACT_SCOPE_DENIED")


async def _owned_artifact(
    services: ChatServices,
    conversation_id: str,
    session_id: str,
    artifact_id: str,
) -> tuple[Any, Any]:
    from agent_foundations.command_output.models import ARTIFACT_ID_PATTERN
    from agent_foundations.command_output.repository import (
        CommandArtifactNotFoundError,
        CommandArtifactRepository,
    )
    from agent_foundations.command_output.store import CommandArtifactStore

    store = services.command_artifact_store
    artifacts = services.command_artifact_repository
    if not isinstance(store, CommandArtifactStore) or not isinstance(
        artifacts,
        CommandArtifactRepository,
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    if ARTIFACT_ID_PATTERN.fullmatch(artifact_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ARTIFACT_SCOPE_DENIED")
    try:
        run = await services.repository.get_run(session_id)
        conversation = await services.repository.get_conversation(conversation_id)
    except ChatNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ARTIFACT_SCOPE_DENIED",
        ) from exc
    if run.conversation_id != conversation.conversation_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ARTIFACT_SCOPE_DENIED")
    try:
        metadata = artifacts.fetch_artifact(artifact_id)
    except CommandArtifactNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ARTIFACT_NOT_READABLE",
        ) from exc
    if str(metadata.run_id) != session_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ARTIFACT_SCOPE_DENIED")
    return store, metadata


def create_chat_router(
    services: ChatServices,
    *,
    keepalive_seconds: float = 15.0,
) -> APIRouter:
    router = APIRouter()
    repository = services.repository
    broker = services.broker
    runner = services.runner
    supervisor = services.supervisor
    coordinator = services.coordinator

    @router.post(
        "/conversations",
        status_code=status.HTTP_201_CREATED,
        response_model=Conversation,
    )
    async def create_conversation(request: CreateConversationRequest) -> Conversation:
        try:
            return await repository.create_conversation(
                title=request.title,
                project_root=Path(request.project_root),
                permission_mode=request.permission_mode,
                permission_profile=request.permission_profile,
            )
        except ValueError as exc:
            raise _validation_http_error("invalid conversation request") from exc

    @router.get("/conversations", response_model=list[Conversation])
    async def list_conversations() -> list[Conversation]:
        return await repository.list_conversations()

    @router.get("/conversations/{conversation_id}", response_model=Conversation)
    async def get_conversation(conversation_id: UUID) -> Conversation:
        conversation_key = str(conversation_id)
        try:
            return await repository.get_conversation(conversation_key)
        except ChatNotFoundError as exc:
            raise _stable_http_error(exc) from exc

    @router.patch("/conversations/{conversation_id}", response_model=Conversation)
    async def patch_conversation(
        conversation_id: UUID,
        request: PatchConversationRequest,
    ) -> Conversation:
        conversation_key = str(conversation_id)
        try:
            return await repository.update_conversation(
                conversation_key,
                title=request.title,
                permission_mode=request.permission_mode,
                permission_profile=request.permission_profile,
            )
        except ChatNotFoundError as exc:
            raise _stable_http_error(exc) from exc
        except ChatConflictError as exc:
            raise _stable_http_error(exc) from exc
        except ValueError as exc:
            raise _validation_http_error("invalid conversation update") from exc

    @router.get(
        "/conversations/{conversation_id}/messages",
        response_model=list[ChatMessage],
    )
    async def list_messages(conversation_id: UUID) -> list[ChatMessage]:
        conversation_key = str(conversation_id)
        try:
            await repository.get_conversation(conversation_key)
        except ChatNotFoundError as exc:
            raise _stable_http_error(exc) from exc
        return await repository.list_messages(conversation_key)

    @router.get(
        "/conversations/{conversation_id}/runs",
        response_model=list[RunRecord],
    )
    async def list_runs(conversation_id: UUID) -> list[RunRecord]:
        try:
            return await repository.list_runs(str(conversation_id))
        except ChatNotFoundError as exc:
            raise _stable_http_error(exc) from exc

    @router.get(
        "/conversations/{conversation_id}/activities",
        response_model=list[ChatToolActivity],
    )
    async def list_tool_activities(
        conversation_id: UUID,
    ) -> list[ChatToolActivity]:
        try:
            return await repository.list_tool_activities(str(conversation_id))
        except ChatNotFoundError as exc:
            raise _stable_http_error(exc) from exc

    @router.get(
        "/conversations/{conversation_id}/state",
        response_model=ConversationStateResponse,
    )
    async def get_conversation_state(conversation_id: UUID) -> ConversationStateResponse:
        conversation_key = str(conversation_id)
        try:
            latest_run, pending_approval = await repository.get_conversation_state(
                conversation_key,
            )
        except ChatNotFoundError as exc:
            raise _stable_http_error(exc) from exc
        plan_state: ConversationPlanState | None = None
        if services.durable_repository is not None:
            runs = await repository.list_runs(conversation_key)
            snapshot = await load_latest_conversation_plan(
                services.durable_repository,
                [run.session_id for run in runs],
            )
            if snapshot is not None:
                plan_state = ConversationPlanState.model_validate(
                    execution_plan_to_chat_view(snapshot),
                )
        return ConversationStateResponse(
            latest_run=latest_run,
            pending_approval=(
                _pending_approval_state(pending_approval)
                if pending_approval is not None
                else None
            ),
            patch_preview=await _patch_preview_state(services, pending_approval),
            plan=plan_state,
        )

    @router.post(
        "/conversations/{conversation_id}/messages",
        status_code=status.HTTP_202_ACCEPTED,
        response_model=None,
    )
    async def post_message(
        conversation_id: UUID,
        request: PostMessageRequest,
    ) -> dict[str, str] | JSONResponse:
        conversation_key = str(conversation_id)
        session_id = new_id()
        try:
            user_message, _run = await repository.begin_run(
                conversation_key,
                content=request.query.strip(),
                session_id=session_id,
            )
        except ChatNotFoundError as exc:
            raise _stable_http_error(exc) from exc
        except ChatConflictError as exc:
            raise _stable_http_error(exc) from exc
        except ValueError as exc:
            raise _validation_http_error("invalid message") from exc

        try:
            await supervisor.start(
                conversation_key,
                lambda: runner.run_turn(
                    conversation_key,
                    session_id,
                    user_message.message_id,
                    request.query.strip(),
                ),
            )
        except ChatConflictError:
            await repository.fail_run(session_id, "RunSupervisorConflict")
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={"detail": "conflict"},
            )

        return {"session_id": session_id}

    @router.post(
        "/conversations/{conversation_id}/runs/{session_id}/interrupt",
        response_model=RunRecord,
    )
    async def interrupt_run(conversation_id: UUID, session_id: UUID) -> RunRecord:
        conversation_key = str(conversation_id)
        session_key = str(session_id)
        try:
            await repository.get_conversation(conversation_key)
            run = await repository.get_run(session_key)
        except ChatNotFoundError as exc:
            raise _stable_http_error(exc) from exc
        if run.conversation_id != conversation_key:
            raise _stable_http_error(ChatConflictError("conflict"))
        if run.status not in {
            RunStatus.QUEUED,
            RunStatus.RUNNING,
            RunStatus.WAITING_APPROVAL,
        }:
            raise _stable_http_error(ChatConflictError("conflict"))

        pending_approval_id: str | None = None
        if run.status is RunStatus.WAITING_APPROVAL:
            _latest, pending = await repository.get_conversation_state(conversation_key)
            if pending is not None and pending.session_id == session_key:
                pending_approval_id = pending.approval_id

        await supervisor.cancel(conversation_key)
        await runner.interrupt_run(session_key)
        if pending_approval_id is not None:
            with suppress(ChatConflictError, ChatNotFoundError):
                await repository.invalidate_approval(pending_approval_id)
        try:
            return await repository.get_run(session_key)
        except ChatNotFoundError as exc:
            raise _stable_http_error(exc) from exc

    @router.get("/runs/{session_id}", response_model=RunRecord)
    async def get_run(session_id: UUID) -> RunRecord:
        try:
            return await repository.get_run(str(session_id))
        except ChatNotFoundError as exc:
            raise _stable_http_error(exc) from exc

    @router.post(
        "/approvals/{approval_id}/decision",
        response_model=ApprovalRequest,
    )
    async def decide_approval(
        approval_id: UUID,
        request: ApprovalDecisionRequest,
    ) -> ApprovalRequest:
        try:
            return await coordinator.resolve(str(approval_id), request.decision)
        except (ChatNotFoundError, ChatConflictError) as exc:
            raise _stable_http_error(exc) from exc

    @router.get("/conversations/{conversation_id}/events")
    async def conversation_events(
        request: Request,
        conversation_id: UUID,
    ) -> StreamingResponse:
        conversation_key = str(conversation_id)
        try:
            await repository.get_conversation(conversation_key)
        except ChatNotFoundError as exc:
            raise _stable_http_error(exc) from exc

        async def generate() -> AsyncIterator[str]:
            subscription = broker.subscribe(conversation_key)
            next_event: asyncio.Task[object] | None = None
            disconnect_logged = False
            try:
                yield ": connected\n\n"
                next_event = asyncio.create_task(anext(subscription))
                while not await request.is_disconnected():
                    done, _ = await asyncio.wait(
                        (next_event,),
                        timeout=keepalive_seconds,
                    )
                    if not done:
                        yield ": keepalive\n\n"
                        continue
                    try:
                        event = next_event.result()
                    except StopAsyncIteration:
                        break
                    assert isinstance(event, ChatEvent)
                    yield encode_chat_sse(event)
                    next_event = asyncio.create_task(anext(subscription))
                else:
                    log_sse_cancelled(request, "chat")
                    disconnect_logged = True
            except asyncio.CancelledError:
                if not disconnect_logged:
                    log_sse_cancelled(request, "chat")
                return
            except Exception as exc:
                log_sse_failed(exc, "chat")
                raise
            finally:
                if next_event is not None and not next_event.done():
                    next_event.cancel()
                    with suppress(asyncio.CancelledError):
                        await next_event
                await subscription.aclose()

        return StreamingResponse(generate(), media_type="text/event-stream")

    @router.get(
        "/conversations/{conversation_id}/runs/{session_id}/command-artifacts/{artifact_id}/pages",
    )
    async def get_command_output_page(
        conversation_id: UUID,
        session_id: UUID,
        artifact_id: str,
        stream: str = Query(...),
        start_line: int = 1,
        line_count: int = 50,
    ) -> dict[str, object]:
        from agent_foundations.command_output.access import (
            AccessError,
            CommandOutputAccessService,
            parse_selector,
        )

        store, _metadata = await _owned_artifact(
            services,
            str(conversation_id),
            str(session_id),
            artifact_id,
        )
        try:
            selector = parse_selector(
                {
                    "stream": stream,
                    "start_line": start_line,
                    "line_count": line_count,
                }
            )
            conversation = await repository.get_conversation(str(conversation_id))
            artifacts = services.command_artifact_repository
            from agent_foundations.command_output.repository import CommandArtifactRepository
            from agent_foundations.command_output.store import CommandArtifactStore

            if not isinstance(store, CommandArtifactStore) or not isinstance(
                artifacts,
                CommandArtifactRepository,
            ):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
            service = CommandOutputAccessService(store, artifacts)
            page = service.read(
                current_run_id=str(session_id),
                artifact_id=artifact_id,
                selector=selector,
                reason="ui sanitized page",
                project_root=Path(conversation.project_root),
                charge_budget=False,
                audit_decision="ui_page",
            )
        except AccessError as exc:
            status_code = (
                status.HTTP_404_NOT_FOUND
                if exc.code in {"ARTIFACT_SCOPE_DENIED", "ARTIFACT_NOT_READABLE"}
                else status.HTTP_400_BAD_REQUEST
            )
            raise HTTPException(status_code=status_code, detail=exc.code) from exc
        return page.model_dump(mode="json")

    @router.post(
        "/conversations/{conversation_id}/runs/{session_id}/command-artifacts/{artifact_id}/download-tickets",
        status_code=status.HTTP_201_CREATED,
    )
    async def create_command_output_download_ticket(
        request: Request,
        conversation_id: UUID,
        session_id: UUID,
        artifact_id: str,
    ) -> dict[str, str]:
        _require_local_user(request, require_origin=True)
        await _owned_artifact(services, str(conversation_id), str(session_id), artifact_id)
        from agent_foundations.command_output.access import CommandOutputDownloadTicketStore

        tickets = services.command_output_tickets
        if not isinstance(tickets, CommandOutputDownloadTicketStore):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
        ticket = tickets.issue(
            conversation_id=str(conversation_id),
            run_id=str(session_id),
            artifact_id=artifact_id,
        )
        return {"ticket": ticket.ticket_id}

    @router.get(
        "/conversations/{conversation_id}/runs/{session_id}/command-artifacts/{artifact_id}/raw",
    )
    async def download_command_output_raw(
        request: Request,
        conversation_id: UUID,
        session_id: UUID,
        artifact_id: str,
        ticket: str,
    ) -> Response:
        from agent_foundations.command_output.access import (
            AccessError,
            CommandOutputDownloadTicketStore,
        )
        from agent_foundations.command_output.store import CommandArtifactStore

        _require_local_user(request, require_origin=False)
        store, _metadata = await _owned_artifact(
            services,
            str(conversation_id),
            str(session_id),
            artifact_id,
        )
        tickets = services.command_output_tickets
        if not isinstance(store, CommandArtifactStore) or not isinstance(
            tickets,
            CommandOutputDownloadTicketStore,
        ):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
        try:
            tickets.consume(
                ticket,
                conversation_id=str(conversation_id),
                run_id=str(session_id),
                artifact_id=artifact_id,
            )
        except AccessError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=exc.code,
            ) from exc
        directory = store.directory_for(artifact_id)
        payload = (directory / "stdout").read_bytes() + b"\n" + (directory / "stderr").read_bytes()
        return Response(
            content=payload,
            media_type="application/octet-stream",
            headers={"Content-Disposition": 'attachment; filename="command-output.bin"'},
        )

    def _require_retention() -> ArtifactRetentionSweeper:
        from agent_foundations.command_output.repository import CommandArtifactRepository

        retention = services.retention
        artifacts = services.command_artifact_repository
        if retention is None or not isinstance(artifacts, CommandArtifactRepository):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
        return retention

    def _sync_sweep(retention: ArtifactRetentionSweeper) -> None:
        retention.sweep_expired()
        retention.sweep_pending_delete()

    def _sync_purge(run_id: str) -> list[str]:
        from agent_foundations.command_output.repository import CommandArtifactRepository

        retention = services.retention
        artifacts = services.command_artifact_repository
        if retention is None or not isinstance(artifacts, CommandArtifactRepository):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
        purged = list(artifacts.mark_pending_delete_for_run(run_id))
        retention.sweep_pending_delete()
        return purged

    @router.get("/artifacts/usage")
    async def get_artifact_usage(request: Request) -> dict[str, int]:
        from agent_foundations.command_output.repository import CommandArtifactRepository

        _require_local_user(request, require_origin=False)
        retention = _require_retention()
        artifacts = services.command_artifact_repository
        assert isinstance(artifacts, CommandArtifactRepository)
        used_bytes = await asyncio.to_thread(artifacts.used_bytes)
        return {
            "used_bytes": used_bytes,
            "capacity_bytes": retention.global_capacity_bytes,
            "retention_seconds": int(retention.retention_period.total_seconds()),
        }

    @router.post("/artifacts/sweep")
    async def post_artifact_sweep(request: Request) -> dict[str, bool]:
        _require_local_user(request, require_origin=True)
        retention = _require_retention()
        await asyncio.to_thread(_sync_sweep, retention)
        return {"ok": True}

    @router.post("/artifacts/runs/{run_id}/purge")
    async def post_artifact_purge(request: Request, run_id: UUID) -> dict[str, object]:
        _require_local_user(request, require_origin=True)
        _require_retention()
        purged = await asyncio.to_thread(_sync_purge, str(run_id))
        return {"ok": True, "purged_artifact_ids": purged}

    return router
