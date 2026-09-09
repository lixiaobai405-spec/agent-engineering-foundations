import json
from collections.abc import Iterable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    RateLimitError,
)
from pydantic import ValidationError

from agent_foundations.domain._freeze import to_json_value
from agent_foundations.domain.errors import (
    InvalidModelResponseError,
    ProviderAuthenticationError,
    ProviderError,
    ProviderRateLimitError,
    ProviderTemporaryError,
    ProviderTimeoutError,
)
from agent_foundations.domain.messages import Message, Role
from agent_foundations.domain.model import ModelRequest, ModelResponse, TokenUsage
from agent_foundations.domain.tool import ToolCall

_PARSE_ERROR_LIMIT = 512
_PARSE_ERROR_MESSAGE_LIMIT = 160
_PARSE_ERROR_WINDOW = 80
_PARSE_ERROR_REPAIR = (
    "Repair the JSON and call the same tool again; "
    "do not resend the identical broken string."
)


def _json_error_window(raw_arguments: str, pos: int, size: int = _PARSE_ERROR_WINDOW) -> str:
    if not raw_arguments:
        return ""
    bounded_pos = min(max(pos, 0), len(raw_arguments))
    left = size // 2
    start = bounded_pos - left
    end = start + size
    if start < 0:
        end = min(len(raw_arguments), end - start)
        start = 0
    if end > len(raw_arguments):
        start = max(0, start - (end - len(raw_arguments)))
        end = len(raw_arguments)
    return raw_arguments[start:end]


def format_argument_parse_error(
    tool_name: str,
    error: BaseException,
    raw_arguments: str,
) -> str:
    pos = getattr(error, "pos", 0)
    if not isinstance(pos, int):
        pos = 0
    message = str(error)
    if len(message) > _PARSE_ERROR_MESSAGE_LIMIT:
        message = message[:_PARSE_ERROR_MESSAGE_LIMIT]
    window = _json_error_window(raw_arguments, pos)
    text = (
        f"{tool_name}: {type(error).__name__}: {message} at pos {pos} "
        f"near {window!r}. {_PARSE_ERROR_REPAIR}"
    )
    if len(text) <= _PARSE_ERROR_LIMIT:
        return text
    overflow = len(text) - _PARSE_ERROR_LIMIT
    if overflow < len(window):
        window = window[: len(window) - overflow]
        text = (
            f"{tool_name}: {type(error).__name__}: {message} at pos {pos} "
            f"near {window!r}. {_PARSE_ERROR_REPAIR}"
        )
    return text[:_PARSE_ERROR_LIMIT]


def _raw_arguments_text(arguments: object) -> str:
    if isinstance(arguments, str):
        return arguments
    if arguments is None:
        return ""
    try:
        return json.dumps(arguments, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(arguments)


def _tool_call_from_arguments(call_id: str, name: str, arguments: object) -> ToolCall:
    raw_text = _raw_arguments_text(arguments)
    loaded: object
    parse_error: str | None = None
    try:
        loaded = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        parse_error = format_argument_parse_error(name, exc, raw_text)
        loaded = {}
    except TypeError as exc:
        parse_error = format_argument_parse_error(name, exc, raw_text)
        loaded = {}
    else:
        if not isinstance(loaded, dict):
            type_error = TypeError(
                f"arguments must be a JSON object, got {type(loaded).__name__}",
            )
            parse_error = format_argument_parse_error(name, type_error, raw_text)
            loaded = {}
    if parse_error is None:
        return ToolCall(id=call_id, name=name, arguments=loaded)
    return ToolCall(
        id=call_id,
        name=name,
        arguments={},
        argument_parse_error=parse_error,
    )


def _parse_tool_calls(raw_calls: Iterable[object]) -> tuple[ToolCall, ...]:
    pending: list[tuple[str, str, object]] = []
    for call in raw_calls:
        function = getattr(call, "function", None)
        call_id = getattr(call, "id", None)
        name = getattr(function, "name", None) if function is not None else None
        arguments = getattr(function, "arguments", None) if function is not None else None
        if not isinstance(call_id, str) or not call_id or not isinstance(name, str) or not name:
            raise AttributeError("tool call missing id or name")
        pending.append((call_id, name, arguments))
    return tuple(
        _tool_call_from_arguments(call_id, name, arguments)
        for call_id, name, arguments in pending
    )


def parse_retry_after_seconds(response: object | None) -> float | None:
    if response is None:
        return None
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    raw = headers.get("retry-after")
    if raw is None:
        raw = headers.get("Retry-After")
    if raw is None:
        return None
    text = str(raw).strip()
    try:
        return max(0.0, float(text))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(text)
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        return max(0.0, (when - datetime.now(UTC)).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None


class OpenAICompatibleProvider:
    def __init__(self, client: AsyncOpenAI, model: str) -> None:
        self._client = client
        self._model = model

    async def complete(self, request: ModelRequest) -> ModelResponse:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": [
                self._message(message)
                for message in request.messages
            ],
        }
        if request.tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": to_json_value(tool.parameters),
                    },
                }
                for tool in request.tools
            ]
            kwargs["tool_choice"] = "auto"
        try:
            response = await self._client.chat.completions.create(**kwargs)
        except AuthenticationError as exc:
            raise ProviderAuthenticationError(
                "provider authentication failed"
            ) from exc
        except RateLimitError as exc:
            raise ProviderRateLimitError(
                "provider rate limit exceeded",
                retry_after_seconds=parse_retry_after_seconds(
                    getattr(exc, "response", None),
                ),
            ) from exc
        except APITimeoutError as exc:
            raise ProviderTimeoutError(
                "provider request timed out"
            ) from exc
        except APIConnectionError as exc:
            raise ProviderTemporaryError("provider connection failed") from exc
        except APIStatusError as exc:
            if exc.status_code in {500, 502, 503, 504}:
                raise ProviderTemporaryError(
                    f"provider returned HTTP {exc.status_code}"
                ) from exc
            if exc.status_code == 429:
                raise ProviderRateLimitError(
                    "provider rate limit exceeded",
                    retry_after_seconds=parse_retry_after_seconds(exc.response),
                ) from exc
            raise ProviderError(
                f"provider returned HTTP {exc.status_code}"
            ) from exc

        raw = self._raw_response(response)
        try:
            choice = response.choices[0].message
            calls = _parse_tool_calls(getattr(choice, "tool_calls", None) or [])
            usage = TokenUsage(
                input_tokens=response.usage.prompt_tokens if response.usage else 0,
                output_tokens=response.usage.completion_tokens if response.usage else 0,
            )
            return ModelResponse(
                content=choice.content,
                tool_calls=calls,
                usage=usage,
                raw_response=raw,
            )
        except InvalidModelResponseError:
            raise
        except (
            IndexError,
            AttributeError,
            TypeError,
            json.JSONDecodeError,
            ValidationError,
        ) as exc:
            raise InvalidModelResponseError(
                "provider returned an invalid response", raw_response=raw,
            ) from exc

    @staticmethod
    def _message(message: Message) -> dict[str, Any]:
        converted: dict[str, Any] = {
            "role": message.role.value,
            "content": message.content,
        }
        if message.name is not None and message.role is not Role.TOOL:
            converted["name"] = message.name
        if message.role is Role.ASSISTANT and message.tool_calls:
            converted["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(
                            to_json_value(call.arguments),
                            ensure_ascii=False,
                        ),
                    },
                }
                for call in message.tool_calls
            ]
        if message.role is Role.TOOL:
            converted["tool_call_id"] = message.tool_call_id
        return converted

    @staticmethod
    def _raw_response(response: object) -> dict[str, object] | None:
        model_dump = getattr(response, "model_dump", None)
        if not callable(model_dump):
            return None
        try:
            raw = model_dump(mode="json")
        except Exception:
            return None
        return raw if isinstance(raw, dict) else None
