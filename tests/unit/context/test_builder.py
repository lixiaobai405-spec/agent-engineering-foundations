import pytest

from agent_foundations.context.budget import ContextBudget
from agent_foundations.context.builder import ContextBuilder
from agent_foundations.domain.errors import ContextBudgetExceededError
from agent_foundations.domain.messages import Message, Role


def test_builder_keeps_system_and_latest_user_message() -> None:
    builder = ContextBuilder(ContextBudget(max_chars=45, max_tool_result_chars=12))
    messages = (
        Message(role=Role.SYSTEM, content="You are read-only."),
        Message(role=Role.USER, content="old request"),
        Message(role=Role.TOOL, content="abcdefghijklmnopqrstuvwxyz", tool_call_id="c1"),
        Message(role=Role.USER, content="latest request"),
    )

    result = builder.build(messages)

    assert result[0].role is Role.SYSTEM
    assert result[-1].content == "latest request"
    assert all(message.content != "old request" for message in result)
    assert any(message.content == "abcdefghi..." for message in result)


def test_builder_does_not_mutate_source_messages() -> None:
    source = Message(role=Role.TOOL, content="123456", tool_call_id="c1")
    ContextBuilder(ContextBudget(max_chars=100, max_tool_result_chars=4)).build((source,))
    assert source.content == "123456"


@pytest.mark.parametrize(
    "limit,expected",
    [
        (1, "."),
        (2, ".."),
        (3, "..."),
        (4, "a..."),
    ],
)
def test_tool_truncation_respects_hard_limit(limit: int, expected: str) -> None:
    builder = ContextBuilder(ContextBudget(max_chars=1000, max_tool_result_chars=limit))
    messages = (
        Message(role=Role.TOOL, content="abcde", tool_call_id="c1"),
    )

    result = builder.build(messages)

    tool_msg = result[0]
    assert tool_msg.content == expected
    assert len(tool_msg.content) <= limit


def test_system_message_exceeding_max_chars_raises() -> None:
    builder = ContextBuilder(ContextBudget(max_chars=10, max_tool_result_chars=100))
    messages = (
        Message(
            role=Role.SYSTEM,
            content="This system message is far too long for the tiny budget",
        ),
    )

    with pytest.raises(ContextBudgetExceededError):
        builder.build(messages)


def test_mandatory_items_exceeding_max_chars_raises() -> None:
    builder = ContextBuilder(ContextBudget(max_chars=40, max_tool_result_chars=100))
    messages = (
        Message(role=Role.SYSTEM, content="You are a helpful assistant."),
        Message(role=Role.USER, content="This is the latest request"),
    )

    with pytest.raises(ContextBudgetExceededError):
        builder.build(messages)
