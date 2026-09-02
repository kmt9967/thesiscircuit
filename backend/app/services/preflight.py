"""Durable two-stage authorization; no broker write is possible in this module."""

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from backend.app.models import Phase1Preflight
from backend.app.services.alpaca import OrderService
from backend.app.services.supabase import SupabaseAuditRepository

TRACE_ID = str(uuid5(NAMESPACE_URL, "thesiscircuit:phase1:official-opening"))
CURRENT_CANDIDATE = "SPY260904C00768000"
Builder = Callable[[Literal["readiness", "execution"], str], Awaitable[Phase1Preflight]]


class PreflightBlocked(RuntimeError):
    pass


class TwoStagePreflight:
    def __init__(self, repository: SupabaseAuditRepository, builder: Builder) -> None:
        self.repository = repository
        self.builder = builder

    async def unclaimed(self) -> None:
        if await self.repository.event(TRACE_ID, 0):
            raise PreflightBlocked("One-use submission already claimed; reconcile only")

    async def receipt(self, sequence: int, receipt_id: UUID | None) -> Phase1Preflight:
        row = await self.repository.event(TRACE_ID, sequence)
        if not row or receipt_id is None:
            raise PreflightBlocked("Both successful preflight receipts are required")
        receipt = Phase1Preflight.model_validate(row["payload"])
        expected = "READY_FOR_EXECUTION" if sequence == -2 else "APPROVED_FOR_SINGLE_ORDER"
        if (receipt.receipt_id != receipt_id or receipt.result != expected
                or receipt.stage != ("readiness" if sequence == -2 else "execution")
                or receipt.risk.decision != "APPROVED"
                or not all(check.passed for check in receipt.risk.checks)
                or not receipt.expires_at or receipt.expires_at <= datetime.now(timezone.utc)):
            raise PreflightBlocked("Preflight receipt invalid or expired; repeat both stages")
        return receipt

    async def store(self, preflight: Phase1Preflight, sequence: int, seconds: int) -> Phase1Preflight:
        preflight.receipt_id = uuid4()
        preflight.expires_at = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        await self.repository.insert(
            "system_events",
            {"trace_id": TRACE_ID, "sequence": sequence, "kind": f"{preflight.stage}_approved",
             "payload": preflight.model_dump(mode="json"), "paper": True},
            on_conflict="trace_id,sequence",
        )
        return preflight

    async def readiness(self) -> Phase1Preflight:
        await self.unclaimed()
        preflight = await self.builder("readiness", CURRENT_CANDIDATE)
        if preflight.result != "READY_FOR_EXECUTION":
            return preflight
        return await self.store(preflight, -2, 900)

    @staticmethod
    def same_candidate(before: Phase1Preflight, after: Phase1Preflight) -> None:
        if before.proposal.instrument != after.proposal.instrument:
            raise PreflightBlocked("Candidate changed; disable execution and repeat readiness")
        if after.proposal.limit_price > before.proposal.limit_price:
            raise PreflightBlocked("Premium increased; disable execution and repeat readiness")

    async def execution(self, readiness_id: UUID | None) -> Phase1Preflight:
        await self.unclaimed()
        ready = await self.receipt(-2, readiness_id)
        preflight = await self.builder("execution", ready.proposal.instrument)
        self.same_candidate(ready, preflight)
        preflight.readiness_id = readiness_id
        if preflight.result != "APPROVED_FOR_SINGLE_ORDER":
            return preflight
        return await self.store(preflight, -1, 60)

    async def submission_preflight(
        self, readiness_id: UUID | None, execution_id: UUID | None,
    ) -> Phase1Preflight:
        await self.unclaimed()
        ready = await self.receipt(-2, readiness_id)
        approved = await self.receipt(-1, execution_id)
        if approved.readiness_id != readiness_id:
            raise PreflightBlocked("Execution approval does not match readiness")
        # A third fresh read immediately before the immutable submission claim.
        fresh = await self.builder("execution", approved.proposal.instrument)
        self.same_candidate(ready, fresh)
        self.same_candidate(approved, fresh)
        if fresh.result != "APPROVED_FOR_SINGLE_ORDER":
            failed = [gate.name for gate in fresh.risk.checks if not gate.passed]
            raise PreflightBlocked(f"Submission recheck failed: {', '.join(failed)}")
        fresh.readiness_id = readiness_id
        fresh.receipt_id = execution_id
        return fresh

    async def claim(self, preflight: Phase1Preflight) -> None:
        await self.repository.claim(TRACE_ID, {
            "preflight": preflight.model_dump(mode="json"),
            "exact_order_payload": OrderService.payload(preflight.proposal),
        })
