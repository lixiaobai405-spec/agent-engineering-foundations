import unicodedata
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID, uuid4

from pydantic import (
    AfterValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    PlainValidator,
    WithJsonSchema,
    field_validator,
)

from agent_foundations.domain._freeze import FrozenJSON, to_json_value
from agent_foundations.domain._model import ValidatedCopyModel


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid4())


def _valid_uuid(value: str) -> str:
    UUID(value)
    return value


def _utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _relative_trace_path(value: str) -> str:
    if ":" in value or any(unicodedata.category(character) == "Cc" for character in value):
        raise ValueError("trace_path must be a relative trace path")
    path = Path(value)
    if not path.parts or path.drive or path.is_absolute() or ".." in path.parts:
        raise ValueError("trace_path must be a relative trace path")
    return path.as_posix()


UUIDString = Annotated[str, AfterValidator(_valid_uuid)]
UTCDateTime = Annotated[datetime, AfterValidator(_utc_datetime)]
RelativeTracePath = Annotated[str, AfterValidator(_relative_trace_path)]


def _freeze_data(value: Any) -> FrozenJSON:
    if isinstance(value, FrozenJSON):
        return value
    if not isinstance(value, dict):
        raise ValueError("chat event data must be an object")
    return FrozenJSON(value)


class PermissionMode(StrEnum):
    PROJECT_READ_ONLY = "PROJECT_READ_ONLY"
    ASK_FOR_ACCESS = "ASK_FOR_ACCESS"


class ResourceKind(StrEnum):
    FILESYSTEM = "filesystem"


class AccessOperation(StrEnum):
    READ = "read"


class AccessScope(StrEnum):
    PROJECT = "project"
    EXTERNAL_EXACT_PATH = "external_exact_path"


class PolicyDecision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"

    @classmethod
    def active(cls) -> set["RunStatus"]:
        return {cls.QUEUED, cls.RUNNING, cls.WAITING_APPROVAL}


class ToolActivityStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"

    @classmethod
    def terminal(cls) -> set["ToolActivityStatus"]:
        return {cls.COMPLETED, cls.FAILED, cls.INTERRUPTED}


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    INVALIDATED = "invalidated"


class ApprovalDecision(StrEnum):
    APPROVE = "approve"
    DENY = "deny"


class ChatEventType(StrEnum):
    RUN_STARTED = "run.started"
    MODEL_REQUESTED = "model.requested"
    TOOL_REQUESTED = "tool.requested"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_RESOLVED = "approval.resolved"
    ASSISTANT_MESSAGE_COMPLETED = "assistant.message.completed"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"


class ChatModel(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True)


class AccessDecision(ChatModel):
    resource: ResourceKind = ResourceKind.FILESYSTEM
    operation: AccessOperation = AccessOperation.READ
    scope: AccessScope
    decision: PolicyDecision
    canonical_path: str


class Conversation(ChatModel):
    conversation_id: UUIDString = Field(default_factory=new_id)
    title: str = Field(min_length=1, max_length=120)
    project_root: str
    permission_mode: PermissionMode
    created_at: UTCDateTime = Field(default_factory=utc_now)
    updated_at: UTCDateTime = Field(default_factory=utc_now)

    @field_validator("project_root")
    @classmethod
    def existing_root(cls, value: str) -> str:
        try:
            path = Path(value).resolve(strict=True)
        except (OSError, ValueError) as exc:
            raise ValueError("project_root must be an existing directory") from exc
        if not path.is_dir():
            raise ValueError("project_root must be an existing directory")
        return str(path)


class ChatMessage(ChatModel):
    message_id: UUIDString = Field(default_factory=new_id)
    conversation_id: UUIDString
    role: MessageRole
    content: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    created_at: UTCDateTime = Field(default_factory=utc_now)


class RunRecord(ChatModel):
    session_id: UUIDString = Field(default_factory=new_id)
    conversation_id: UUIDString
    user_message_id: UUIDString
    trace_path: RelativeTracePath
    assistant_message_id: UUIDString | None = None
    status: RunStatus = RunStatus.QUEUED
    error_code: str | None = None
    created_at: UTCDateTime = Field(default_factory=utc_now)
    started_at: UTCDateTime | None = None
    finished_at: UTCDateTime | None = None


class ChatToolActivity(ChatModel):
    conversation_id: UUIDString
    session_id: UUIDString
    tool_call_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    status: ToolActivityStatus
    arguments_summary: str | None = Field(default=None, max_length=240)
    result_summary: str | None = Field(default=None, max_length=240)
    started_at: UTCDateTime
    finished_at: UTCDateTime | None = None
    last_event_id: UUIDString


class ApprovalRequest(ChatModel):
    approval_id: UUIDString = Field(default_factory=new_id)
    conversation_id: UUIDString
    session_id: UUIDString
    tool_call_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    canonical_path: str
    operation: AccessOperation = AccessOperation.READ
    status: ApprovalStatus = ApprovalStatus.PENDING
    requested_at: UTCDateTime = Field(default_factory=utc_now)
    decided_at: UTCDateTime | None = None


class ChatEvent(ChatModel):
    event_id: UUIDString = Field(default_factory=new_id)
    conversation_id: UUIDString
    session_id: UUIDString
    type: ChatEventType
    occurred_at: UTCDateTime = Field(default_factory=utc_now)
    data: Annotated[
        Mapping[str, Any],
        PlainValidator(_freeze_data),
        PlainSerializer(to_json_value, return_type=dict[str, Any]),
        WithJsonSchema({"type": "object"}),
    ] = Field(default_factory=lambda: FrozenJSON({}))
