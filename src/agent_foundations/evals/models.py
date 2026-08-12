import unicodedata
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from agent_foundations.domain._model import ValidatedCopyModel


class EvalAssertionKind(StrEnum):
    ANSWER_CONTAINS = "answer_contains"
    ANSWER_EXCLUDES = "answer_excludes"
    TOOL_CALLED = "tool_called"
    TOOL_NOT_CALLED = "tool_not_called"
    ERROR_CODE = "error_code"


def _validate_project_fixture(value: str) -> str:
    if not value or any(unicodedata.category(character) == "Cc" for character in value):
        raise ValueError("project_fixture must be a safe relative path")
    normalized = value.replace("\\", "/")
    if normalized.startswith("//") or normalized.startswith("\\\\"):
        raise ValueError("project_fixture must be a safe relative path")
    if normalized.startswith(("\\\\?\\", "\\\\.\\")):
        raise ValueError("project_fixture must be a safe relative path")
    path = Path(value)
    if not path.parts or path.drive or path.is_absolute() or path.anchor:
        raise ValueError("project_fixture must be a safe relative path")
    if ".." in path.parts:
        raise ValueError("project_fixture must be a safe relative path")
    return path.as_posix()


class EvalAssertion(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True)

    kind: EvalAssertionKind
    value: str


class EvalTask(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True)

    task_id: str
    project_fixture: str
    prompt: str
    assertions: tuple[EvalAssertion, ...]
    max_steps: int = Field(ge=1)
    tags: tuple[str, ...] = ()

    @field_validator("project_fixture")
    @classmethod
    def validate_project_fixture(cls, value: str) -> str:
        return _validate_project_fixture(value)

    @model_validator(mode="after")
    def validate_non_empty_assertions(self) -> "EvalTask":
        if not self.assertions:
            raise ValueError("assertions must not be empty")
        return self


class EvalTaskSet(ValidatedCopyModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1]
    dataset_id: str
    dataset_version: str
    tasks: tuple[EvalTask, ...]
