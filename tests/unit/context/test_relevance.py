from __future__ import annotations

import hashlib
import importlib.util
from typing import Any

import pytest

from agent_foundations.context.budget import ContextBudget
from agent_foundations.context.builder import ContextBuilder
from agent_foundations.domain.errors import ContextBudgetExceededError
from agent_foundations.domain.messages import Message, Role


def _relevance() -> Any:
    try:
        spec = importlib.util.find_spec("agent_foundations.context.relevance")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "RelevanceScorer is missing"
    from agent_foundations.context.relevance import RelevanceScorer, rank_sources
    from agent_foundations.context.sources import ContextSource

    return RelevanceScorer, rank_sources, ContextSource


def _source(
    ContextSource: Any,
    *,
    source_id: str,
    kind: str,
    content: str,
    priority: int,
) -> Any:
    return ContextSource(
        source_id=source_id,
        kind=kind,
        content=content,
        priority=priority,
        provenance="src/mod.py python-ast",
        fingerprint=hashlib.sha256(content.encode("utf-8")).hexdigest(),
    )


def test_term_overlap_score_is_deterministic_and_bounded() -> None:
    RelevanceScorer, _, ContextSource = _relevance()
    scorer = RelevanceScorer()
    source = _source(
        ContextSource,
        source_id="file:src/auth.py",
        kind="file",
        content="authenticate token demo",
        priority=0,
    )
    score = scorer.score("Authenticate the token", source)
    assert 0.0 <= score <= 1.0
    assert score == scorer.score("Authenticate the token", source)
    empty = scorer.score("zzzz-no-overlap", source)
    assert empty == 0.0


def test_tie_break_priority_kind_then_source_id() -> None:
    _, rank_sources, ContextSource = _relevance()
    shared = "alpha beta"
    lower = _source(
        ContextSource,
        source_id="file:src/z.py",
        kind="file",
        content=shared,
        priority=1,
    )
    higher_priority = _source(
        ContextSource,
        source_id="file:src/a.py",
        kind="file",
        content=shared,
        priority=5,
    )
    symbol = _source(
        ContextSource,
        source_id="symbol:src/m.py:Alpha",
        kind="symbol",
        content=shared,
        priority=5,
    )
    imported = _source(
        ContextSource,
        source_id="import:src/m.py:pkg.other",
        kind="import",
        content=shared,
        priority=5,
    )
    ranked = rank_sources("alpha", (lower, higher_priority, imported, symbol))
    assert [item.source_id for item in ranked] == [
        "symbol:src/m.py:Alpha",
        "import:src/m.py:pkg.other",
        "file:src/a.py",
        "file:src/z.py",
    ]


def test_builder_empty_sources_match_legacy_build() -> None:
    import inspect

    builder = ContextBuilder(ContextBudget(max_chars=45, max_tool_result_chars=12))
    messages = (
        Message(role=Role.SYSTEM, content="You are read-only."),
        Message(role=Role.USER, content="old request"),
        Message(role=Role.TOOL, content="abcdefghijklmnopqrstuvwxyz", tool_call_id="c1"),
        Message(role=Role.USER, content="latest request"),
    )
    parameters = inspect.signature(ContextBuilder.build).parameters
    assert "sources" in parameters, "ContextBuilder.build must accept sources"
    assert builder.build(messages, sources=()) == builder.build(messages)


def test_droppable_sources_do_not_raise_and_mandatory_overflow_still_raises() -> None:
    RelevanceScorer, rank_sources, ContextSource = _relevance()
    del RelevanceScorer, rank_sources
    huge = _source(
        ContextSource,
        source_id="file:src/huge.py",
        kind="file",
        content="token " * 4000,
        priority=0,
    )
    builder = ContextBuilder(ContextBudget(max_chars=80, max_tool_result_chars=20))
    messages = (
        Message(role=Role.SYSTEM, content="sys"),
        Message(role=Role.USER, content="find token"),
    )
    result = builder.build(messages, sources=(huge,))
    joined = "\n".join(message.content or "" for message in result)
    assert "token " * 50 not in joined
    tiny = ContextBuilder(ContextBudget(max_chars=10, max_tool_result_chars=20))
    with pytest.raises(ContextBudgetExceededError):
        tiny.build(
            (
                Message(role=Role.SYSTEM, content="This system message is far too long"),
                Message(role=Role.USER, content="latest"),
            ),
            sources=(huge,),
        )
