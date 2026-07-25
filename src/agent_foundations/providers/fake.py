from collections import deque

from agent_foundations.domain.errors import FakeModelExhaustedError
from agent_foundations.domain.model import ModelRequest, ModelResponse


class FakeModelProvider:
    def __init__(self, responses: list[ModelResponse]) -> None:
        self._responses = deque(responses)
        self.requests: list[ModelRequest] = []

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if not self._responses:
            raise FakeModelExhaustedError("fake model response script is exhausted")
        return self._responses.popleft()
