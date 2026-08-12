"""Durable run persistence and versioned checkpoints."""

from typing import Any

from agent_foundations.durable.effects import (
    EffectResolutionRequiredError,
    SideEffectLedger,
    compute_idempotency_key,
    compute_intent_digest,
    normalize_tool_arguments,
)
from agent_foundations.durable.faults import (
    CrashPoint,
    FaultInjector,
    InjectedCrash,
    PointFaultInjector,
)
from agent_foundations.durable.lease import (
    InvalidLeaseClockError,
    InvalidLeaseTTLError,
    LeaseConflictError,
    LeaseExpiredError,
    LeaseManager,
    LeaseNotExpiredError,
    LeaseNotFoundError,
    LeaseTokenMismatchError,
)
from agent_foundations.durable.models import (
    DurableRun,
    DurableRunStatus,
    EffectStatus,
    RunCheckpoint,
    RunLease,
    RunState,
    SideEffectIntent,
    SideEffectRecord,
)
from agent_foundations.durable.repository import (
    CheckpointNotFoundError,
    DurableRepositoryError,
    DurableRunAlreadyExistsError,
    DurableRunNotFoundError,
    DurableRunRepository,
    DurableRunStatusConflictError,
    EffectNotFoundError,
    EffectOwnerConflictError,
    EffectStatusConflictError,
    ExecutionFactRunMismatchError,
    IdempotencyConflictError,
    InvalidLeaseWriteParametersError,
    LeaseWriteRejectedError,
    StateVersionConflictError,
    UnsupportedCheckpointSchemaVersionError,
)


def __getattr__(name: str) -> Any:
    if name == "IdempotentToolCallExecutor":
        from agent_foundations.runtime.tool_execution import IdempotentToolCallExecutor

        return IdempotentToolCallExecutor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "CheckpointNotFoundError",
    "CrashPoint",
    "DurableRepositoryError",
    "DurableRun",
    "DurableRunAlreadyExistsError",
    "DurableRunNotFoundError",
    "DurableRunRepository",
    "DurableRunStatus",
    "DurableRunStatusConflictError",
    "EffectNotFoundError",
    "EffectOwnerConflictError",
    "EffectResolutionRequiredError",
    "EffectStatus",
    "EffectStatusConflictError",
    "ExecutionFactRunMismatchError",
    "FaultInjector",
    "IdempotencyConflictError",
    "IdempotentToolCallExecutor",
    "InjectedCrash",
    "InvalidLeaseClockError",
    "InvalidLeaseTTLError",
    "InvalidLeaseWriteParametersError",
    "LeaseConflictError",
    "LeaseExpiredError",
    "LeaseManager",
    "LeaseNotExpiredError",
    "LeaseNotFoundError",
    "LeaseTokenMismatchError",
    "LeaseWriteRejectedError",
    "PointFaultInjector",
    "RunCheckpoint",
    "RunLease",
    "RunState",
    "SideEffectIntent",
    "SideEffectLedger",
    "SideEffectRecord",
    "StateVersionConflictError",
    "UnsupportedCheckpointSchemaVersionError",
    "compute_idempotency_key",
    "compute_intent_digest",
    "normalize_tool_arguments",
]
