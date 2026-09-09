from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from agent_foundations.domain.errors import PathPolicyViolationError
from agent_foundations.execution.backend import ExecutionBackend
from agent_foundations.execution.models import ExecutionRequest, ExecutionResult
from agent_foundations.runtime.redaction import Redactor
from agent_foundations.tools.filesystem.path_policy import PathPolicy
from agent_foundations.tools.git.models import (
    DEFAULT_DIFF_MAX_BYTES,
    DEFAULT_LOG_LIMIT,
    MAX_LOG_LIMIT,
    GitDiffResult,
    GitLogEntry,
    GitLogResult,
    GitStatusEntry,
    GitStatusResult,
)
from agent_foundations.tools.git.probe import (
    STATUS_L1_ARGV,
    VERSION_ARGV,
    build_diff_l1_argv,
    build_log_l1_argv,
    parse_git_version,
    should_use_legacy_argv,
)

STATUS_ARGV: tuple[str, ...] = (
    "git",
    "--no-pager",
    "--no-optional-locks",
    "status",
    "--porcelain=v1",
    "-z",
    "--untracked-files=all",
)

GIT_ISOLATED_ENV: tuple[tuple[str, str], ...] = (
    ("GIT_OPTIONAL_LOCKS", "0"),
    ("GIT_TERMINAL_PROMPT", "0"),
    ("GIT_CONFIG_NOSYSTEM", "1"),
    ("GIT_CONFIG_GLOBAL", "/opt/isolated-home/gitconfig"),
    ("HOME", "/opt/isolated-home"),
    ("XDG_CONFIG_HOME", "/opt/isolated-xdg"),
    ("GIT_CONFIG_COUNT", "2"),
    ("GIT_CONFIG_KEY_0", "safe.directory"),
    ("GIT_CONFIG_VALUE_0", "*"),
    ("GIT_CONFIG_KEY_1", "core.autocrlf"),
    ("GIT_CONFIG_VALUE_1", "true"),
)


class GitReadError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def build_diff_argv(*, path: str | None, staged: bool) -> tuple[str, ...]:
    argv: tuple[str, ...] = (
        "git",
        "--no-pager",
        "--no-optional-locks",
        "diff",
        "--no-ext-diff",
        "--no-textconv",
        "--no-color",
    )
    if staged:
        argv = (*argv, "--cached")
    if path is not None:
        argv = (*argv, "--", path)
    return argv


def build_log_argv(limit: int) -> tuple[str, ...]:
    return (
        "git",
        "--no-pager",
        "--no-optional-locks",
        "log",
        "--no-ext-diff",
        "--no-textconv",
        f"--max-count={limit}",
        "--pretty=format:%H%x09%s",
    )


def parse_status_z(payload: bytes) -> GitStatusResult:
    entries: list[GitStatusEntry] = []
    parts = payload.split(b"\0")
    index = 0
    while index < len(parts):
        raw = parts[index]
        if not raw:
            index += 1
            continue
        text = raw.decode("utf-8", "replace")
        if len(text) < 3:
            index += 1
            continue
        index_status = text[0]
        worktree_status = text[1]
        path = text[3:]
        if index_status in {"R", "C"}:
            index += 1
            if index < len(parts) and parts[index]:
                path = parts[index].decode("utf-8", "replace")
        entries.append(
            GitStatusEntry(
                path=path,
                index_status=index_status,
                worktree_status=worktree_status,
            )
        )
        index += 1
    untracked = tuple(
        entry.path
        for entry in entries
        if entry.index_status == "?" and entry.worktree_status == "?"
    )
    staged = tuple(
        entry.path
        for entry in entries
        if entry.index_status not in {" ", "?", "!"}
    )
    return GitStatusResult(entries=tuple(entries), untracked=untracked, staged=staged)


def parse_log(payload: bytes) -> GitLogResult:
    entries: list[GitLogEntry] = []
    text = payload.decode("utf-8", "replace")
    for line in text.splitlines():
        if not line.strip():
            continue
        commit, separator, subject = line.partition("\t")
        if not separator:
            continue
        entries.append(GitLogEntry(commit=commit, subject=subject))
    return GitLogResult(entries=tuple(entries))


class GitReadService:
    def __init__(
        self,
        workspace: Path,
        backend: ExecutionBackend,
        policy: PathPolicy,
        redactor: Redactor,
    ) -> None:
        self._workspace = workspace
        self._backend = backend
        self._policy = policy
        self._redactor = redactor
        self._probe_done = False
        self._probe_version: tuple[int, int, int] | None = None
        self._probe_error: GitReadError | None = None

    async def status(self) -> GitStatusResult:
        stdout = await self._run_with_fallback(
            STATUS_ARGV,
            STATUS_L1_ARGV,
            max_output_bytes=256_000,
        )
        return parse_status_z(stdout)

    async def diff(
        self,
        path: str | None = None,
        staged: bool = False,
        max_bytes: int = DEFAULT_DIFF_MAX_BYTES,
    ) -> GitDiffResult:
        if max_bytes < 1 or max_bytes > DEFAULT_DIFF_MAX_BYTES:
            raise GitReadError("SELECTOR_INVALID", "max_bytes must be between 1 and 200000")
        relative: str | None = None
        if path is not None:
            relative = self._require_regular_file(path)
        stdout = await self._run_with_fallback(
            build_diff_argv(path=relative, staged=staged),
            build_diff_l1_argv(path=relative, staged=staged),
            max_output_bytes=max_bytes,
        )
        truncated = len(stdout) >= max_bytes
        clipped = stdout[:max_bytes]
        patch = self._redactor.redact(clipped.decode("utf-8", "replace"))
        if not isinstance(patch, str):
            patch = str(patch)
        return GitDiffResult(
            path=relative,
            staged=staged,
            patch=patch,
            truncated=truncated,
            byte_count=len(clipped),
        )

    async def log(self, limit: int = DEFAULT_LOG_LIMIT) -> GitLogResult:
        if limit < 1 or limit > MAX_LOG_LIMIT:
            raise GitReadError("SELECTOR_INVALID", "limit must be between 1 and 100")
        stdout = await self._run_with_fallback(
            build_log_argv(limit),
            build_log_l1_argv(limit),
            max_output_bytes=256_000,
        )
        result = parse_log(stdout)
        redacted = tuple(
            GitLogEntry(
                commit=entry.commit,
                subject=str(self._redactor.redact(entry.subject)),
            )
            for entry in result.entries
        )
        return GitLogResult(entries=redacted)

    def _require_regular_file(self, relative_path: str) -> str:
        requested = Path(relative_path)
        if requested.is_absolute() or requested.drive:
            raise GitReadError("PATH_DENIED", "path must be project-relative")
        unresolved = self._workspace / requested
        try:
            if unresolved.is_symlink():
                raise GitReadError("PATH_DENIED", "symlinks are blocked")
        except OSError as exc:
            raise GitReadError("PATH_DENIED", "path cannot be inspected") from exc
        try:
            authorized = self._policy.authorize(relative_path)
        except PathPolicyViolationError as exc:
            message = str(exc).casefold()
            code = "SENSITIVE_PATH" if "sensitive" in message else "PATH_DENIED"
            raise GitReadError(code, str(exc)) from exc
        if authorized.is_dir() or not authorized.is_file() or authorized.is_symlink():
            raise GitReadError("PATH_DENIED", "git_diff path must be a regular file")
        return self._policy.display_path(authorized)

    async def _run_with_fallback(
        self,
        preferred: tuple[str, ...],
        fallback: tuple[str, ...],
        *,
        max_output_bytes: int,
    ) -> bytes:
        version = await self._ensure_version()
        if should_use_legacy_argv(version):
            return await self._run(fallback, max_output_bytes=max_output_bytes)
        try:
            return await self._run(preferred, max_output_bytes=max_output_bytes)
        except GitReadError as exc:
            if exc.code != "GIT_USAGE_ERROR":
                raise
            return await self._run(fallback, max_output_bytes=max_output_bytes)

    async def _ensure_version(self) -> tuple[int, int, int] | None:
        if self._probe_done:
            if self._probe_error is not None:
                raise GitReadError(self._probe_error.code, str(self._probe_error))
            return self._probe_version
        result = await self._execute(VERSION_ARGV, max_output_bytes=4096)
        self._probe_done = True
        if result.timed_out:
            error = GitReadError("GIT_TIMEOUT", "git execution timed out")
            self._probe_error = error
            raise error
        if result.cancelled:
            error = GitReadError("GIT_CANCELLED", "git execution was cancelled")
            self._probe_error = error
            raise error
        if result.exit_code != 0:
            stderr_text = result.stderr.decode("utf-8", "replace").strip()[:200]
            stdout_text = result.stdout.decode("utf-8", "replace").strip()[:200]
            detail = stderr_text or stdout_text
            error = GitReadError("GIT_FAILED", detail or "git command failed")
            self._probe_error = error
            raise error
        self._probe_version = parse_git_version(result.stdout)
        return self._probe_version

    async def _execute(
        self, argv: tuple[str, ...], *, max_output_bytes: int
    ) -> ExecutionResult:
        request = ExecutionRequest(
            execution_id=str(uuid4()),
            run_id=str(uuid4()),
            capability_id=str(uuid4()),
            argv=argv,
            cwd=".",
            mount_mode="read_only",
            sandbox_profile="legacy_patch",
            timeout_seconds=30,
            max_output_bytes=max_output_bytes,
            env=GIT_ISOLATED_ENV,
        )
        return await self._backend.execute(request)

    async def _run(self, argv: tuple[str, ...], *, max_output_bytes: int) -> bytes:
        result = await self._execute(argv, max_output_bytes=max_output_bytes)
        if result.timed_out:
            raise GitReadError("GIT_TIMEOUT", "git execution timed out")
        if result.cancelled:
            raise GitReadError("GIT_CANCELLED", "git execution was cancelled")
        if result.exit_code not in {0, 1}:
            stderr_text = result.stderr.decode("utf-8", "replace").strip()[:200]
            stdout_text = result.stdout.decode("utf-8", "replace").strip()[:200]
            combined = f"{stderr_text}\n{stdout_text}".casefold()
            detail = stderr_text or stdout_text
            if "not a git repository" in combined:
                raise GitReadError("NOT_A_REPOSITORY", detail or "not a git repository")
            if "unknown option" in combined or result.exit_code == 129:
                raise GitReadError("GIT_USAGE_ERROR", detail or "git usage error")
            raise GitReadError("GIT_FAILED", detail or "git command failed")
        return result.stdout
