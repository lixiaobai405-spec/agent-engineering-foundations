from __future__ import annotations

import re
from typing import Literal

from pydantic import ConfigDict, Field, field_validator

from agent_foundations.domain._model import ValidatedCopyModel

ContextSourceKind = Literal["file", "symbol", "import"]
_KIND_PREFIX = {"file": "file:", "symbol": "symbol:", "import": "import:"}


def source_relative_path(source_id: str) -> str:
    kind, separator, remainder = source_id.partition(":")
    if not separator or kind not in _KIND_PREFIX:
        raise ValueError("source_id must use a file/symbol/import prefix")
    if kind == "file":
        return remainder
    relative, sep, _name = remainder.rpartition(":")
    if not sep:
        raise ValueError("source_id is missing a project-relative path")
    return relative


def _reject_host_path(value: str) -> None:
    if "\\" in value:
        raise ValueError("absolute host paths are blocked")
    candidate = value
    for prefix in ("file:", "symbol:", "import:"):
        if value.startswith(prefix):
            candidate = value[len(prefix) :]
            break
    if candidate.startswith("/") or (len(candidate) >= 2 and candidate[1] == ":"):
        raise ValueError("absolute host paths are blocked")


class ContextSource(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str
    kind: ContextSourceKind
    content: str
    priority: int
    provenance: str
    fingerprint: str = Field(min_length=64, max_length=64)

    @field_validator("fingerprint")
    @classmethod
    def _fingerprint_hex(cls, value: str) -> str:
        if re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("fingerprint must be a SHA-256 hex digest")
        return value

    @field_validator("source_id")
    @classmethod
    def _stable_source_id(cls, value: str) -> str:
        _reject_host_path(value)
        kind, separator, remainder = value.partition(":")
        if not separator or kind not in _KIND_PREFIX:
            raise ValueError("source_id must start with file:, symbol:, or import:")
        if not remainder or ".." in remainder.split("/"):
            raise ValueError("source_id must be project-relative")
        if kind != "file" and ":" not in remainder:
            raise ValueError("symbol/import source_id must include a name")
        return value

    @field_validator("provenance")
    @classmethod
    def _safe_provenance(cls, value: str) -> str:
        _reject_host_path(value)
        return value

    @field_validator("kind")
    @classmethod
    def _kind_matches_id(cls, value: ContextSourceKind, info: object) -> ContextSourceKind:
        source_id = getattr(info, "data", {}).get("source_id")
        if isinstance(source_id, str) and not source_id.startswith(_KIND_PREFIX[value]):
            raise ValueError("kind must match source_id prefix")
        return value
