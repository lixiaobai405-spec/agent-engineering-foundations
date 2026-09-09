from __future__ import annotations

import hashlib
import importlib.util
from typing import Any

import pytest
from pydantic import ValidationError


def _sources() -> Any:
    try:
        spec = importlib.util.find_spec("agent_foundations.context.sources")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "ContextSource module is missing"
    from agent_foundations.context.sources import ContextSource

    return ContextSource


def test_context_source_shape_fingerprint_and_stable_ids() -> None:
    ContextSource = _sources()
    content = "class Foo:\n    pass\n"
    source = ContextSource(
        source_id="symbol:src/pkg/mod.py:Foo",
        kind="symbol",
        content=content,
        priority=10,
        provenance="src/pkg/mod.py python-ast",
        fingerprint=hashlib.sha256(content.encode("utf-8")).hexdigest(),
    )
    assert source.source_id.startswith("symbol:")
    assert source.kind == "symbol"
    assert "/" not in source.source_id[:6]
    assert ":" in source.source_id
    assert not source.source_id.startswith("/")
    assert "\\" not in source.source_id
    with pytest.raises(ValidationError):
        ContextSource.model_validate({**source.model_dump(), "kind": "artifact"})
    with pytest.raises(ValidationError):
        ContextSource.model_validate({**source.model_dump(), "host_path": "C:/secrets"})


def test_context_source_rejects_absolute_and_credential_ids() -> None:
    ContextSource = _sources()
    payload = {
        "source_id": "file:src/ok.py",
        "kind": "file",
        "content": "x",
        "priority": 0,
        "provenance": "src/ok.py python-ast",
        "fingerprint": hashlib.sha256(b"x").hexdigest(),
    }
    ContextSource.model_validate(payload)
    with pytest.raises(ValidationError):
        ContextSource.model_validate({**payload, "source_id": "file:C:/Windows/mod.py"})
    with pytest.raises(ValidationError):
        ContextSource.model_validate({**payload, "source_id": "file:/etc/passwd"})
    with pytest.raises(ValidationError):
        ContextSource.model_validate({**payload, "provenance": "C:/Users/admin/.env"})
