class ChatError(Exception):
    """Base error for deterministic Chat control-plane failures."""


class ChatNotFoundError(ChatError):
    pass


class ChatConflictError(ChatError):
    pass


class ApprovalUnavailableError(ChatConflictError):
    pass
