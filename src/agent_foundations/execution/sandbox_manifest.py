from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import ConfigDict, ValidationError, field_validator, model_validator

from agent_foundations.domain._model import ValidatedCopyModel
from agent_foundations.tools.patch.models import DigestHex

SandboxProfile = Literal["python", "node"]
_IMAGE_TAG_RE = re.compile(r"^agent-foundations-sandbox-(python|node):phase2d$")
_REPO_DIGEST_RE = re.compile(
    r"^[a-z0-9]+(?:[._/-][a-z0-9]+)*@sha256:[a-f0-9]{64}$"
)
_IMAGE_ID_RE = re.compile(r"^sha256:[a-f0-9]{64}$")


class SandboxManifestMismatchError(RuntimeError):
    """Raised when runtime image provenance differs from the trusted manifest."""


class SandboxImageProvenance(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    profile: SandboxProfile
    image_tag: str
    base_repo_digest: str
    lockfile_sha256: DigestHex
    final_image_id: str
    final_repo_digest: str | None = None

    @field_validator("image_tag")
    @classmethod
    def _valid_image_tag(cls, value: str) -> str:
        if _IMAGE_TAG_RE.fullmatch(value) is None:
            raise ValueError("image_tag must be a fixed Task 17 profile tag")
        return value

    @field_validator("base_repo_digest")
    @classmethod
    def _valid_repo_digest(cls, value: str) -> str:
        if _REPO_DIGEST_RE.fullmatch(value) is None:
            raise ValueError("image provenance must use an immutable repository digest")
        return value

    @field_validator("final_repo_digest")
    @classmethod
    def _valid_optional_repo_digest(cls, value: str | None) -> str | None:
        if value is not None and _REPO_DIGEST_RE.fullmatch(value) is None:
            raise ValueError("final RepoDigest must use immutable repository digest syntax")
        return value

    @field_validator("final_image_id")
    @classmethod
    def _valid_image_id(cls, value: str) -> str:
        if _IMAGE_ID_RE.fullmatch(value) is None:
            raise ValueError("final_image_id must be a sha256 image ID")
        return value

    @model_validator(mode="after")
    def _profile_matches_tag(self) -> SandboxImageProvenance:
        expected = f"agent-foundations-sandbox-{self.profile}:phase2d"
        if self.image_tag != expected:
            raise ValueError("sandbox profile and image tag do not match")
        expected_repo = f"agent-foundations-sandbox-{self.profile}@sha256:"
        if self.final_repo_digest is not None and not self.final_repo_digest.startswith(
            expected_repo
        ):
            raise ValueError("sandbox profile and final RepoDigest do not match")
        return self


class SandboxManifest(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    python: SandboxImageProvenance
    node: SandboxImageProvenance

    @model_validator(mode="after")
    def _fixed_profiles(self) -> SandboxManifest:
        if self.python.profile != "python" or self.node.profile != "node":
            raise ValueError("sandbox manifest profiles must be python and node")
        return self

    @classmethod
    def from_path(cls, path: Path) -> SandboxManifest:
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise SandboxManifestMismatchError("sandbox manifest is unavailable") from exc
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SandboxManifestMismatchError("sandbox manifest is invalid") from exc
        try:
            return cls.model_validate(payload)
        except ValidationError as exc:
            raise SandboxManifestMismatchError("sandbox manifest is invalid") from exc

    @classmethod
    def load_pinned(cls, repo_root: Path) -> SandboxManifest:
        manifest = cls.from_path(repo_root / "docker" / "sandbox-manifest.phase2d.json")
        verify_lockfile_fingerprint(
            manifest.python,
            repo_root / "docker" / "agent-sandbox-python.requirements.lock",
        )
        verify_lockfile_fingerprint(
            manifest.node,
            repo_root / "package-lock.json",
        )
        return manifest

    def profile(self, profile: str) -> SandboxImageProvenance:
        if profile == "python":
            return self.python
        if profile == "node":
            return self.node
        raise SandboxManifestMismatchError(f"unknown sandbox profile: {profile}")

    def verify_runtime(
        self,
        profile: str,
        *,
        image_id: str,
        repo_digest: str | None,
    ) -> None:
        provenance = self.profile(profile)
        if image_id != provenance.final_image_id:
            raise SandboxManifestMismatchError("sandbox image ID mismatch")
        if provenance.final_repo_digest is not None and (
            repo_digest != provenance.final_repo_digest
        ):
            raise SandboxManifestMismatchError("sandbox RepoDigest mismatch")


def verify_lockfile_fingerprint(
    provenance: SandboxImageProvenance,
    lockfile: Path,
) -> None:
    try:
        digest = hashlib.sha256(lockfile.read_bytes()).hexdigest()
    except OSError as exc:
        raise SandboxManifestMismatchError("sandbox lockfile is unavailable") from exc
    if digest != provenance.lockfile_sha256:
        raise SandboxManifestMismatchError("sandbox lockfile fingerprint mismatch")
