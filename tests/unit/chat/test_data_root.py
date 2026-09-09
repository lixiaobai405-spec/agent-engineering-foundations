from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from typer.testing import CliRunner

from agent_foundations.cli import main
from agent_foundations.command_output.store import (
    ArtifactRootError,
    CommandArtifactStore,
    default_artifact_root,
)


def _data_root_api() -> Any:
    spec = importlib.util.find_spec("agent_foundations.chat.data_root")
    assert spec is not None, "chat data_root is missing"
    from agent_foundations.chat.data_root import (
        DATA_ROOT_ENV,
        chat_data_layout,
        default_data_root,
        leftover_legacy_paths,
        leftover_warning,
        resolve_data_root,
    )

    return (
        DATA_ROOT_ENV,
        default_data_root,
        resolve_data_root,
        chat_data_layout,
        leftover_legacy_paths,
        leftover_warning,
    )


def test_default_data_root_is_artifact_parent_not_drive_literal() -> None:
    (
        _env,
        default_data_root,
        _resolve,
        _layout,
        _leftover,
        _warning,
    ) = _data_root_api()
    root = default_data_root()
    assert root == default_artifact_root().parent
    assert root.is_absolute()
    assert "AgentFoundations" in root.parts
    assert root.name == "AgentFoundations"
    rendered = str(root)
    assert "D:\\AgentFoundationsData" not in rendered
    assert "D:/AgentFoundationsData" not in rendered


def test_explicit_data_root_overrides_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (
        env_name,
        _default,
        resolve_data_root,
        _layout,
        _leftover,
        _warning,
    ) = _data_root_api()
    env_root = tmp_path / "from-env"
    cli_root = tmp_path / "from-cli"
    env_root.mkdir()
    cli_root.mkdir()
    monkeypatch.setenv(env_name, str(env_root))
    resolved = resolve_data_root(explicit=cli_root)
    assert resolved == cli_root.resolve()


def test_env_data_root_overrides_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (
        env_name,
        default_data_root,
        resolve_data_root,
        _layout,
        _leftover,
        _warning,
    ) = _data_root_api()
    env_root = tmp_path / "from-env"
    env_root.mkdir()
    monkeypatch.setenv(env_name, str(env_root))
    resolved = resolve_data_root(explicit=None)
    assert resolved == env_root.resolve()
    assert resolved != default_data_root()


def test_data_root_inside_git_worktree_raises(tmp_path: Path) -> None:
    (
        _env,
        _default,
        resolve_data_root,
        _layout,
        _leftover,
        _warning,
    ) = _data_root_api()
    repo = tmp_path / "repo"
    nested = repo / "nested-data"
    nested.mkdir(parents=True)
    (repo / ".git").mkdir()
    with pytest.raises(ArtifactRootError):
        resolve_data_root(explicit=nested)


def test_chat_data_layout_uses_command_output_not_command_artifacts(tmp_path: Path) -> None:
    (
        _env,
        _default,
        _resolve,
        chat_data_layout,
        _leftover,
        _warning,
    ) = _data_root_api()
    layout = chat_data_layout(tmp_path)
    assert layout.data_root == tmp_path.resolve()
    assert layout.sqlite_path == tmp_path.resolve() / "chat.sqlite3"
    assert layout.command_output == tmp_path.resolve() / "command-output"
    assert layout.controller == tmp_path.resolve() / "controller"
    assert layout.traces == tmp_path.resolve() / "traces"
    assert layout.command_output.name == "command-output"
    assert "command-artifacts" not in str(layout.command_output)


def test_build_chat_services_signature_is_data_root_only() -> None:
    params = list(inspect.signature(main.build_chat_services).parameters)
    assert params == ["data_root"]


def test_build_chat_services_source_has_no_command_artifacts_disk_path() -> None:
    source = inspect.getsource(main.build_chat_services)
    assert "command-artifacts" not in source
    assert "command-output" in source


def test_build_chat_services_layout_under_tmp_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_API_KEY", "test-placeholder")
    monkeypatch.setenv("AGENT_MODEL", "test-model")
    params = list(inspect.signature(main.build_chat_services).parameters)
    assert params == ["data_root"]
    services = main.build_chat_services(tmp_path)
    store = services.command_artifact_store
    assert isinstance(store, CommandArtifactStore)
    assert Path(store.root) == (tmp_path / "command-output").resolve()
    assert services.repository._database_path == (tmp_path / "chat.sqlite3").resolve()
    assert Path(services.runner._trace_dir) == (tmp_path / "traces").resolve()
    assert Path(store.root) != default_artifact_root()


def test_leftover_warns_without_moving_or_deleting(tmp_path: Path) -> None:
    (
        _env,
        _default,
        _resolve,
        _layout,
        leftover_legacy_paths,
        leftover_warning,
    ) = _data_root_api()
    cwd = tmp_path / "cwd"
    data_root = tmp_path / "new-root"
    data_root.mkdir()
    old_sqlite = cwd / ".agent-foundations" / "chat.sqlite3"
    old_artifacts = cwd / ".agent-foundations" / "command-artifacts"
    old_traces = cwd / "traces"
    old_sqlite.parent.mkdir(parents=True)
    old_sqlite.write_text("legacy-sqlite", encoding="utf-8")
    old_artifacts.mkdir()
    old_traces.mkdir()
    found = leftover_legacy_paths(cwd)
    assert old_sqlite in found
    assert old_artifacts in found
    assert old_traces in found
    text = leftover_warning(found, data_root)
    assert str(old_sqlite) in text
    assert str(old_artifacts) in text
    assert str(old_traces) in text
    assert str(data_root) in text
    assert old_sqlite.read_text(encoding="utf-8") == "legacy-sqlite"
    assert old_artifacts.is_dir()
    assert old_traces.is_dir()


def test_chat_help_shows_data_root_not_state_db() -> None:
    result = CliRunner().invoke(main.app, ["chat", "--help"])
    assert result.exit_code == 0
    assert "--data-root" in result.output
    assert "--state-db" not in result.output
    assert "--trace-dir" not in result.output
    assert "--port" in result.output


def test_chat_rejects_git_worktree_data_root_with_exit_2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    nested = repo / "nested-data"
    nested.mkdir(parents=True)
    (repo / ".git").mkdir()
    monkeypatch.setenv("AGENT_API_KEY", "test-placeholder")
    monkeypatch.setenv("AGENT_MODEL", "test-model")
    result = CliRunner().invoke(main.app, ["chat", "--data-root", str(nested)])
    assert result.exit_code == 2
    assert "No such option" not in result.output
    assert "worktree" in result.output.lower() or "Git" in result.output


def test_chat_cli_data_root_overrides_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Path] = {}

    def fake_build(data_root: Path) -> object:
        captured["data_root"] = Path(data_root)
        return object()

    env_root = tmp_path / "from-env"
    cli_root = tmp_path / "from-cli"
    env_root.mkdir()
    cli_root.mkdir()
    monkeypatch.setenv("AGENT_API_KEY", "test-placeholder")
    monkeypatch.setenv("AGENT_MODEL", "test-model")
    monkeypatch.setenv("AGENT_FOUNDATIONS_DATA_ROOT", str(env_root))
    monkeypatch.setattr(main, "build_chat_services", fake_build)
    monkeypatch.setattr(main, "create_app", lambda *args, **kwargs: object())
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: None)
    result = CliRunner().invoke(main.app, ["chat", "--data-root", str(cli_root)])
    assert result.exit_code == 0
    assert captured["data_root"] == cli_root.resolve()
