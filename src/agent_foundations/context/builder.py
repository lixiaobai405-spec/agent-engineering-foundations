from agent_foundations.context.budget import ContextBudget
from agent_foundations.context.relevance import rank_sources
from agent_foundations.context.sources import ContextSource, source_relative_path
from agent_foundations.domain.errors import ContextBudgetExceededError, PathPolicyViolationError
from agent_foundations.domain.messages import Message, Role
from agent_foundations.tools.filesystem.path_policy import PathPolicy

_SOURCE_HEADER = "[repository context]"


class ContextBuilder:
    def __init__(self, budget: ContextBudget) -> None:
        self._budget = budget

    @property
    def budget(self) -> ContextBudget:
        return self._budget

    def build(
        self,
        messages: tuple[Message, ...],
        sources: tuple[ContextSource, ...] = (),
        *,
        policy: PathPolicy | None = None,
    ) -> tuple[Message, ...]:
        normalized = tuple(self._truncate_tool_message(message) for message in messages)
        system = tuple(message for message in normalized if message.role is Role.SYSTEM)
        non_system = tuple(message for message in normalized if message.role is not Role.SYSTEM)
        selected: list[Message] = list(system)
        used = sum(self._size(message) for message in selected)

        if used > self._budget.max_chars:
            raise ContextBudgetExceededError(
                f"system messages ({used} chars) exceed context budget"
                f" ({self._budget.max_chars} chars)"
            )

        recent: list[Message] = []
        for message in reversed(non_system):
            size = self._size(message)
            if used + size <= self._budget.max_chars or not recent:
                recent.append(message)
                used += size
        selected.extend(reversed(recent))

        if used > self._budget.max_chars:
            raise ContextBudgetExceededError(
                f"mandatory messages ({used} chars) exceed context budget"
                f" ({self._budget.max_chars} chars)"
            )

        source_message = self._source_message(normalized, sources, used, policy)
        if source_message is not None:
            insert_at = len(system)
            selected.insert(insert_at, source_message)
        return tuple(selected)

    def needs_compaction(self, messages: tuple[Message, ...]) -> bool:
        from agent_foundations.context.compaction import should_compact

        return should_compact(messages, self._budget)

    def _source_message(
        self,
        messages: tuple[Message, ...],
        sources: tuple[ContextSource, ...],
        used: int,
        policy: PathPolicy | None,
    ) -> Message | None:
        if not sources:
            return None
        leftover = max(0, self._budget.max_chars - used)
        source_budget = min(leftover, self._budget.max_source_chars)
        if source_budget < 1:
            return None
        query = _latest_user_text(messages)
        blocks: list[str] = []
        total = len(_SOURCE_HEADER) + 1
        for source in rank_sources(query, sources):
            if policy is not None:
                try:
                    policy.authorize(source_relative_path(source.source_id))
                except (PathPolicyViolationError, ValueError):
                    continue
            block = f"## {source.source_id}\n{source.content}"
            extra = len(block) + (2 if blocks else 0)
            if total + extra > source_budget:
                continue
            blocks.append(block)
            total += extra
        if not blocks:
            return None
        content = f"{_SOURCE_HEADER}\n" + "\n\n".join(blocks)
        if used + len(content) > self._budget.max_chars:
            return None
        return Message(role=Role.SYSTEM, content=content)

    def _truncate_tool_message(self, message: Message) -> Message:
        if message.role is not Role.TOOL or message.content is None:
            return message
        limit = self._budget.max_tool_result_chars
        if len(message.content) <= limit:
            return message
        suffix = "..."
        if limit <= len(suffix):
            truncated = suffix[:limit]
        else:
            truncated = message.content[: limit - len(suffix)] + suffix
        return message.model_copy(update={"content": truncated})

    @staticmethod
    def _size(message: Message) -> int:
        return len(message.content or "")


def _latest_user_text(messages: tuple[Message, ...]) -> str:
    for message in reversed(messages):
        if message.role is Role.USER and message.content:
            return message.content
    return ""
