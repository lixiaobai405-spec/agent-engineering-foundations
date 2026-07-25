class AgentFoundationsError(Exception):
    """Base class for expected runtime failures."""


class ProviderError(AgentFoundationsError):
    pass


class ProviderAuthenticationError(ProviderError):
    pass


class ProviderRateLimitError(ProviderError):
    pass


class ProviderTimeoutError(ProviderError):
    pass


class InvalidModelResponseError(ProviderError):
    def __init__(self, message: str, raw_response: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.raw_response = raw_response


class FakeModelExhaustedError(ProviderError):
    pass


class ToolError(AgentFoundationsError):
    pass


class UnknownToolError(ToolError):
    pass


class InvalidToolArgumentsError(ToolError):
    pass


class PathPolicyViolationError(ToolError):
    pass


class FileTooLargeError(ToolError):
    pass


class BinaryFileError(ToolError):
    pass


class ContextBudgetExceededError(AgentFoundationsError):
    pass


class MaxStepsExceededError(AgentFoundationsError):
    pass
