from __future__ import annotations

import re

from agent_foundations.context.sources import ContextSource

_KIND_RANK = {"symbol": 0, "import": 1, "file": 2}
_SPLIT = re.compile(r"[^0-9A-Za-z]+")


def tokenize(text: str) -> frozenset[str]:
    return frozenset(token for token in _SPLIT.split(text.casefold()) if token)


class RelevanceScorer:
    def score(self, query: str, source: ContextSource) -> float:
        query_tokens = tokenize(query)
        if not query_tokens:
            return 0.0
        source_tokens = tokenize(f"{source.source_id} {source.content}")
        overlap = query_tokens & source_tokens
        return len(overlap) / len(query_tokens)


def rank_sources(
    query: str,
    sources: tuple[ContextSource, ...],
) -> tuple[ContextSource, ...]:
    scorer = RelevanceScorer()
    return tuple(
        sorted(
            sources,
            key=lambda source: (
                -scorer.score(query, source),
                -source.priority,
                _KIND_RANK[source.kind],
                source.source_id,
            ),
        )
    )
