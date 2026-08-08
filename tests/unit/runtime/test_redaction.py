import copy
import json
import sys
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

from agent_foundations.domain._freeze import FrozenJSON
from agent_foundations.runtime.redaction import Redactor

REDACTED = "[REDACTED]"
PROJECT_ROOT = "<PROJECT_ROOT>"

SENSITIVE_FIELD_NAMES = [
    "api_key",
    "apiKey",
    "x-api-key",
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "password",
    "private_key",
    "client_secret",
    "access_token",
    "refresh_token",
    "secret",
    "token",
]


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "src").mkdir()
    (root / "src" / "auth.py").write_text("token = 1\n", encoding="utf-8")
    return root


@pytest.fixture
def redactor(project_root: Path) -> Redactor:
    return Redactor(
        project_root=project_root,
        secrets=("live-secret-value", "another-long-secret-value"),
    )


@pytest.mark.parametrize("field_name", SENSITIVE_FIELD_NAMES)
def test_redacts_sensitive_field_names_case_insensitively(
    redactor: Redactor,
    field_name: str,
) -> None:
    for value in ("plain-secret", {"nested": "value"}, ["a", "b"]):
        result = redactor.redact({field_name: value})
        assert result[field_name] == REDACTED


def test_redacts_sensitive_keys_with_mixed_case_variants(redactor: Redactor) -> None:
    source = {
        "API_KEY": "hidden",
        "Authorization": "Bearer hidden",
        "Set-Cookie": "session=abc",
        "CLIENT_SECRET": "hidden",
    }
    result = redactor.redact(source)
    assert all(item == REDACTED for item in result.values())


def test_redacts_nested_structures_to_json_compatible_output(redactor: Redactor) -> None:
    source = {
        "plain_dict": {"token": "secret-value", "safe": 1},
        "mapping_proxy": MappingProxyType({"password": "hidden"}),
        "frozen": FrozenJSON({"refresh_token": "hidden", "count": 2}),
        "items": [
            {"client_secret": "hidden"},
            ("nested", {"access_token": "hidden"}),
        ],
        "safe_tuple": (1, "ok"),
    }

    result = redactor.redact(source)

    assert isinstance(result, dict)
    assert isinstance(result["plain_dict"], dict)
    assert result["plain_dict"]["token"] == REDACTED
    assert result["plain_dict"]["safe"] == 1
    assert isinstance(result["mapping_proxy"], dict)
    assert result["mapping_proxy"]["password"] == REDACTED
    assert isinstance(result["frozen"], dict)
    assert result["frozen"]["refresh_token"] == REDACTED
    assert result["frozen"]["count"] == 2
    assert isinstance(result["items"], list)
    assert isinstance(result["items"][0], dict)
    assert result["items"][0]["client_secret"] == REDACTED
    assert isinstance(result["items"][1], list)
    assert result["items"][1][0] == "nested"
    assert result["items"][1][1]["access_token"] == REDACTED
    assert result["safe_tuple"] == [1, "ok"]


def test_redacts_known_secrets_in_strings(redactor: Redactor) -> None:
    source = {
        "message": "prefix live-secret-value suffix",
        "nested": ["another-long-secret-value inside"],
    }
    result = redactor.redact(source)
    rendered = json.dumps(result, ensure_ascii=False)

    assert "live-secret-value" not in rendered
    assert "another-long-secret-value" not in rendered
    assert REDACTED in rendered


def test_longer_secrets_are_redacted_before_shorter_overlaps(
    project_root: Path,
) -> None:
    redactor = Redactor(
        project_root=project_root,
        secrets=("live-secret", "live-secret-value"),
    )
    result = redactor.redact("live-secret-value remains safe")
    assert "live-secret-value" not in result
    assert result == f"{REDACTED} remains safe"


def test_empty_string_secrets_are_ignored(project_root: Path) -> None:
    redactor = Redactor(project_root=project_root, secrets=("", "real-secret"))
    source = "real-secret should go away"
    result = redactor.redact(source)
    assert result == f"{REDACTED} should go away"


@pytest.mark.parametrize(
    ("text", "forbidden"),
    [
        ("Authorization: Bearer abc.def", "abc.def"),
        ("header bearer example-token ok", "example-token"),
        ("prefix BEARER abc_123-xyz suffix", "abc_123-xyz"),
    ],
)
def test_redacts_bearer_tokens_case_insensitively(
    redactor: Redactor,
    text: str,
    forbidden: str,
) -> None:
    result = redactor.redact(text)
    assert forbidden not in result
    assert REDACTED in result


@pytest.mark.parametrize(
    "provider_key",
    [
        "sk-example1234567890",
        "sk-proj-example_1234567890",
    ],
)
def test_redacts_openai_like_keys(redactor: Redactor, provider_key: str) -> None:
    result = redactor.redact({"model_key": provider_key, "note": f"use {provider_key}"})
    rendered = json.dumps(result, ensure_ascii=False)
    assert provider_key not in rendered
    assert REDACTED in rendered


def test_redacts_project_absolute_paths(project_root: Path) -> None:
    redactor = Redactor(project_root=project_root, secrets=())
    absolute = project_root.resolve()
    native = str(absolute)
    forward = native.replace("\\", "/")
    nested_file = absolute / "src" / "auth.py"

    cases = [
        native,
        forward,
        f"read {nested_file}",
        f"mixed {forward}/src/auth.py tail",
    ]
    if sys.platform == "win32":
        cases.append(str(nested_file).swapcase())

    for text in cases:
        result = redactor.redact(text)
        assert str(absolute) not in result
        assert native not in result
        assert forward not in result
        assert PROJECT_ROOT in result


@pytest.mark.skipif(sys.platform != "win32", reason="Windows path semantics")
def test_redacts_windows_project_paths_with_mixed_separators(
    project_root: Path,
) -> None:
    redactor = Redactor(project_root=project_root, secrets=())
    native = str(project_root.resolve())
    mixed_root = native.replace("\\", "/", 1)
    mixed_path = f"{mixed_root}\\src/auth.py"

    assert Path(mixed_path).is_absolute()
    result = redactor.redact(mixed_path)

    assert mixed_root not in result
    assert PROJECT_ROOT in result


def test_does_not_redact_relative_paths_or_urls(redactor: Redactor) -> None:
    safe_values = [
        "src/auth.py",
        "https://example.test/v1",
        "relative/path/to/file.py",
    ]
    for value in safe_values:
        assert redactor.redact(value) == value


def test_redact_does_not_modify_source(redactor: Redactor) -> None:
    source: dict[str, Any] = {
        "headers": {"Authorization": "Bearer abc.def"},
        "items": [{"token": "secret"}, ("nested", {"api_key": "hidden"})],
        "message": "live-secret-value",
    }
    snapshot = copy.deepcopy(source)

    result = redactor.redact(source)

    assert source == snapshot
    assert result is not source
    assert result["headers"] is not source["headers"]
    assert result["items"][0] is not source["items"][0]
    assert isinstance(result["items"][1], list)
    assert result["items"][1] is not source["items"][1]

    result["headers"]["Authorization"] = "mutated"
    result["items"][0]["token"] = "mutated"
    assert source == snapshot


def test_does_not_over_redact_safe_content(redactor: Redactor) -> None:
    source = {
        "variable": "token is a source-code variable",
        "metric": "token_count",
        "budget": "authentication token budget",
        "path": "src/auth.py",
        "url": "https://example.test/v1",
    }
    result = redactor.redact(source)
    assert result == source


def test_result_is_json_serializable(redactor: Redactor, project_root: Path) -> None:
    absolute = str(project_root.resolve())
    source = {
        "api_key": "live-secret-value",
        "headers": {"Authorization": "Bearer abc.def"},
        "payload": [f"read {absolute}/src/auth.py", "sk-example1234567890"],
        "safe": "token is a source-code variable",
    }
    result = redactor.redact(source)
    serialized = json.dumps(result, ensure_ascii=False)

    assert "live-secret-value" not in serialized
    assert "abc.def" not in serialized
    assert absolute not in serialized
    assert "sk-example1234567890" not in serialized
    assert "token is a source-code variable" in serialized
