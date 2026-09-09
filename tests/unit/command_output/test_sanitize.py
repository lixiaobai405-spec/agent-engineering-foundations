from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

PLACEHOLDER_KEY = "sk-test_placeholder_not_real"
PLACEHOLDER_BEARER = "Bearer test-token-placeholder"
PLACEHOLDER_COOKIE = "session=test-cookie-placeholder-not-real"
PLACEHOLDER_PEM = (
    "-----BEGIN PRIVATE KEY-----\n"
    "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQCplaceholder\n"
    "-----END PRIVATE KEY-----"
)
PLACEHOLDER_ENV = "API_KEY=sk-test_placeholder_not_real"


def _require_sanitize() -> Any:
    try:
        spec = importlib.util.find_spec("agent_foundations.command_output.sanitize")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "command output sanitize is missing"
    from agent_foundations.command_output.sanitize import sanitize_streams

    return sanitize_streams


def test_sanitize_keeps_two_streams_and_replaces_invalid_utf8() -> None:
    sanitize_streams = _require_sanitize()
    stdout, stderr = sanitize_streams(
        stdout=b"ok\xff",
        stderr=b"err",
        project_root=Path("."),
    )
    assert stdout != stderr
    assert "\ufffd" in stdout or stdout.startswith("ok")
    assert "err" in stderr


def test_sanitize_normalizes_newlines_and_strips_ansi_osc() -> None:
    sanitize_streams = _require_sanitize()
    payload = b"a\r\nb\rc\n\x1b[31mred\x1b[0m\n\x1b]0;title\x07done\n"
    stdout, stderr = sanitize_streams(stdout=payload, stderr=b"", project_root=Path("."))
    assert "\r" not in stdout
    assert "\x1b" not in stdout
    assert "red" in stdout
    assert "done" in stdout
    assert stderr == ""


def test_sanitize_handles_binary_and_no_newline() -> None:
    sanitize_streams = _require_sanitize()
    stdout, _stderr = sanitize_streams(
        stdout=b"\x00no-newline",
        stderr=b"",
        project_root=Path("."),
    )
    assert "no-newline" in stdout
    assert "\n" not in stdout or stdout.endswith("no-newline")


def test_sanitize_truncates_overlong_lines_to_240() -> None:
    sanitize_streams = _require_sanitize()
    long_line = ("x" * 400).encode("utf-8")
    stdout, _stderr = sanitize_streams(
        stdout=long_line,
        stderr=b"",
        project_root=Path("."),
    )
    assert max((len(line) for line in stdout.split("\n") if line), default=0) <= 240


def test_sanitize_redacts_token_cookie_pem_and_env_forms() -> None:
    sanitize_streams = _require_sanitize()
    blob = "\n".join(
        [
            PLACEHOLDER_KEY,
            PLACEHOLDER_BEARER,
            f"Cookie: {PLACEHOLDER_COOKIE}",
            PLACEHOLDER_PEM,
            PLACEHOLDER_ENV,
            "Authorization: Bearer test-token-placeholder",
        ]
    ).encode("utf-8")
    stdout, _stderr = sanitize_streams(stdout=blob, stderr=b"", project_root=Path("."))
    assert PLACEHOLDER_KEY not in stdout
    assert "test-token-placeholder" not in stdout
    assert "BEGIN PRIVATE KEY" not in stdout
    assert "API_KEY=" not in stdout or "[REDACTED]" in stdout
    assert "[REDACTED]" in stdout


def test_fixture_corpus_has_no_live_secrets_and_redacts_placeholders() -> None:
    sanitize_streams = _require_sanitize()
    root = Path("tests/fixtures/command-output")
    forbidden = (
        "sk-live",
        "BEGIN RSA PRIVATE KEY",
        "AKIA",
        "Set-Cookie: session=",
    )
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in forbidden:
            assert token not in text, f"{path} must not contain live secret form {token}"
    stdout, _stderr = sanitize_streams(
        stdout=PLACEHOLDER_PEM.encode("utf-8"),
        stderr=b"",
        project_root=Path("."),
    )
    assert "[REDACTED]" in stdout
    assert "BEGIN PRIVATE KEY" not in stdout


def test_parser_feedback_path_redacts_placeholder_secrets() -> None:
    sanitize_streams = _require_sanitize()
    from agent_foundations.command_output.parsers.ruff import RuffOutputParser

    raw = (
        b'[{"filename":"src/a.py","code":"F401",'
        b'"message":"unused sk-test_placeholder_not_real",'
        b'"location":{"row":1,"column":1}}]'
    )
    stdout, _stderr = sanitize_streams(stdout=raw, stderr=b"", project_root=Path("."))
    outcome = RuffOutputParser().parse(stdout, "", exit_code=1)
    combined = " ".join(item.message for item in outcome.diagnostics)
    assert PLACEHOLDER_KEY not in combined
    assert PLACEHOLDER_KEY not in stdout
    assert "[REDACTED]" in combined
