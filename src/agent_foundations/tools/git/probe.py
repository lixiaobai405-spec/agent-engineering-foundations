"""Git version probe and predefined weaker argv fallbacks."""

from __future__ import annotations

import re

VERSION_ARGV: tuple[str, ...] = ("git", "--version")
LEGACY_GIT_VERSION: tuple[int, int, int] = (2, 15, 0)

STATUS_L1_ARGV: tuple[str, ...] = (
    "git",
    "--no-pager",
    "status",
    "--porcelain",
    "-z",
)

_VERSION_RE = re.compile(r"git version (\d+)\.(\d+)(?:\.(\d+))?")


def parse_git_version(stdout: bytes) -> tuple[int, int, int] | None:
    text = stdout.decode("utf-8", "replace")
    match = _VERSION_RE.search(text)
    if match is None:
        return None
    major = int(match.group(1))
    minor = int(match.group(2))
    patch = int(match.group(3) or "0")
    return (major, minor, patch)


def should_use_legacy_argv(version: tuple[int, int, int] | None) -> bool:
    return version is not None and version < LEGACY_GIT_VERSION


def build_diff_l1_argv(*, path: str | None, staged: bool) -> tuple[str, ...]:
    argv: tuple[str, ...] = ("git", "--no-pager", "diff", "--no-color")
    if staged:
        argv = (*argv, "--cached")
    if path is not None:
        argv = (*argv, "--", path)
    return argv


def build_log_l1_argv(limit: int) -> tuple[str, ...]:
    return (
        "git",
        "--no-pager",
        "log",
        f"--max-count={limit}",
        "--pretty=format:%H%x09%s",
    )
