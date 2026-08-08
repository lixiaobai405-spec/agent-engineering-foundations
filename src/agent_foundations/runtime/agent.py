from dataclasses import dataclass


@dataclass(frozen=True)
class AgentConfig:
    max_steps: int = 10
    system_prompt: str = (
        "You are a read-only coding agent. Use only the supplied tools. "
        "Never claim to modify files, run commands, or access paths outside the project."
    )

    def __post_init__(self) -> None:
        if self.max_steps < 1:
            raise ValueError("max_steps must be positive")


@dataclass(frozen=True)
class AgentResult:
    session_id: str
    answer: str
    steps: int
