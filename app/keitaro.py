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
        self._client: httpx.AsyncClient | None = None
        self.statistics_available: bool | None = None

    async def open(self) -> None:
        if self.configured and self._client is None:
            self._client = httpx.AsyncClient(base_url=f"{self.base_url}/admin_api/v1/", headers=self.headers, timeout=settings.keitaro_timeout)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        if not self.configured:
            raise HTTPException(status_code=503, detail="Keitaro API не настроен. Заполните KEITARO_BASE_URL и KEITARO_API_KEY.")
        try:
            try:
                if self._client is not None:
                    response = await self._client.request(method, path.lstrip("/"), **kwargs)
                else:
                    async with httpx.AsyncClient(timeout=settings.keitaro_timeout) as client:
                        response = await client.request(method, f"{self.base_url}/admin_api/v1/{path.lstrip('/')}", headers=self.headers, **kwargs)
            except (httpx.TimeoutException, httpx.RemoteProtocolError):
                # Some tracker/proxy connections become stale after long sessions.
                # report/build is a read-only POST; retrying it cannot create a
                # duplicate remote resource. Other POST operations remain single-shot.
                read_only_post = method.upper() == "POST" and path.strip("/") == "report/build"
                if method.upper() not in {"GET", "PUT"} and not read_only_post:
                    raise
                async with httpx.AsyncClient(timeout=settings.keitaro_timeout) as client:
                    response = await client.request(method, f"{self.base_url}/admin_api/v1/{path.lstrip('/')}", headers=self.headers, **kwargs)
            response.raise_for_status()
            return response.json() if response.content else None
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise HTTPException(status_code=502, detail=f"{method} {path}: Keitaro API вернул {exc.response.status_code}: {detail}") from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"{method} {path}: не удалось связаться с Keitaro ({type(exc).__name__})") from exc

    async def resources(self, path: str, *, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        result = await self.request("GET", path, params=params)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            rows = result.get("data", result.get("offers", result.get("campaigns", [])))
            if isinstance(rows, list):
                return rows
        raise HTTPException(status_code=502, detail=f"Неожиданный формат ответа Keitaro для {path}")

    async def list_campaigns(self) -> list[dict[str, Any]]:
        # Keitaro can take a long time to return an unbounded campaign list.
        # Use the documented limit/offset parameters and collect every page.
        # Prefer efficient large pages, then shrink a page if an older record
        # makes that response too large for this tracker to return in time.
        page_size = 100
        campaigns: list[dict[str, Any]] = []
        offset = 0
        while True:
            try:
                page = await self.resources("campaigns", params={"limit": page_size, "offset": offset})
            except HTTPException as exc:
                if page_size > 1:
                    page_size = max(1, page_size // 2)
                    continue
                raise HTTPException(status_code=exc.status_code, detail=f"Не удалось загрузить кампанию начиная с позиции {offset}: {exc.detail}") from exc
            campaigns.extend(page)
            if len(page) < page_size:
                return campaigns
            offset += len(page)

    async def campaign_streams(self, campaign_id: int) -> list[dict[str, Any]]:
        return await self.resources(f"campaigns/{campaign_id}/streams")

    async def campaign_report(self) -> dict[str, Any]:
        result = await self.request("POST", "report/build", json={
            "range": {"interval": "all_time"},
            "grouping": ["campaign_id"],
            "metrics": ["clicks", "conversions", "revenue", "cost"],
        })
        if not isinstance(result, dict) or not isinstance(result.get("rows"), list):
            raise HTTPException(status_code=502, detail="Keitaro вернул отчёт в неожиданном формате")
        return result

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
                "state": "active",
                "position": 1,
                "schema": "redirect",
                "action_type": "http",
                "action_payload": "https://www.google.com/",
                "action_options": None,
                "offer_selection": "before_click",
                "landings": [],
                "offers": [],
                "weight": 0,
                "collect_clicks": True,
                "comments": "",
                "filter_or": False,
                "filters": [{"name": "country", "mode": "allow", "payload": [data["country_code"]]}],
                "triggers": [],
            })
            await self.request("POST", "streams", json={
                "campaign_id": campaign_id,
                "name": "Оффер · fallback",
                "type": "regular",
                "state": "active",
                "position": 2,
                "schema": "landings",
                "action_type": "http",
                "action_payload": None,
                "action_options": None,
                "offer_selection": "before_click",
                "landings": [],
                "collect_clicks": True,
                "comments": "",
                "filter_or": False,
                "filters": [],
                "triggers": [],
                "weight": 0,
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
        target = next((stream for stream in streams if stream.get("name") == "Оффер · fallback"), None)
        if target is None:
            target = next((stream for stream in streams if stream.get("type") == "default"), None)
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
