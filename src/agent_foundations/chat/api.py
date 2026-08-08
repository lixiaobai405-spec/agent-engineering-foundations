from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent_foundations.chat.approvals import ApprovalCoordinator
from agent_foundations.chat.errors import ChatConflictError, ChatNotFoundError
from agent_foundations.chat.events import ChatEventBroker, encode_chat_sse
from agent_foundations.chat.models import (
    AccessOperation,
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
    ChatEvent,
    ChatMessage,
    Conversation,
    PermissionMode,
    RunRecord,
    new_id,
)
from agent_foundations.chat.repository import ConversationRepository
from agent_foundations.chat.runner import ConversationRunner
from agent_foundations.chat.supervisor import RunSupervisor


@dataclass(frozen=True)
class ChatServices:
    repository: ConversationRepository
    broker: ChatEventBroker
    runner: ConversationRunner
    supervisor: RunSupervisor
    coordinator: ApprovalCoordinator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateConversationRequest(_StrictModel):
    title: str = Field(min_length=1, max_length=120)
    project_root: str
    permission_mode: PermissionMode

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
    operation: AccessOperation
    scope: str
    status: ApprovalStatus
    requested_at: str


class ConversationStateResponse(_StrictModel):
    latest_run: RunRecord | None
    pending_approval: PendingApprovalState | None


def _pending_approval_state(
    approval: ApprovalRequest,
) -> PendingApprovalState:
    return PendingApprovalState(
        approval_id=approval.approval_id,
        conversation_id=approval.conversation_id,
        session_id=approval.session_id,
        tool_call_id=approval.tool_call_id,
        tool_name=approval.tool_name,
        canonical_path=approval.canonical_path,
        operation=approval.operation,
        scope="external_exact_path",
        status=ApprovalStatus.PENDING,
        requested_at=approval.requested_at.isoformat(),
    )


def _stable_http_error(exc: ChatNotFoundError | ChatConflictError) -> HTTPException:
    if isinstance(exc, ChatNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="conflict")


def _validation_http_error(message: str) -> HTTPException:
    return HTTPException(status_code=422, detail=message)


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
        return ConversationStateResponse(
            latest_run=latest_run,
            pending_approval=(
                _pending_approval_state(pending_approval)
                if pending_approval is not None
                else None
            ),
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
            finally:
                if next_event is not None and not next_event.done():
                    next_event.cancel()
                    with suppress(asyncio.CancelledError):
                        await next_event
                await subscription.aclose()

        return StreamingResponse(generate(), media_type="text/event-stream")

    return router
