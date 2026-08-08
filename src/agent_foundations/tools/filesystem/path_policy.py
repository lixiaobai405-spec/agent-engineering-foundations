from pathlib import Path

from agent_foundations.domain.errors import PathPolicyViolationError


class PathPolicy:
    """Authorize project-relative paths in a stable, locally trusted workspace.

    The returned path should be used immediately. This policy does not claim to
    prevent an external process from replacing filesystem entries after
    authorization.
    """

    _blocked_parts = frozenset({".git", ".ssh", "credentials", "secrets"})
    _blocked_names = frozenset(
        {
            ".env",
            ".envrc",
            ".git-credentials",
            ".netrc",
            ".npmrc",
            ".pypirc",
            "cookies.json",
            "id_ed25519",
            "id_rsa",
        }
    )
    _blocked_suffixes = frozenset({".key", ".pem", ".p12", ".pfx"})
    _blocked_prefixes = ("credentials.", "secrets.")
    _windows_forbidden_chars = frozenset('<>"|?*')
    _windows_reserved_stems = frozenset(
        {
            "aux",
            "clock$",
            "con",
            "conin$",
            "conout$",
            "nul",
            "prn",
            *(f"com{number}" for number in range(1, 10)),
            *(f"lpt{number}" for number in range(1, 10)),
        }
    )

    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError(f"project root is not a directory: {self.root}")

    def authorize(self, relative_path: str, *, must_exist: bool = True) -> Path:
        try:
            requested = Path(relative_path)
        except (TypeError, ValueError) as exc:
            raise PathPolicyViolationError(
                f"invalid path syntax is blocked: {relative_path}"
            ) from exc
        if requested.is_absolute() or requested.drive:
            raise PathPolicyViolationError("path must be relative to the project root")
        self._validate_components(requested, relative_path)
        if self._is_sensitive(requested):
            raise PathPolicyViolationError(f"sensitive path is blocked: {relative_path}")

        try:
            candidate = (self.root / requested).resolve(strict=must_exist)
        except (OSError, ValueError) as exc:
            raise PathPolicyViolationError(
                f"path cannot be resolved: {relative_path}"
            ) from exc
        if not candidate.is_relative_to(self.root):
            raise PathPolicyViolationError(f"path escapes project root: {relative_path}")
        relative_resolved = candidate.relative_to(self.root)
        if self._is_sensitive(relative_resolved):
            raise PathPolicyViolationError(f"resolved path is sensitive: {relative_path}")
        return candidate

    @classmethod
    def resolve_external_read_target(cls, value: str) -> Path:
        """Resolve a safe local absolute read target; this grants no access."""
        normalized = value.replace("/", "\\")
        if normalized.startswith(("\\\\?\\", "\\\\.\\")):
            raise PathPolicyViolationError("device namespace paths are blocked")
        if normalized.startswith("\\\\"):
            raise PathPolicyViolationError("network paths are blocked")
        try:
            requested = Path(value)
        except (TypeError, ValueError) as exc:
            raise PathPolicyViolationError("invalid absolute path syntax") from exc
        if not requested.is_absolute():
            raise PathPolicyViolationError("external read target must be absolute")

        unresolved_parts = cls._parts_without_anchor(requested)
        unresolved = Path(*unresolved_parts)
        cls._validate_components(unresolved, value)
        if cls._is_sensitive(unresolved):
            raise PathPolicyViolationError("sensitive external path is blocked")

        try:
            resolved = requested.resolve(strict=True)
        except (OSError, ValueError) as exc:
            raise PathPolicyViolationError("external read target cannot be resolved") from exc
        resolved_relative = Path(*cls._parts_without_anchor(resolved))
        cls._validate_components(resolved_relative, str(resolved))
        if cls._is_sensitive(resolved_relative):
            raise PathPolicyViolationError("resolved external path is sensitive")
        if not resolved.is_file() and not resolved.is_dir():
            raise PathPolicyViolationError(
                "external read target must be a file or directory",
            )
        return resolved

    def display_path(self, path: Path) -> str:
        try:
            resolved = path.resolve(strict=True)
        except (OSError, ValueError) as exc:
            raise PathPolicyViolationError("path cannot be resolved") from exc
        try:
            relative = resolved.relative_to(self.root)
        except ValueError as exc:
            raise PathPolicyViolationError("path escapes project root") from exc
        if self._is_sensitive(relative):
            raise PathPolicyViolationError("resolved path is sensitive")
        return relative.as_posix() or "."

    @classmethod
    def _validate_components(cls, path: Path, original: str) -> None:
        for part in path.parts:
            if ":" in part:
                raise PathPolicyViolationError(
                    f"alternate path syntax is blocked: {original}"
                )
            if any(
                ord(character) < 32 or character in cls._windows_forbidden_chars
                for character in part
            ):
                raise PathPolicyViolationError(
                    f"invalid path syntax is blocked: {original}"
                )

            normalized = cls._normalize_component(part)
            stem = normalized.partition(".")[0]
            if stem in cls._windows_reserved_stems:
                raise PathPolicyViolationError(
                    f"reserved device path is blocked: {original}"
                )

    @staticmethod
    def _normalize_component(part: str) -> str:
        return part.rstrip(" .").casefold()

    @staticmethod
    def _parts_without_anchor(path: Path) -> tuple[str, ...]:
        parts = path.parts
        if path.anchor and parts:
            return parts[1:]
        return parts

    @classmethod
    def _is_sensitive(cls, path: Path) -> bool:
        return any(cls._is_sensitive_component(part) for part in path.parts)

    @classmethod
    def _is_sensitive_component(cls, part: str) -> bool:
        normalized = cls._normalize_component(part)
        suffix = Path(normalized).suffix.casefold()
        return (
            normalized in cls._blocked_parts
            or normalized in cls._blocked_names
            or normalized.startswith(".env.")
            or normalized.startswith(cls._blocked_prefixes)
            or suffix in cls._blocked_suffixes
        )
