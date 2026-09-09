from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from agent_foundations.command_output.store import default_artifact_root, validate_artifact_root

DATA_ROOT_ENV = "AGENT_FOUNDATIONS_DATA_ROOT"
_LEFTOVER_RELATIVE = (
    Path(".agent-foundations") / "chat.sqlite3",
    Path(".agent-foundations") / "command-artifacts",
    Path("traces"),
)


@dataclass(frozen=True)
class ChatDataLayout:
    data_root: Path
    sqlite_path: Path
    command_output: Path
    controller: Path
    traces: Path


def default_data_root() -> Path:
    return default_artifact_root().parent


def validate_data_root(root: Path) -> Path:
    absolute = root if root.is_absolute() else root.resolve()
    return validate_artifact_root(absolute)


def resolve_data_root(
    *,
    explicit: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path:
    env_map = os.environ if environ is None else environ
    if explicit is not None:
        candidate = explicit
    else:
        raw = str(env_map.get(DATA_ROOT_ENV, "")).strip()
        candidate = Path(raw) if raw else default_data_root()
    return validate_data_root(candidate)


def chat_data_layout(data_root: Path) -> ChatDataLayout:
    root = validate_data_root(data_root)
    return ChatDataLayout(
        data_root=root,
        sqlite_path=root / "chat.sqlite3",
        command_output=root / "command-output",
        controller=root / "controller",
        traces=root / "traces",
    )


def leftover_legacy_paths(cwd: Path) -> tuple[Path, ...]:
    found: list[Path] = []
    for relative in _LEFTOVER_RELATIVE:
        candidate = cwd / relative
        if candidate.exists():
            found.append(candidate)
    return tuple(found)


def leftover_warning(legacy_paths: Sequence[Path], data_root: Path) -> str:
    listed = ", ".join(str(path) for path in legacy_paths)
    return (
        f"Leftover Chat data at {listed} is not used; "
        f"new data root is {data_root}. Not copied or moved."
    )
