from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path

from agent_foundations.durable.lease import (
    LeaseConflictError,
    LeaseManager,
    LeaseNotExpiredError,
    LeaseNotFoundError,
)
from agent_foundations.durable.models import DurableRun, DurableRunStatus, RunLease
from agent_foundations.durable.repository import (
    DurableRepositoryError,
    DurableRunRepository,
)
from agent_foundations.runtime.agent import AgentResult
from agent_foundations.runtime.loop import AgentLoop
from agent_foundations.runtime.state_machine import (
    AgentRunState,
    CancellationToken,
    CheckpointReason,
    CheckpointSink,
    RunCancelledError,
)

Clock = Callable[[], datetime]
LoopFactory = Callable[[DurableRun], AgentLoop]

_RESUME_START_STATUSES = frozenset({
    DurableRunStatus.CREATED,
    DurableRunStatus.PAUSED,
    DurableRunStatus.WAITING_APPROVAL,
})


class RunCommand(StrEnum):
    RESUME = "resume"
    RETRY = "retry"
    CANCEL = "cancel"


class ControllerError(DurableRepositoryError):
    """Base durable run controller error."""


class ControllerRejectedError(ControllerError):
    """Controller rejected the requested command."""


class _RepositoryCancellationToken:
    def __init__(self, repository: DurableRunRepository, run_id: str) -> None:
        self._repository = repository
        self._run_id = run_id

    async def is_cancelled(self) -> bool:
        run = await self._repository.get_run(self._run_id)
        return run.status == DurableRunStatus.CANCELLED


class _RepositoryCheckpointSink:
    def __init__(
        self,
        repository: DurableRunRepository,
        run_id: str,
        lease_holder: list[RunLease],
        lease_manager: LeaseManager,
        lease_ttl: timedelta,
        clock: Clock,
        state_version_holder: list[int],
    ) -> None:
        self._repository = repository
        self._run_id = run_id
        self._lease_holder = lease_holder
        self._lease_manager = lease_manager
        self._lease_ttl = lease_ttl
        self._clock = clock
        self._state_version_holder = state_version_holder

    async def save(self, state: AgentRunState, reason: CheckpointReason) -> None:
        checked_at = self._clock().astimezone(UTC)
        lease = await self._lease_manager.renew(self._lease_holder[0], self._lease_ttl)
        self._lease_holder[0] = lease
        await self._repository.save_checkpoint(
            self._run_id,
            self._state_version_holder[0],
            state,
            lease=lease,
            checked_at=checked_at,
            expected_status=DurableRunStatus.RUNNING,
        )
        self._state_version_holder[0] += 1


class DurableRunController:
    def __init__(
        self,
        repository: DurableRunRepository,
        lease_manager: LeaseManager,
        loop_factory: LoopFactory,
        *,
        lease_ttl: timedelta,
        clock: Clock | None = None,
    ) -> None:
        self._repository = repository
        self._lease_manager = lease_manager
        self._loop_factory = loop_factory
        self._lease_ttl = lease_ttl
        self._clock: Clock = clock or (lambda: datetime.now(UTC))

    async def resume(self, run_id: str, owner_id: str) -> AgentResult:
        if not owner_id or not owner_id.strip():
            raise ControllerRejectedError("owner_id must not be blank")
        run = await self._repository.get_run(run_id)
        if run.status == DurableRunStatus.FAILED:
            raise ControllerRejectedError("failed runs must use retry")
        if run.status in {DurableRunStatus.COMPLETED, DurableRunStatus.CANCELLED}:
            raise ControllerRejectedError(f"cannot resume status {run.status.value}")
        checkpoint = await self._repository.load_latest_checkpoint(run_id)
        lease = await self._acquire_or_takeover(run_id, owner_id, run.status)
        if run.status in _RESUME_START_STATUSES:
            run = await self._repository.transition_status(
                run_id,
                run.status,
                DurableRunStatus.RUNNING,
                lease=lease,
                checked_at=self._clock().astimezone(UTC),
            )
        elif run.status == DurableRunStatus.RUNNING:
            pass
        else:
            raise ControllerRejectedError(f"cannot resume status {run.status.value}")
        return await self._execute_with_lease(run, checkpoint.state, lease)

    async def retry(self, run_id: str, owner_id: str) -> AgentResult:
        if not owner_id or not owner_id.strip():
            raise ControllerRejectedError("owner_id must not be blank")
        run = await self._repository.get_run(run_id)
        if run.status != DurableRunStatus.FAILED:
            raise ControllerRejectedError("retry requires failed status")
        checkpoint = await self._repository.load_latest_checkpoint(run_id)
        lease = await self._acquire_or_takeover(run_id, owner_id, run.status)
        checked_at = self._clock().astimezone(UTC)
        retry_checkpoint = await self._repository.begin_retry(
            run_id,
            run.state_version,
            checkpoint.state,
            lease=lease,
            checked_at=checked_at,
        )
        run = await self._repository.get_run(run_id)
        return await self._execute_with_lease(run, retry_checkpoint.state, lease)

    async def cancel(self, run_id: str, requested_by: str) -> DurableRun:
        if not requested_by or not requested_by.strip():
            raise ControllerRejectedError("requested_by must not be blank")
        return await self._repository.cancel_run(run_id)

    async def _acquire_or_takeover(
        self,
        run_id: str,
        owner_id: str,
        status: DurableRunStatus,
    ) -> RunLease:
        try:
            return await self._lease_manager.acquire(run_id, owner_id, self._lease_ttl)
        except LeaseConflictError:
            try:
                return await self._lease_manager.takeover_expired(
                    run_id,
                    owner_id,
                    self._lease_ttl,
                )
            except LeaseNotExpiredError:
                raise ControllerRejectedError(
                    "active lease conflict",
                ) from None
        except LeaseNotFoundError:
            if status == DurableRunStatus.RUNNING:
                raise ControllerRejectedError("active lease conflict") from None
            raise

    async def _execute_with_lease(
        self,
        run: DurableRun,
        state: AgentRunState,
        lease: RunLease,
    ) -> AgentResult:
        state_version_holder = [run.state_version]
        lease_holder = [lease]
        sink: CheckpointSink = _RepositoryCheckpointSink(
            self._repository,
            run.run_id,
            lease_holder,
            self._lease_manager,
            self._lease_ttl,
            self._clock,
            state_version_holder,
        )
        token: CancellationToken = _RepositoryCancellationToken(
            self._repository,
            run.run_id,
        )
        loop = self._loop_factory(run)
        try:
            result = await loop.resume(
                Path(run.project_root),
                run.run_id,
                state,
                checkpoint_sink=sink,
                cancellation_token=token,
            )
            checked_at = self._clock().astimezone(UTC)
            active_lease = lease_holder[0]
            active_lease = await self._lease_manager.renew(active_lease, self._lease_ttl)
            await self._repository.transition_status(
                run.run_id,
                DurableRunStatus.RUNNING,
                DurableRunStatus.COMPLETED,
                lease=active_lease,
                checked_at=checked_at,
            )
            await self._lease_manager.release(active_lease)
            return result
        except RunCancelledError:
            await self._lease_manager.release(lease_holder[0])
            raise
        except Exception:
            checked_at = self._clock().astimezone(UTC)
            active_lease = lease_holder[0]
            try:
                active_lease = await self._lease_manager.renew(active_lease, self._lease_ttl)
                await self._repository.transition_status(
                    run.run_id,
                    DurableRunStatus.RUNNING,
                    DurableRunStatus.FAILED,
                    lease=active_lease,
                    checked_at=checked_at,
                )
            except Exception:
                pass
            await self._lease_manager.release(active_lease)
            raise
        except BaseException:
            raise
