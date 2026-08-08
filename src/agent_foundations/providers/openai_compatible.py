import json
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
    ProviderTimeoutError,
)
from agent_foundations.domain.messages import Message, Role
from agent_foundations.domain.model import ModelRequest, ModelResponse, TokenUsage
from agent_foundations.domain.tool import ToolCall


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
                "provider rate limit exceeded"
            ) from exc
        except APITimeoutError as exc:
            raise ProviderTimeoutError(
                "provider request timed out"
            ) from exc
        except APIConnectionError as exc:
            raise ProviderError("provider connection failed") from exc
        except APIStatusError as exc:
            raise ProviderError(
                f"provider returned HTTP {exc.status_code}"
            ) from exc

        raw = self._raw_response(response)
        try:
            choice = response.choices[0].message
            calls = tuple(
                ToolCall(
                    id=call.id,
                    name=call.function.name,
                    arguments=json.loads(call.function.arguments),
                )
                for call in (getattr(choice, "tool_calls", None) or [])
            )
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
