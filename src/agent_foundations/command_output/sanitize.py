from __future__ import annotations

import re
from pathlib import Path

from agent_foundations.runtime.redaction import Redactor

_MAX_LINE = 240
_CSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_OSC = re.compile(r"\x1b\].*?(?:\x07|\x1b\\)", re.DOTALL)
_CHARSET = re.compile(r"\x1b[()][A-B0-2]")
_OTHER_ESC = re.compile(r"\x1b[@-Z\\-_]")
_PEM = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)
_COOKIE = re.compile(r"(?i)(?:cookie|set-cookie)\s*:[^\n]*")
_AUTH = re.compile(r"(?i)authorization\s*:[^\n]*")
_ENV_ASSIGN = re.compile(
    r"(?im)^(export\s+)?[A-Za-z_][A-Za-z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|COOKIE|CREDENTIAL)[A-Za-z0-9_]*\s*=\s*.+$"
)
_LONG_TOKEN = re.compile(r"\b(?:eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}|[A-Za-z0-9_-]{32,})\b")


def sanitize_streams(
    *,
    stdout: bytes,
    stderr: bytes,
    project_root: Path,
) -> tuple[str, str]:
    redactor = Redactor(project_root)
    return (
        _sanitize_one(stdout, redactor),
        _sanitize_one(stderr, redactor),
    )


def _sanitize_one(payload: bytes, redactor: Redactor) -> str:
    text = payload.decode("utf-8", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CSI.sub("", text)
    text = _OSC.sub("", text)
    text = _CHARSET.sub("", text)
    text = _OTHER_ESC.sub("", text)
    text = "".join(ch if ch in "\n\t" or ord(ch) >= 32 else "" for ch in text)
    text = _PEM.sub("[REDACTED]", text)
    text = _COOKIE.sub("[REDACTED]", text)
    text = _AUTH.sub("[REDACTED]", text)
    text = _ENV_ASSIGN.sub("[REDACTED]", text)
    text = str(redactor.redact(text))
    text = _LONG_TOKEN.sub("[REDACTED]", text)
    lines = [_truncate_line(line) for line in text.split("\n")]
    return "\n".join(lines)


def _truncate_line(line: str) -> str:
    if len(line) <= _MAX_LINE:
        return line
    return line[:_MAX_LINE]
