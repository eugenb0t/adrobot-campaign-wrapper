import asyncio
import json

import httpx

from app.keitaro import KeitaroClient


def test_create_campaign_builds_geo_and_fallback_streams():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, request.url.path, body))
        if request.url.path.endswith("/campaigns"):
            return httpx.Response(201, json={"id": 712, "name": "test_novikov_api"})
        return httpx.Response(201, json={"id": len(calls)})

    async def run():
        client = KeitaroClient()
        client.configured = True
        client._client = httpx.AsyncClient(
            base_url="https://keitaro.test/admin_api/v1/",
            transport=httpx.MockTransport(handler),
        )
        result = await client.create_campaign({
            "name": "test_novikov_api",
            "country_code": "SE",
            "offer_id": 184,
            "domain_id": 4,
            "group_id": 2,
            "traffic_source_id": 3,
        })
        await client.close()
        return result

    assert asyncio.run(run())["id"] == 712
    campaign_call, geo_call, fallback_call = calls
    assert campaign_call[0:2] == ("POST", "/admin_api/v1/campaigns")
    assert campaign_call[2]["domain_id"] == 4
    assert campaign_call[2]["group_id"] == 2
    assert campaign_call[2]["traffic_source_id"] == 3
    assert geo_call[2]["filters"] == [{"name": "country", "mode": "allow", "payload": ["SE"]}]
    assert geo_call[2]["action_payload"] == "https://www.google.com/"
    assert fallback_call[2]["type"] == "regular"
    assert fallback_call[2]["schema"] == "landings"
    assert fallback_call[2]["offers"] == [{"offer_id": 184, "share": 100, "state": "active"}]


def test_update_offer_stream_preserves_equal_total_shares():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, request.url.path, body))
        if request.method == "GET":
            return httpx.Response(200, json=[{"id": 55, "type": "default", "offers": [{"offer_id": 9, "share": 100}]}])
        return httpx.Response(200, json={"id": 55})

    async def run():
        client = KeitaroClient()
        client.configured = True
        client._client = httpx.AsyncClient(
            base_url="https://keitaro.test/admin_api/v1/",
            transport=httpx.MockTransport(handler),
        )
        await client.update_campaign_offers(712, [11, 12, 13])
        await client.close()

    asyncio.run(run())
    assert calls[0][0:2] == ("GET", "/admin_api/v1/campaigns/712/streams")
    updated_offers = calls[1][2]["offers"]
    assert [offer["share"] for offer in updated_offers] == [34, 33, 33]
    assert sum(offer["share"] for offer in updated_offers) == 100


def test_list_campaigns_uses_limit_offset_until_last_page():
    requested = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append((request.url.params.get("limit"), request.url.params.get("offset")))
        offset = int(request.url.params.get("offset", 0))
        size = int(request.url.params.get("limit", 0))
        stop = min(offset + size, 205)
        return httpx.Response(200, json=[{"id": value} for value in range(offset, stop)])

    async def run():
        client = KeitaroClient()
        client.configured = True
        client._client = httpx.AsyncClient(
            base_url="https://keitaro.test/admin_api/v1/",
            transport=httpx.MockTransport(handler),
        )
        campaigns = await client.list_campaigns()
        await client.close()
        return campaigns

    campaigns = asyncio.run(run())
    assert len(campaigns) == 205
    assert requested == [("100", "0"), ("100", "100"), ("100", "200")]
