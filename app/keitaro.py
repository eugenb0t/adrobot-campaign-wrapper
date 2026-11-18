from typing import Any
import re
from uuid import uuid4

import httpx
from fastapi import HTTPException

from app.settings import settings


class KeitaroClient:
    """Small API boundary; no credentials are stored in the database or browser."""

    def __init__(self) -> None:
        self.configured = bool(settings.keitaro_base_url and settings.keitaro_api_key)
        self.base_url = settings.keitaro_base_url.rstrip("/")
        self.headers = {"Api-Key": settings.keitaro_api_key}

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        if not self.configured:
            raise HTTPException(status_code=503, detail="Keitaro API не настроен. Заполните KEITARO_BASE_URL и KEITARO_API_KEY.")
        try:
            async with httpx.AsyncClient(timeout=settings.keitaro_timeout) as client:
                response = await client.request(method, f"{self.base_url}/admin_api/v1/{path.lstrip('/')}", headers=self.headers, **kwargs)
                response.raise_for_status()
                return response.json() if response.content else None
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise HTTPException(status_code=502, detail=f"Keitaro API вернул {exc.response.status_code}: {detail}") from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Не удалось связаться с Keitaro: {exc}") from exc

    async def resources(self, path: str) -> list[dict[str, Any]]:
        result = await self.request("GET", path)
        return result if isinstance(result, list) else result.get("data", result.get("offers", []))

    async def list_campaigns(self) -> list[dict[str, Any]]:
        return await self.resources("campaigns")

    async def campaign_streams(self, campaign_id: int) -> list[dict[str, Any]]:
        return await self.resources(f"campaigns/{campaign_id}/streams")

    async def campaign_report(self) -> dict[str, Any]:
        return await self.request("POST", "report/build", json={
            "range": {"interval": "all_time"},
            "grouping": ["campaign_id"],
            "metrics": ["clicks", "conversions", "revenue", "cost"],
        })

    async def create_campaign(self, data: dict[str, Any]) -> dict[str, Any]:
        campaign_payload = {
            "name": data["name"],
            "alias": f"{re.sub(r'[^a-z0-9-]+', '-', data['name'].lower()).strip('-')[:60]}-{uuid4().hex[:6]}",
            "state": "active",
            "type": "position",
            "group_id": data.get("group_id"),
            "domain_id": data.get("domain_id"),
            "traffic_source_id": data.get("traffic_source_id"),
        }
        created = await self.request("POST", "campaigns", json=campaign_payload)
        campaign_id = created.get("id") or created.get("campaign_id")
        if not campaign_id:
            raise HTTPException(status_code=502, detail="Keitaro создал кампанию, но не вернул её ID")
        try:
            await self.request("POST", "streams", json={
                "campaign_id": campaign_id,
                "name": "Google · выбранное GEO",
                "type": "regular",
                "position": 1,
                "schema": "redirect",
                "action_type": "http",
                "action_payload": "https://www.google.com/",
                "collect_clicks": True,
                "filter_or": False,
                "filters": [{"name": "country", "mode": "allow", "payload": [data["country_code"]]}],
            })
            await self.request("POST", "streams", json={
                "campaign_id": campaign_id,
                "name": "Оффер · fallback",
                "type": "default",
                "position": 2,
                "schema": "offers",
                "action_type": "http",
                "collect_clicks": True,
                "offers": [{"offer_id": data["offer_id"], "share": 100, "state": "active"}],
            })
        except HTTPException:
            # Avoid leaving an unusable campaign behind when stream setup fails.
            try:
                await self.request("DELETE", f"campaigns/{campaign_id}")
            except HTTPException:
                pass
            raise
        return created

    async def update_campaign_offers(self, campaign_id: int, offer_ids: list[int]) -> None:
        streams = await self.resources(f"campaigns/{campaign_id}/streams")
        target = next((stream for stream in streams if stream.get("type") == "default" or stream.get("name") == "Оффер · fallback"), None)
        if target is None:
            raise HTTPException(status_code=409, detail="В кампании не найден поток оффера")
        base_share, remainder = divmod(100, len(offer_ids))
        target["offers"] = [
            {"offer_id": offer_id, "share": base_share + (1 if index < remainder else 0), "state": "active"}
            for index, offer_id in enumerate(offer_ids)
        ]
        await self.request("PUT", f"streams/{target['id']}", json=target)

    async def update_campaign_state(self, campaign_id: int, state: str) -> None:
        action = "enable" if state == "active" else "disable"
        await self.request("POST", f"campaigns/{campaign_id}/{action}")

    async def delete_campaign(self, campaign_id: int) -> None:
        await self.request("DELETE", f"campaigns/{campaign_id}")


keitaro = KeitaroClient()
