"""Context selection and character budgeting."""

from agent_foundations.context.budget import ContextBudget
from agent_foundations.context.builder import ContextBuilder
from agent_foundations.context.cache import CacheKey, ContextSourceCache
from agent_foundations.context.compaction import CompactionRecord, ContextCompactor
from agent_foundations.context.critical_facts import CriticalFact, CriticalFactKind
from agent_foundations.context.fake_compactor import FakeCompactor
from agent_foundations.context.relevance import RelevanceScorer, rank_sources
from agent_foundations.context.repo_map import RepoMap, RepoMapBuilder, RepoMapLimits
from agent_foundations.context.sources import ContextSource

__all__ = [
    "CacheKey",
    "CompactionRecord",
    "ContextBudget",
    "ContextBuilder",
    "ContextCompactor",
    "ContextSource",
    "ContextSourceCache",
    "CriticalFact",
    "CriticalFactKind",
    "FakeCompactor",
    "RelevanceScorer",
    "RepoMap",
    "RepoMapBuilder",
    "RepoMapLimits",
    "rank_sources",
]
