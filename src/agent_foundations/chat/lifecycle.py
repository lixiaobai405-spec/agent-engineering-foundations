from __future__ import annotations

import logging
from typing import Literal

logger = logging.getLogger("agent_foundations.chat.lifecycle")

SSE_CLIENT_DISCONNECT = "sse cancelled: client disconnect"
SSE_LIFESPAN_CANCEL = "sse cancelled: lifespan shutdown"
SSE_FAILED = "sse failed"
CHAT_LIFESPAN_SHUTDOWN = "chat lifespan shutdown"

SseSource = Literal["chat", "trace"]


def is_shutting_down(request: object) -> bool:
    scope = getattr(request, "scope", None)
    if not isinstance(scope, dict):
        return False
    app = scope.get("app")
    if app is None:
        return False
    state = getattr(app, "state", None)
    return bool(getattr(state, "chat_shutting_down", False))


def log_sse_cancelled(request: object, source: SseSource) -> None:
    if is_shutting_down(request):
        logger.info("%s (%s)", SSE_LIFESPAN_CANCEL, source)
    else:
        logger.debug("%s (%s)", SSE_CLIENT_DISCONNECT, source)


def log_sse_failed(exc: BaseException, source: SseSource) -> None:
    logger.error(
        "%s (%s) (%s)",
        SSE_FAILED,
        type(exc).__name__,
        source,
        exc_info=exc,
    )


def mark_lifespan_shutdown(app: object | None) -> None:
    if app is not None:
        state = getattr(app, "state", None)
        if state is not None:
            state.chat_shutting_down = True
    logger.info(CHAT_LIFESPAN_SHUTDOWN)
