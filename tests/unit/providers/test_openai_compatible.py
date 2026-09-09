import json
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    RateLimitError,
)

from agent_foundations.domain._freeze import FrozenJSON
from agent_foundations.domain.errors import (
    InvalidModelResponseError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderTemporaryError,
    ProviderTimeoutError,
)
from agent_foundations.domain.messages import Message, Role
from agent_foundations.domain.model import ModelRequest
from agent_foundations.domain.tool import ToolCall, ToolDefinition
from agent_foundations.providers.openai_compatible import OpenAICompatibleProvider

# ── Fake client helpers ──────────────────────────────────────────────────


class FakeCompletions:
    def __init__(
        self,
        response: object = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> object:
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.response


def fake_client(completions: FakeCompletions) -> AsyncOpenAI:
    return cast(AsyncOpenAI, SimpleNamespace(chat=SimpleNamespace(completions=completions)))


# ── Error factories ───────────────────────────────────────────────────────


def _fake_request() -> httpx.Request:
    return httpx.Request("POST", "https://example.test/v1/chat/completions")


def _fake_response(status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, request=_fake_request())


def make_auth_error() -> AuthenticationError:
    return AuthenticationError(
        "bad key", response=_fake_response(401), body=None,
    )


def make_rate_limit_error() -> RateLimitError:
    return RateLimitError(
        "too many", response=_fake_response(429), body=None,
    )


def make_timeout_error() -> APITimeoutError:
    return APITimeoutError(request=_fake_request())


def make_connection_error() -> APIConnectionError:
    return APIConnectionError(message="refused", request=_fake_request())


def make_status_error() -> APIStatusError:
    return APIStatusError(
        "server error", response=_fake_response(500), body=None,
    )


# ── Conversion tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_converts_chat_completion_to_domain_response() -> None:
    """Full round-trip: SDK response → ModelResponse with tool_calls and usage."""
    message = SimpleNamespace(
        content=None,
        tool_calls=[
            SimpleNamespace(
                id="c1",
                function=SimpleNamespace(
                    name="read_file",
                    arguments='{"path":"README.md"}',
                ),
            ),
        ],
    )
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=message)],
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=4),
        model_dump=lambda mode: {"id": "response-1"},
    )
    completions = FakeCompletions(response=response)
    provider = OpenAICompatibleProvider(fake_client(completions), model="demo-model")

    result = await provider.complete(
        ModelRequest(messages=(Message(role=Role.USER, content="inspect"),))
    )

    # Tool calls were parsed
    assert result.tool_calls[0].id == "c1"
    assert result.tool_calls[0].name == "read_file"
    assert result.tool_calls[0].arguments == {"path": "README.md"}
    assert result.tool_calls[0].argument_parse_error is None
    assert isinstance(result.tool_calls[0].arguments, Mapping)

    # Usage extracted
    assert result.usage.input_tokens == 11
    assert result.usage.output_tokens == 4

    # raw_response preserved
    assert result.raw_response == {"id": "response-1"}

    # SDK kwargs
    assert completions.kwargs["model"] == "demo-model"
    assert "tools" not in completions.kwargs
    assert "tool_choice" not in completions.kwargs


@pytest.mark.asyncio
async def test_converts_all_messages_and_tool_definitions() -> None:
    """All four roles, name, tool_call_id, and FrozenJSON→dict/list conversion."""
    content_msg = SimpleNamespace(content="Hello")
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=content_msg)],
        usage=None,
        model_dump=lambda mode: {"id": "r2"},
    )
    completions = FakeCompletions(response=response)
    provider = OpenAICompatibleProvider(
        fake_client(completions), model="demo-model",
    )

    result = await provider.complete(
        ModelRequest(
            messages=(
                Message(role=Role.SYSTEM, content="You are helpful."),
                Message(role=Role.USER, content="inspect", name="caller"),
                Message(
                    role=Role.ASSISTANT,
                    content=None,
                    name="agent",
                    tool_calls=(
                        ToolCall(
                            id="assistant-call",
                            name="read_file",
                            arguments={
                                "path": "README.md",
                                "options": {"tags": ["a", "b"]},
                            },
                        ),
                    ),
                ),
                Message(
                    role=Role.TOOL,
                    content='{"ok":true}',
                    name="read_file",
                    tool_call_id="t1",
                ),
            ),
            tools=(
                ToolDefinition(
                    name="read_file",
                    description="Read a file.",
                    parameters=FrozenJSON({
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                        "additionalProperties": False,
                    }),
                ),
            ),
        )
    )

    kwargs = completions.kwargs
    messages = kwargs["messages"]

    # SYSTEM message
    assert messages[0] == {"role": "system", "content": "You are helpful."}

    # USER message with name
    assert messages[1] == {
        "role": "user", "content": "inspect", "name": "caller",
    }

    # ASSISTANT message — name and tool_calls preserved
    assert messages[2]["role"] == "assistant"
    assert messages[2]["content"] is None
    assert messages[2]["name"] == "agent"
    assistant_call = messages[2]["tool_calls"][0]
    assert assistant_call["id"] == "assistant-call"
    assert assistant_call["type"] == "function"
    assert assistant_call["function"]["name"] == "read_file"
    assert json.loads(assistant_call["function"]["arguments"]) == {
        "path": "README.md",
        "options": {"tags": ["a", "b"]},
    }

    # TOOL message — tool_call_id present
    assert messages[3] == {
        "role": "tool",
        "content": '{"ok":true}',
        "tool_call_id": "t1",
    }

    # Tool definitions: FrozenJSON → plain dict via to_json_value
    assert kwargs["tool_choice"] == "auto"
    assert kwargs["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a file.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
        },
    ]
    # Verify parameters are plain dict, not FrozenJSON
    assert isinstance(kwargs["tools"][0]["function"]["parameters"], dict)
    assert not isinstance(
        kwargs["tools"][0]["function"]["parameters"], FrozenJSON,
    )

    # Missing usage → tokens default to 0
    assert result.usage.input_tokens == 0
    assert result.usage.output_tokens == 0


# ── Error mapping tests ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("error_factory", "expected_type", "match_text"),
    [
        (make_auth_error, ProviderAuthenticationError, "authentication"),
        (make_rate_limit_error, ProviderRateLimitError, "rate limit"),
        (make_timeout_error, ProviderTimeoutError, "timed out"),
        (make_connection_error, ProviderTemporaryError, "connection failed"),
        (make_status_error, ProviderTemporaryError, "HTTP 500"),
    ],
)
@pytest.mark.asyncio
async def test_maps_sdk_errors_to_domain_errors(
    error_factory: Any,
    expected_type: type,
    match_text: str,
) -> None:
    """Each SDK error type is mapped to its domain counterpart."""
    sdk_error = error_factory()
    completions = FakeCompletions(error=sdk_error)
    provider = OpenAICompatibleProvider(
        fake_client(completions), model="demo-model",
    )

    with pytest.raises(expected_type, match=match_text) as exc_info:
        await provider.complete(
            ModelRequest(messages=(Message(role=Role.USER, content="inspect"),))
        )

    # Exception chaining preserves the original SDK error
    assert exc_info.value.__cause__ is sdk_error


@pytest.mark.asyncio
async def test_rate_limit_parses_retry_after_seconds() -> None:
    response = httpx.Response(
        429,
        headers={"Retry-After": "7"},
        request=_fake_request(),
    )
    sdk_error = RateLimitError("too many", response=response, body=None)
    provider = OpenAICompatibleProvider(
        fake_client(FakeCompletions(error=sdk_error)), model="demo-model",
    )
    with pytest.raises(ProviderRateLimitError) as exc_info:
        await provider.complete(
            ModelRequest(messages=(Message(role=Role.USER, content="inspect"),))
        )
    assert exc_info.value.retry_after_seconds == 7.0
    assert exc_info.value.__cause__ is sdk_error


# ── Malformed response tests ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_malformed_response_preserves_raw_response() -> None:
    """Empty choices stay InvalidModelResponseError and keep safe raw data."""
    response = SimpleNamespace(
        choices=[],
        usage=None,
        model_dump=lambda mode: {"id": "empty-choices"},
    )
    completions = FakeCompletions(response=response)
    provider = OpenAICompatibleProvider(
        fake_client(completions), model="demo-model",
    )

    with pytest.raises(InvalidModelResponseError, match="invalid response") as exc_info:
        await provider.complete(
            ModelRequest(messages=(Message(role=Role.USER, content="inspect"),))
        )

    assert exc_info.value.raw_response == {"id": "empty-choices"}


@pytest.mark.parametrize(
    ("raw_id", "call_id", "arguments"),
    [
        ("invalid-json", "invalid-json", "not-valid-json"),
        ("non-object", "non-object", "42"),
    ],
    ids=["invalid-json-arguments", "non-object-arguments"],
)
@pytest.mark.asyncio
async def test_malformed_tool_arguments_return_parse_error_call(
    raw_id: str,
    call_id: str,
    arguments: str,
) -> None:
    """Illegal arguments JSON must not raise; return a parse-error ToolCall."""
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id=call_id,
                            function=SimpleNamespace(
                                name="bad_tool",
                                arguments=arguments,
                            ),
                        ),
                    ],
                ),
            ),
        ],
        usage=None,
        model_dump=lambda mode: {"id": raw_id},
    )
    completions = FakeCompletions(response=response)
    provider = OpenAICompatibleProvider(
        fake_client(completions), model="demo-model",
    )

    result = await provider.complete(
        ModelRequest(messages=(Message(role=Role.USER, content="inspect"),))
    )

    assert result.raw_response == {"id": raw_id}
    assert len(result.tool_calls) == 1
    call = result.tool_calls[0]
    assert call.id == call_id
    assert call.name == "bad_tool"
    assert call.arguments == {}
    assert call.argument_parse_error is not None
    error = call.argument_parse_error
    assert "bad_tool" in error
    assert "pos" in error
    repair = (
        "Repair the JSON and call the same tool again; "
        "do not resend the identical broken string."
    )
    assert repair in error
    assert len(error) <= 512


@pytest.mark.asyncio
async def test_invalid_arguments_json_includes_position_and_window() -> None:
    """Node-3 shape: id+name present, arguments are illegal JSON."""
    broken = '{"changes":[{"path":"src/math.ts","diff":"@@' + ("x" * 300) + " not closed"
    try:
        json.loads(broken)
        raise AssertionError("fixture must be illegal JSON")
    except json.JSONDecodeError as exc:
        expected_pos = exc.pos
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="call-validate",
                            function=SimpleNamespace(
                                name="validate_patch",
                                arguments=broken,
                            ),
                        ),
                    ],
                ),
            ),
        ],
        usage=None,
        model_dump=lambda mode: {"id": "broken-args", "secret": "must-not-copy-full-raw"},
    )
    completions = FakeCompletions(response=response)
    provider = OpenAICompatibleProvider(
        fake_client(completions), model="demo-model",
    )

    result = await provider.complete(
        ModelRequest(messages=(Message(role=Role.USER, content="inspect"),))
    )

    call = result.tool_calls[0]
    assert call.arguments == {}
    error = call.argument_parse_error
    assert error is not None
    assert "validate_patch" in error
    assert "JSONDecodeError" in error
    assert f"pos {expected_pos}" in error
    repair = (
        "Repair the JSON and call the same tool again; "
        "do not resend the identical broken string."
    )
    assert repair in error
    assert broken not in error
    assert "must-not-copy-full-raw" not in error
    window_hits = [
        error[index:index + 8]
        for index in range(0, max(0, len(error) - 7))
        if error[index:index + 8] in broken
    ]
    assert window_hits, "error text must include a short window from the broken JSON"
    assert len(error) <= 512


@pytest.mark.asyncio
async def test_missing_tool_call_name_raises_invalid_model_response() -> None:
    """Any call missing id or name fail-closes the whole completion."""
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="ok",
                            function=SimpleNamespace(
                                name="read_file",
                                arguments='{"path":"README.md"}',
                            ),
                        ),
                        SimpleNamespace(
                            id="broken",
                            function=SimpleNamespace(
                                name=None,
                                arguments='{"path":"other"}',
                            ),
                        ),
                    ],
                ),
            ),
        ],
        usage=None,
        model_dump=lambda mode: {"id": "missing-name"},
    )
    completions = FakeCompletions(response=response)
    provider = OpenAICompatibleProvider(
        fake_client(completions), model="demo-model",
    )

    with pytest.raises(InvalidModelResponseError, match="invalid response") as exc_info:
        await provider.complete(
            ModelRequest(messages=(Message(role=Role.USER, content="inspect"),))
        )

    assert exc_info.value.raw_response == {"id": "missing-name"}
