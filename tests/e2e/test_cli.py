import json
import os
from pathlib import Path

import pytest
import uvicorn
from pytest import MonkeyPatch
from typer.testing import CliRunner

from agent_foundations.cli import main
from agent_foundations.runtime.agent import AgentResult, PlanningMode
from agent_foundations.runtime.sinks import CompositeEventSink, JsonlEventSink, LiveEventSink

# ── Fake runtime ─────────────────────────────────────────────────────────


class FakeLoop:
    """An AgentLoop stand-in that returns a pre-canned AgentResult."""

    def __init__(self, answer: str) -> None:
        self._answer = answer

    async def run(self, root: Path, query: str) -> AgentResult:
        return AgentResult(
            session_id="session-test",
            answer=self._answer,
            steps=1,
        )


class ExplodingLoop:
    """An AgentLoop stand-in that always raises."""

    async def run(self, root: Path, query: str) -> AgentResult:
        raise RuntimeError("simulated failure")


# ── CLI tests ────────────────────────────────────────────────────────────


def test_help_shows_analyze_and_viewer_commands() -> None:
    result = CliRunner().invoke(main.app, ["--help"])
    assert result.exit_code == 0
    assert "analyze" in result.output
    assert "viewer" in result.output
    assert "chat" in result.output


def test_chat_help_shows_local_options() -> None:
    result = CliRunner().invoke(main.app, ["chat", "--help"])
    assert result.exit_code == 0
    assert "--state-db" in result.output
    assert "--trace-dir" in result.output
    assert "--port" in result.output
    assert "--host" not in result.output


def test_chat_missing_api_key_returns_exit_2(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AGENT_API_KEY", raising=False)
    monkeypatch.setenv("AGENT_MODEL", "test-model")
    result = CliRunner().invoke(main.app, ["chat", "--trace-dir", str(tmp_path)])
    assert result.exit_code == 2
    assert "AGENT_API_KEY" in result.output


def test_chat_missing_model_returns_exit_2(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGENT_API_KEY", "test-key")
    monkeypatch.delenv("AGENT_MODEL", raising=False)
    result = CliRunner().invoke(main.app, ["chat", "--trace-dir", str(tmp_path)])
    assert result.exit_code == 2
    assert "AGENT_MODEL" in result.output


def test_chat_blank_credentials_return_exit_2(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGENT_API_KEY", "   ")
    monkeypatch.setenv("AGENT_MODEL", "test-model")
    result = CliRunner().invoke(main.app, ["chat"])
    assert result.exit_code == 2
    assert "AGENT_API_KEY" in result.output


def test_chat_command_binds_loopback_only(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def fake_run(app: object, host: str, port: int, **kwargs: object) -> None:
        captured.update({"app": app, "host": host, "port": port})

    monkeypatch.setenv("AGENT_API_KEY", "test-placeholder")
    monkeypatch.setenv("AGENT_MODEL", "test-model")
    monkeypatch.setattr(uvicorn, "run", fake_run)
    result = CliRunner().invoke(
        main.app,
        [
            "chat",
            "--state-db",
            str(tmp_path / "chat.sqlite3"),
            "--trace-dir",
            str(tmp_path / "traces"),
            "--port",
            "9002",
        ],
    )
    assert result.exit_code == 0
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 9002


def test_help_output_is_ascii_safe_for_windows_conda() -> None:
    result = CliRunner().invoke(main.app, ["--help"])

    assert result.exit_code == 0
    assert result.output.isascii()


def test_viewer_command_binds_loopback(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def fake_run(app: object, host: str, port: int, **kwargs: object) -> None:
        captured.update({"host": host, "port": port})

    monkeypatch.setattr(uvicorn, "run", fake_run)
    result = CliRunner().invoke(
        main.app,
        ["viewer", "--trace-dir", str(tmp_path), "--port", "9001"],
    )
    assert result.exit_code == 0
    assert captured == {"host": "127.0.0.1", "port": 9001}
    assert "http://127.0.0.1:9001" in result.output


def test_viewer_command_does_not_require_model_env(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("AGENT_API_KEY", raising=False)
    monkeypatch.delenv("AGENT_MODEL", raising=False)

    def fake_run(app: object, host: str, port: int, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(uvicorn, "run", fake_run)
    result = CliRunner().invoke(
        main.app,
        ["viewer", "--trace-dir", str(tmp_path)],
    )
    assert result.exit_code == 0


def test_analyze_passes_default_trace_dir_and_no_viewer_url(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def fake_build(
        root: Path,
        trace_dir: Path,
        viewer_url: str | None,
        planning_mode: PlanningMode = PlanningMode.DISABLED,
    ) -> FakeLoop:
        captured.update({
            "root": root,
            "trace_dir": trace_dir,
            "viewer_url": viewer_url,
        })
        return FakeLoop("Everything is fine.")

    monkeypatch.setenv("AGENT_API_KEY", "test-placeholder")
    monkeypatch.setenv("AGENT_MODEL", "test-model")
    monkeypatch.setattr(main, "build_runtime", fake_build)
    result = CliRunner().invoke(
        main.app,
        ["analyze", str(tmp_path), "inspect"],
    )
    assert result.exit_code == 0
    assert captured["root"] == tmp_path.resolve()
    trace_dir = captured["trace_dir"]
    assert isinstance(trace_dir, Path)
    assert trace_dir.is_absolute()
    assert trace_dir.name == "traces"
    assert captured["viewer_url"] is None


def test_analyze_passes_viewer_url(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def fake_build(
        root: Path,
        trace_dir: Path,
        viewer_url: str | None,
        planning_mode: PlanningMode = PlanningMode.DISABLED,
    ) -> FakeLoop:
        captured["viewer_url"] = viewer_url
        return FakeLoop("Everything is fine.")

    monkeypatch.setenv("AGENT_API_KEY", "test-placeholder")
    monkeypatch.setenv("AGENT_MODEL", "test-model")
    monkeypatch.setattr(main, "build_runtime", fake_build)
    result = CliRunner().invoke(
        main.app,
        [
            "analyze",
            str(tmp_path),
            "inspect",
            "--viewer-url",
            "http://127.0.0.1:8765",
        ],
    )
    assert result.exit_code == 0
    assert captured["viewer_url"] == "http://127.0.0.1:8765"


def test_missing_api_key_returns_exit_2(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AGENT_API_KEY", raising=False)
    monkeypatch.setenv("AGENT_MODEL", "test-model")
    result = CliRunner().invoke(main.app, ["analyze", str(tmp_path), "inspect"])
    assert result.exit_code == 2
    assert "AGENT_API_KEY" in result.output


def test_missing_api_model_returns_exit_2(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGENT_API_KEY", "test-key")
    monkeypatch.delenv("AGENT_MODEL", raising=False)
    result = CliRunner().invoke(main.app, ["analyze", str(tmp_path), "inspect"])
    assert result.exit_code == 2
    assert "AGENT_MODEL" in result.output


def test_blank_api_key_is_treated_as_missing(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGENT_API_KEY", "   ")
    monkeypatch.setenv("AGENT_MODEL", "test-model")
    result = CliRunner().invoke(main.app, ["analyze", str(tmp_path), "inspect"])
    assert result.exit_code == 2
    assert "AGENT_API_KEY" in result.output


def test_load_cli_env_reads_dotenv_file(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AGENT_API_KEY", raising=False)
    (tmp_path / ".env").write_text("AGENT_API_KEY=from-dotenv\n", encoding="utf-8")
    main.load_cli_env()
    assert os.getenv("AGENT_API_KEY") == "from-dotenv"


def test_load_cli_env_does_not_override_shell_env(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGENT_API_KEY", "shell-key")
    (tmp_path / ".env").write_text("AGENT_API_KEY=from-dotenv\n", encoding="utf-8")
    main.load_cli_env()
    assert os.getenv("AGENT_API_KEY") == "shell-key"


def test_analyze_loads_credentials_from_dotenv_file(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AGENT_API_KEY", raising=False)
    monkeypatch.delenv("AGENT_MODEL", raising=False)
    (tmp_path / ".env").write_text(
        "AGENT_API_KEY=dotenv-key\nAGENT_MODEL=dotenv-model\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        main,
        "build_runtime",
        lambda root, trace_dir, viewer_url, planning_mode=PlanningMode.DISABLED: FakeLoop(
            "Loaded from dotenv.",
        ),
    )
    result = CliRunner().invoke(
        main.app,
        ["analyze", str(tmp_path), "inspect"],
    )
    assert result.exit_code == 0
    assert "Loaded from dotenv." in result.output


def test_fake_loop_success_renders_answer(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AGENT_API_KEY", "test-placeholder")
    monkeypatch.setenv("AGENT_MODEL", "test-model")
    monkeypatch.setattr(
        main,
        "build_runtime",
        lambda root, trace_dir, viewer_url, planning_mode=PlanningMode.DISABLED: FakeLoop(
            "Everything is fine.",
        ),
    )
    result = CliRunner().invoke(
        main.app, ["analyze", str(tmp_path), "inspect"],
    )
    assert result.exit_code == 0
    assert "Everything is fine." in result.output
    assert "session-test" in result.output
    assert "Steps: 1" in result.output


def test_fake_loop_failure_returns_exit_1(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AGENT_API_KEY", "test-placeholder")
    monkeypatch.setenv("AGENT_MODEL", "test-model")
    monkeypatch.setattr(
        main,
        "build_runtime",
        lambda root, trace_dir, viewer_url, planning_mode=PlanningMode.DISABLED: ExplodingLoop(),
    )
    result = CliRunner().invoke(
        main.app, ["analyze", str(tmp_path), "inspect"],
    )
    assert result.exit_code == 1
    assert "Agent failed" in result.output


def test_build_runtime_registers_three_tools(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AGENT_API_KEY", "test-key")
    monkeypatch.setenv("AGENT_MODEL", "test-model")
    runtime = main.build_runtime(tmp_path, tmp_path / "traces", None)
    names = {definition.name for definition in runtime._registry.definitions()}
    assert names == {"list_directory", "read_file", "search_text"}


def test_build_runtime_uses_jsonl_only_without_viewer_url(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AGENT_API_KEY", "test-key")
    monkeypatch.setenv("AGENT_MODEL", "test-model")
    runtime = main.build_runtime(tmp_path, tmp_path / "traces", None)
    assert isinstance(runtime._event_sink, CompositeEventSink)
    sinks = runtime._event_sink._sinks
    assert len(sinks) == 1
    assert isinstance(sinks[0], JsonlEventSink)
    assert all(not isinstance(sink, LiveEventSink) for sink in sinks)


def test_build_runtime_adds_live_sink_for_loopback_viewer_url(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AGENT_API_KEY", "test-key")
    monkeypatch.setenv("AGENT_MODEL", "test-model")
    runtime = main.build_runtime(
        tmp_path,
        tmp_path / "traces",
        "http://127.0.0.1:8765",
    )
    assert isinstance(runtime._event_sink, CompositeEventSink)
    sinks = runtime._event_sink._sinks
    assert len(sinks) == 2
    assert isinstance(sinks[0], JsonlEventSink)
    assert isinstance(sinks[1], LiveEventSink)


def test_build_runtime_rejects_non_loopback_viewer_url(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AGENT_API_KEY", "test-key")
    monkeypatch.setenv("AGENT_MODEL", "test-model")
    with pytest.raises(ValueError, match="viewer_url"):
        main.build_runtime(tmp_path, tmp_path / "traces", "http://localhost:8765")


def test_build_runtime_passes_sdk_config(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AGENT_API_KEY", "test-key")
    monkeypatch.setenv("AGENT_MODEL", "test-model")
    monkeypatch.setenv("AGENT_BASE_URL", "https://custom.example/v1")

    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(main, "AsyncOpenAI", FakeClient)
    main.build_runtime(tmp_path, tmp_path / "traces", None)

    assert captured["api_key"] == "test-key"
    assert captured["base_url"] == "https://custom.example/v1"
    assert captured["timeout"] == 60.0
    assert captured["max_retries"] == 2


# ── Offline evaluate ─────────────────────────────────────────────────────


REPO_ROOT = Path(__file__).resolve().parents[2]
TASK_SET_PATH = REPO_ROOT / "tests" / "fixtures" / "evals" / "phase-1-tasks-v1.json"
RESPONSES_PATH = REPO_ROOT / "tests" / "fixtures" / "evals" / "phase-1-responses-v1.json"
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures"
SAMPLE_PROJECT_PATH = FIXTURE_ROOT / "sample_project"


def offline_evaluate_args(output: Path) -> list[str]:
    return [
        "evaluate",
        "--task-set",
        str(TASK_SET_PATH),
        "--responses",
        str(RESPONSES_PATH),
        "--output",
        str(output),
        "--runtime-revision",
        "working-tree",
    ]


def test_help_shows_evaluate_command() -> None:
    result = CliRunner().invoke(main.app, ["--help"])
    assert result.exit_code == 0
    assert "evaluate" in result.output


def test_evaluate_command_does_not_require_model_credentials(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("AGENT_API_KEY", raising=False)
    monkeypatch.delenv("AGENT_MODEL", raising=False)
    output = tmp_path / "report.json"
    result = CliRunner().invoke(main.app, offline_evaluate_args(output))
    assert result.exit_code == 0


def test_evaluate_does_not_load_dotenv(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AGENT_API_KEY", raising=False)
    (tmp_path / ".env").write_text("AGENT_API_KEY=from-dotenv\n", encoding="utf-8")
    output = tmp_path / "report.json"

    load_calls = 0

    def track_load() -> None:
        nonlocal load_calls
        load_calls += 1
        main.load_cli_env()

    monkeypatch.setattr(main, "load_cli_env", track_load)
    result = CliRunner().invoke(
        main.app,
        [
            "evaluate",
            "--task-set",
            str(TASK_SET_PATH),
            "--responses",
            str(RESPONSES_PATH),
            "--output",
            str(output),
            "--runtime-revision",
            "working-tree",
        ],
    )
    assert result.exit_code == 0
    assert load_calls == 0
    assert os.getenv("AGENT_API_KEY") is None


def test_evaluate_does_not_build_real_provider(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("AGENT_API_KEY", raising=False)

    def fail_build() -> object:
        raise AssertionError("build_provider must not be called")

    monkeypatch.setattr(main, "build_provider", fail_build)
    def fail_openai(**kwargs: object) -> object:
        raise AssertionError("openai")

    monkeypatch.setattr(main, "AsyncOpenAI", fail_openai)
    output = tmp_path / "report.json"
    result = CliRunner().invoke(main.app, offline_evaluate_args(output))
    assert result.exit_code == 0


def test_evaluate_all_pass_exits_zero_and_writes_report(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    result = CliRunner().invoke(main.app, offline_evaluate_args(output))
    assert result.exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["summary"]["failed_tasks"] == 0
    assert payload["runtime_revision"] == "working-tree"
    assert "task_set_sha256" in dict(payload["environment"])
    assert "response_fixture_sha256" in dict(payload["environment"])


def test_evaluate_capability_failure_exits_one_and_writes_report(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    failing_responses = tmp_path / "responses.json"
    failing_responses.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "fixture_id": "phase-1-responses-fail",
                "fixture_version": "v1",
                "scripts": [
                    {
                        "task_id": "phase1-code-location",
                        "responses": [{"content": "wrong answer without auth.py"}],
                    },
                    {
                        "task_id": "phase1-error-explanation",
                        "responses": [{"content": "False"}],
                    },
                    {
                        "task_id": "phase1-readonly-tool-selection",
                        "responses": [
                            {
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call-list-1",
                                        "name": "list_directory",
                                        "arguments": {"path": "src"},
                                    }
                                ],
                            },
                            {"content": "src contains auth.py"},
                        ],
                    },
                    {
                        "task_id": "phase1-sensitive-file-rejection",
                        "responses": [
                            {
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call-env-1",
                                        "name": "read_file",
                                        "arguments": {"path": ".env"},
                                    }
                                ],
                            },
                            {"content": "blocked"},
                        ],
                    },
                    {
                        "task_id": "phase1-external-path-rejection",
                        "responses": [
                            {
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call-ext-1",
                                        "name": "read_file",
                                        "arguments": {"path": "C:/outside/eval-forbidden.txt"},
                                    }
                                ],
                            },
                            {"content": "blocked"},
                        ],
                    },
                    {
                        "task_id": "phase2a-planning-required",
                        "responses": [{"content": "authenticate is in src/auth.py"}],
                    },
                    {
                        "task_id": "phase2a-planning-disabled",
                        "responses": [{"content": "src contains auth.py"}],
                    },
                    {
                        "task_id": "phase2a-replan-limit",
                        "responses": [{"content": "auth.py is in src"}],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "report.json"
    result = CliRunner().invoke(
        main.app,
        [
            "evaluate",
            "--task-set",
            str(TASK_SET_PATH),
            "--responses",
            str(failing_responses),
            "--output",
            str(output),
            "--runtime-revision",
            "working-tree",
        ],
    )
    assert result.exit_code == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["summary"]["failed_tasks"] >= 1


def test_evaluate_missing_task_set_exits_two_without_overwriting_output(
    tmp_path: Path,
) -> None:
    output = tmp_path / "report.json"
    output.write_text('{"stable": true}\n', encoding="utf-8")
    result = CliRunner().invoke(
        main.app,
        [
            "evaluate",
            "--task-set",
            str(tmp_path / "missing-tasks.json"),
            "--responses",
            str(RESPONSES_PATH),
            "--output",
            str(output),
            "--runtime-revision",
            "working-tree",
        ],
    )
    assert result.exit_code == 2
    assert output.read_text(encoding="utf-8") == '{"stable": true}\n'


def test_evaluate_invalid_response_schema_exits_two(
    tmp_path: Path,
) -> None:
    bad_responses = tmp_path / "bad-responses.json"
    bad_responses.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "fixture_id": "bad",
                "fixture_version": "v1",
                "scripts": [
                    {
                        "task_id": "phase1-code-location",
                        "responses": [{"content": None, "tool_calls": []}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "report.json"
    result = CliRunner().invoke(
        main.app,
        [
            "evaluate",
            "--task-set",
            str(TASK_SET_PATH),
            "--responses",
            str(bad_responses),
            "--output",
            str(output),
            "--runtime-revision",
            "working-tree",
        ],
    )
    assert result.exit_code == 2
    assert not output.exists()


def test_evaluate_duplicate_task_id_in_responses_exits_two(tmp_path: Path) -> None:
    dup_responses = tmp_path / "dup-responses.json"
    dup_responses.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "fixture_id": "dup",
                "fixture_version": "v1",
                "scripts": [
                    {"task_id": "phase1-code-location", "responses": [{"content": "ok"}]},
                    {"task_id": "phase1-code-location", "responses": [{"content": "ok"}]},
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "report.json"
    result = CliRunner().invoke(
        main.app,
        [
            "evaluate",
            "--task-set",
            str(TASK_SET_PATH),
            "--responses",
            str(dup_responses),
            "--output",
            str(output),
            "--runtime-revision",
            "working-tree",
        ],
    )
    assert result.exit_code == 2


def test_evaluate_exhausted_response_script_exits_two(tmp_path: Path) -> None:
    exhausted = tmp_path / "exhausted.json"
    exhausted.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "fixture_id": "exhausted",
                "fixture_version": "v1",
                "scripts": [
                    {
                        "task_id": "phase1-code-location",
                        "responses": [
                            {
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call-1",
                                        "name": "search_text",
                                        "arguments": {"query": "authenticate", "path": "."},
                                    }
                                ],
                            }
                        ],
                    },
                    {"task_id": "phase1-error-explanation", "responses": [{"content": "False"}]},
                    {
                        "task_id": "phase1-readonly-tool-selection",
                        "responses": [
                            {
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call-list-1",
                                        "name": "list_directory",
                                        "arguments": {"path": "src"},
                                    }
                                ],
                            },
                            {"content": "src contains auth.py"},
                        ],
                    },
                    {
                        "task_id": "phase1-sensitive-file-rejection",
                        "responses": [
                            {
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call-env-1",
                                        "name": "read_file",
                                        "arguments": {"path": ".env"},
                                    }
                                ],
                            },
                            {"content": "blocked"},
                        ],
                    },
                    {
                        "task_id": "phase1-external-path-rejection",
                        "responses": [
                            {
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call-ext-1",
                                        "name": "read_file",
                                        "arguments": {"path": "C:/outside/eval-forbidden.txt"},
                                    }
                                ],
                            },
                            {"content": "blocked"},
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "report.json"
    result = CliRunner().invoke(
        main.app,
        [
            "evaluate",
            "--task-set",
            str(TASK_SET_PATH),
            "--responses",
            str(exhausted),
            "--output",
            str(output),
            "--runtime-revision",
            "working-tree",
        ],
    )
    assert result.exit_code == 2


def test_evaluate_only_reads_sample_project_fixture(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    result = CliRunner().invoke(main.app, offline_evaluate_args(output))
    assert result.exit_code == 0
    assert SAMPLE_PROJECT_PATH.is_dir()
