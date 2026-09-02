from __future__ import annotations

from typing import Any

import httpx
from typing_extensions import Self

from backend.app.config import Settings


class SupabaseAuditRepository:
    async def event(self, trace_id: str, sequence: int) -> dict[str, Any] | None:
        response = await self.client.get(
            f"{self.base}/system_events",
            params={"select": "*", "trace_id": f"eq.{trace_id}", "sequence": f"eq.{sequence}"},
            headers=self.headers,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list) or len(data) > 1:
            raise RuntimeError("Malformed audit event response")
        return data[0] if data else None

    async def claim(self, trace_id: str, payload: dict[str, Any]) -> None:
        """Immutable INSERT: UNIQUE(trace_id, sequence) arbitrates all replicas/restarts.

        An HTTP error or uncertain response never authorizes submission. Never upsert/delete.
        """
        response = await self.client.post(
            f"{self.base}/system_events",
            json={"trace_id": trace_id, "sequence": 0, "kind": "submission_claimed",
                  "payload": payload, "paper": True},
            headers={**self.headers, "Prefer": "return=representation"},
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list) or len(data) != 1 or data[0].get("sequence") != 0:
            raise RuntimeError("Submission claim was not confirmed; execution forbidden")

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise RuntimeError("Supabase server configuration is missing")
        self.base = f"{str(settings.supabase_url).rstrip('/')}/rest/v1"
        key = settings.supabase_service_role_key.get_secret_value()
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        self.client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def insert(
        self, table: str, row: dict[str, Any], *, on_conflict: str | None = None
    ) -> dict[str, Any]:
        params = {"on_conflict": on_conflict} if on_conflict else None
        response = await self.client.post(
            f"{self.base}/{table}",
            params=params,
            json=row,
            headers={**self.headers, "Prefer": "return=representation,resolution=merge-duplicates"},
        )
        response.raise_for_status()
        data = response.json()
        return data[0] if isinstance(data, list) and data else row

    async def latest(self, table: str, trace_id: str | None = None) -> dict[str, Any] | None:
        params: dict[str, str] = {"select": "*", "order": "created_at.desc", "limit": "1"}
        if trace_id:
            params["trace_id"] = f"eq.{trace_id}"
        response = await self.client.get(f"{self.base}/{table}", params=params, headers=self.headers)
        response.raise_for_status()
        data = response.json()
        return data[0] if isinstance(data, list) and data else None

    async def timeline(self, trace_id: str) -> list[dict[str, Any]]:
        response = await self.client.get(
            f"{self.base}/system_events",
            params={"select": "*", "trace_id": f"eq.{trace_id}", "order": "sequence.asc"},
            headers=self.headers,
        )
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []
