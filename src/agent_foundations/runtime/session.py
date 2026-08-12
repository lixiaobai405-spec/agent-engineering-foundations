from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from uuid import UUID, uuid4

from agent_foundations.domain.messages import Message


class SessionStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentSession:
    root: Path
    messages: list[Message] = field(default_factory=list)
    session_id: str = field(default_factory=lambda: str(uuid4()))
    status: SessionStatus = SessionStatus.CREATED

    def __post_init__(self) -> None:
        try:
            UUID(self.session_id)
        except ValueError as exc:
            raise ValueError(
                f"session_id must be a valid UUID: {self.session_id}",
            ) from exc
        resolved = self.root.resolve(strict=True)
        if not resolved.is_dir():
            raise ValueError(f"root is not a directory: {resolved}")
        self.root = resolved
