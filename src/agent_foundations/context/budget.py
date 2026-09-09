from dataclasses import dataclass


@dataclass(frozen=True)
class ContextBudget:
    max_chars: int = 32_000
    max_tool_result_chars: int = 8_000
    max_source_chars: int = 4_000
    compaction_trigger_chars: int | None = None

    def __post_init__(self) -> None:
        trigger = (
            self.max_chars
            if self.compaction_trigger_chars is None
            else self.compaction_trigger_chars
        )
        if (
            self.max_chars < 1
            or self.max_tool_result_chars < 1
            or self.max_source_chars < 1
            or trigger < 1
        ):
            raise ValueError("context limits must be positive")
        if self.compaction_trigger_chars is None:
            object.__setattr__(self, "compaction_trigger_chars", trigger)
