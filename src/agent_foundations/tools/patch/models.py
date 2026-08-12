from __future__ import annotations

import hashlib
import json
import os
import re
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Annotated, Any

from pydantic import AfterValidator, ConfigDict, Field, field_validator

from agent_foundations.domain._model import ValidatedCopyModel

_DIGEST_RE = re.compile(r"^[a-f0-9]{64}$")


def _valid_digest(value: str) -> str:
    if not _DIGEST_RE.fullmatch(value):
        raise ValueError("digest must be 64 lowercase hex characters")
    return value


DigestHex = Annotated[str, AfterValidator(_valid_digest)]


class PatchOperation(StrEnum):
    MODIFY = "modify"
    CREATE = "create"


class PatchLineKind(StrEnum):
    CONTEXT = "context"
    REMOVE = "remove"
    ADD = "add"


class PatchLimits(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_patch_bytes: int = Field(default=256000, ge=1)
    max_files: int = Field(default=32, ge=1)
    max_hunks: int = Field(default=256, ge=1)
    max_file_bytes: int = Field(default=1_000_000, ge=1)


class PatchLine(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: PatchLineKind
    text: str
    missing_newline: bool = False


class PatchHunk(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    old_start: int = Field(ge=0)
    old_count: int = Field(ge=0)
    new_start: int = Field(ge=0)
    new_count: int = Field(ge=0)
    lines: tuple[PatchLine, ...]


class PatchFile(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    operation: PatchOperation
    baseline_sha256: DigestHex | None = None
    hunks: tuple[PatchHunk, ...]
    old_path: str | None = None
    add_line_count: int = Field(ge=0)
    remove_line_count: int = Field(ge=0)
    hunk_count: int = Field(ge=1)

    @field_validator("path", "old_path")
    @classmethod
    def validate_relative_posix(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value or value.strip() != value:
            raise ValueError("path must not be blank or padded")
        if "\\" in value or PurePosixPath(value).is_absolute():
            raise ValueError("path must be relative POSIX")
        return value


class ValidatedPatch(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    patch_id: DigestHex
    project_root_fingerprint: DigestHex
    files: tuple[PatchFile, ...] = Field(min_length=1)


class BaselineEntry(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    sha256: DigestHex | None = None


def canonical_json_dumps(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def compute_project_root_fingerprint(root: Path) -> str:
    resolved = root.resolve(strict=True)
    normalized = resolved.as_posix()
    if os.name == "nt":
        normalized = normalized.casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def patch_identity_payload(
    project_root_fingerprint: str,
    files: tuple[PatchFile, ...],
) -> dict[str, Any]:
    return {
        "project_root_fingerprint": project_root_fingerprint,
        "files": [file.model_dump(mode="json") for file in files],
    }


def compute_patch_id(
    project_root_fingerprint: str,
    files: tuple[PatchFile, ...],
) -> str:
    payload = patch_identity_payload(project_root_fingerprint, files)
    digest_input = canonical_json_dumps(payload)
    return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()


def build_validated_patch(
    project_root_fingerprint: str,
    files: tuple[PatchFile, ...],
) -> ValidatedPatch:
    patch_id = compute_patch_id(project_root_fingerprint, files)
    return ValidatedPatch(
        patch_id=patch_id,
        project_root_fingerprint=project_root_fingerprint,
        files=files,
    )
