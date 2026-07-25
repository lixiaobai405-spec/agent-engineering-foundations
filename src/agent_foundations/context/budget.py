from dataclasses import dataclass


@dataclass(frozen=True)
class ContextBudget:
    max_chars: int = 32_000
    max_tool_result_chars: int = 8_000

    def __post_init__(self) -> None:
        if self.max_chars < 1 or self.max_tool_result_chars < 1:
            raise ValueError("context limits must be positive")
