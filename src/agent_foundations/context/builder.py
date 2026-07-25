from agent_foundations.context.budget import ContextBudget
from agent_foundations.domain.errors import ContextBudgetExceededError
from agent_foundations.domain.messages import Message, Role


class ContextBuilder:
    def __init__(self, budget: ContextBudget) -> None:
        self._budget = budget

    def build(self, messages: tuple[Message, ...]) -> tuple[Message, ...]:
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

        return tuple(selected)

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
