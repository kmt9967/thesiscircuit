from __future__ import annotations

from typing import Any

import httpx
from typing_extensions import Self

from backend.app.config import Settings


class SupabaseAuditRepository:
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
