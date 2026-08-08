import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_REDACTED = "[REDACTED]"
_PROJECT_ROOT = "<PROJECT_ROOT>"


def _normalize_key(key: str) -> str:
    return key.lower().replace("_", "").replace("-", "")


class Redactor:
    _SENSITIVE_KEYS = frozenset({
        "apikey",
        "xapikey",
        "authorization",
        "proxyauthorization",
        "cookie",
        "setcookie",
        "password",
        "privatekey",
        "clientsecret",
        "accesstoken",
        "refreshtoken",
        "secret",
        "token",
    })
    _BEARER = re.compile(r"(?i)bearer\s+[a-zA-Z0-9._~+/=-]+")
    _OPENAI_LIKE_KEY = re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b")

    def __init__(self, project_root: Path, secrets: tuple[str, ...] = ()) -> None:
        resolved = project_root.resolve()
        native = str(resolved)
        if sys.platform == "win32":
            pattern = "".join(
                r"[\\/]" if character in "\\/" else re.escape(character)
                for character in native
            )
            self._root_pattern = re.compile(pattern, flags=re.IGNORECASE)
        else:
            self._root_pattern = re.compile(re.escape(native))
        self._secrets = tuple(secret for secret in secrets if secret)

    def redact(self, value: Any, *, key: str | None = None) -> Any:
        if key is not None and self._is_sensitive_key(key):
            return _REDACTED
        if isinstance(value, Mapping):
            return {
                str(item_key): self.redact(item_value, key=str(item_key))
                for item_key, item_value in value.items()
            }
        if isinstance(value, list):
            return [self.redact(item) for item in value]
        if isinstance(value, tuple):
            return [self.redact(item) for item in value]
        if isinstance(value, str):
            return self._redact_text(value)
        return value

    def _is_sensitive_key(self, key: str) -> bool:
        return _normalize_key(key) in self._SENSITIVE_KEYS

    def _redact_text(self, text: str) -> str:
        result = text
        for secret in sorted(self._secrets, key=len, reverse=True):
            result = result.replace(secret, _REDACTED)
        result = self._root_pattern.sub(_PROJECT_ROOT, result)
        result = self._BEARER.sub("Bearer [REDACTED]", result)
        return self._OPENAI_LIKE_KEY.sub(_REDACTED, result)
