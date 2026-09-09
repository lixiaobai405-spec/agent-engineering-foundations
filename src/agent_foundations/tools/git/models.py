from __future__ import annotations

from pydantic import ConfigDict, Field

from agent_foundations.domain._model import ValidatedCopyModel

DEFAULT_DIFF_MAX_BYTES = 200000
DEFAULT_LOG_LIMIT = 20
MAX_LOG_LIMIT = 100


class GitStatusEntry(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    index_status: str = Field(min_length=1, max_length=1)
    worktree_status: str = Field(min_length=1, max_length=1)


class GitStatusResult(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entries: tuple[GitStatusEntry, ...]
    untracked: tuple[str, ...]
    staged: tuple[str, ...]


class GitDiffResult(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str | None
    staged: bool
    patch: str
    truncated: bool
    byte_count: int = Field(ge=0)


class GitLogEntry(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    commit: str = Field(min_length=1)
    subject: str


class GitLogResult(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entries: tuple[GitLogEntry, ...]
