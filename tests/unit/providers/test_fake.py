import pytest

from agent_foundations.domain.errors import FakeModelExhaustedError
from agent_foundations.domain.messages import Message, Role
from agent_foundations.domain.model import ModelRequest, ModelResponse
from agent_foundations.providers.fake import FakeModelProvider


@pytest.mark.asyncio
async def test_fake_model_returns_scripted_responses_and_records_requests() -> None:
    provider = FakeModelProvider([ModelResponse(content="done")])
    request = ModelRequest(messages=(Message(role=Role.USER, content="inspect"),))

    assert await provider.complete(request) == ModelResponse(content="done")
    assert provider.requests == [request]


@pytest.mark.asyncio
async def test_fake_model_fails_when_script_is_exhausted() -> None:
    provider = FakeModelProvider([])
    request = ModelRequest(messages=(Message(role=Role.USER, content="inspect"),))

    with pytest.raises(FakeModelExhaustedError):
        await provider.complete(request)
