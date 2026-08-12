from __future__ import annotations

from enum import StrEnum


class CrashPoint(StrEnum):
    BEFORE_INTENT = "before_intent"
    AFTER_INTENT = "after_intent"
    AFTER_CLAIM = "after_claim"
    AFTER_EXECUTE = "after_execute"
    AFTER_COMMIT = "after_commit"


class InjectedCrash(RuntimeError):
    """Deterministic crash injected at a ledger boundary."""


class FaultInjector:
    """Default no-op fault injector for production paths."""

    def hit(self, point: CrashPoint) -> None:
        return None


class PointFaultInjector(FaultInjector):
    def __init__(self, crash_at: CrashPoint | None = None) -> None:
        self._crash_at = crash_at

    def hit(self, point: CrashPoint) -> None:
        if self._crash_at == point:
            raise InjectedCrash(point.value)
