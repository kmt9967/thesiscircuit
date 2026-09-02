from backend.app.phase2.models import Cycle, Shadow, ShadowMark
from backend.app.services.supabase import SupabaseAuditRepository


class Phase2Repository(SupabaseAuditRepository):
    async def dispatcher_status(self) -> dict:
        response = await self.client.get(f"{self.base}/phase2_cycle_lease", headers=self.headers,
            params={"select":"cycle_id,expires_at,next_allowed_at,events", "singleton":"eq.true"})
        response.raise_for_status()
        rows=response.json()
        if len(rows)!=1:
            raise RuntimeError("Missing dispatcher singleton")
        row=rows[0]
        return {"cycle_id":row["cycle_id"],"expires_at":row["expires_at"],
                "next_allowed_at":row["next_allowed_at"],"events":row["events"][-20:],
                "mode":"DRY_RUN", "broker_dispatch_available":False}

    async def acquire_lease(self, owner: str, seconds: int, cycle_id: str) -> bool:
        response = await self.client.post(f"{self.base}/rpc/phase2_acquire_lease",
            json={"owner_id": owner, "lease_seconds": seconds, "requested_cycle":cycle_id}, headers=self.headers)
        response.raise_for_status()
        return response.json() is True

    async def release_lease(self, owner: str, outcome: str, cycle: Cycle | None = None) -> None:
        response = await self.client.post(f"{self.base}/rpc/phase2_release_lease",
            json={"owner_id": owner, "outcome":outcome,
                  "document":cycle.model_dump(mode="json") if cycle else None}, headers=self.headers)
        response.raise_for_status()
        if response.json() is not True:
            raise RuntimeError("Lease lost or expired; stale worker cannot complete cycle")

    async def save_cycle(self, cycle: Cycle) -> None:
        response = await self.client.post(
            f"{self.base}/rpc/phase2_save_cycle", json={"document": cycle.model_dump(mode="json")},
            headers=self.headers,
        )
        response.raise_for_status()
        if response.json() != str(cycle.id):
            raise RuntimeError("Atomic audit persistence not acknowledged")

    async def completed(self, cycle_id: str) -> bool:
        response = await self.client.get(f"{self.base}/autonomous_cycles", headers=self.headers,
                                         params={"id": f"eq.{cycle_id}", "select": "id"})
        response.raise_for_status()
        return bool(response.json())

    async def recent(self, table: str, limit: int = 100) -> list[dict]:
        if table not in {"autonomous_cycles", "shadow_trades", "shadow_marks", "agent_scores"}:
            raise ValueError("Unapproved research table")
        response = await self.client.get(f"{self.base}/{table}", headers=self.headers,
                                         params={"select": "*", "order": "created_at.desc", "limit": limit})
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list):
            raise TypeError("Malformed research collection")
        return rows

    async def history(self) -> tuple[list[Shadow], list[ShadowMark]]:
        shadows = [Shadow.model_validate(row["payload"]) for row in await self.recent("shadow_trades")]
        marks = [ShadowMark.model_validate(row["payload"]) for row in await self.recent("shadow_marks", 500)]
        return shadows, marks
