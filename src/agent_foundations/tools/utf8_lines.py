"""Shared UTF-8 line texts for read_file and structured patch matching."""

from __future__ import annotations

from collections.abc import Sequence


def utf8_file_lines(raw: bytes) -> list[tuple[str, bool]]:
    """Split UTF-8 file bytes into (line text, had newline) pairs.

    Line texts contain neither ``\\n`` nor ``\\r``. An empty file is zero lines.
    Mixed newlines and legacy Mac ``\\r``-only files are out of scope.
    """
    text = raw.decode("utf-8")
    if text == "":
        return []
    result: list[tuple[str, bool]] = []
    for part in text.splitlines(keepends=True):
        if part.endswith("\r\n"):
            result.append((part[:-2], True))
        elif part.endswith("\n"):
            result.append((part[:-1], True))
        else:
            result.append((part, False))
    return result


def utf8_line_texts(raw: bytes) -> tuple[str, ...]:
    return tuple(text for text, _has_newline in utf8_file_lines(raw))


def utf8_newline(raw: bytes) -> str:
    if b"\r\n" in raw:
        return "\r\n"
    return "\n"


def join_utf8_file_lines(
    lines: Sequence[tuple[str, bool]],
    *,
    newline: str,
) -> bytes:
    chunks: list[str] = []
    for text, has_newline in lines:
        chunks.append(text)
        if has_newline:
            chunks.append(newline)
    return "".join(chunks).encode("utf-8")
