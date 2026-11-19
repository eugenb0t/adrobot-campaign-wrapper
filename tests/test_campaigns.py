from app import main
import asyncio
import time


def wait_for_sync(client, keitaro_id):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        response = client.get("/api/campaigns")
        if any(row["keitaro_id"] == keitaro_id for row in response.json()):
            return response
        time.sleep(0.01)
    raise AssertionError("Keitaro sync did not finish")


def test_campaign_crud_and_offer_editor(client):
    created = client.post("/api/campaigns", json={
        "name": "test_novikov_flow",
        "country_code": "se",
        "offer_id": 184,
        "domain_id": None,
        "group_id": None,
        "traffic_source_id": None,
    })
    assert created.status_code == 201
    campaign = created.json()
    assert campaign["country_code"] == "SE"
    assert campaign["offers"] == [184]

    updated = client.put(f"/api/campaigns/{campaign['id']}/offers", json={"offer_ids": [219, 184, 307]})
    assert updated.status_code == 200
    assert updated.json()["offers"] == [219, 184, 307]
    assert updated.json()["offer_id"] == 219

    paused = client.patch(f"/api/campaigns/{campaign['id']}", json={"status": "paused"})
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"
    assert client.get("/api/campaigns", params={"q": "novikov"}).json()[0]["id"] == campaign["id"]

    deleted = client.delete(f"/api/campaigns/{campaign['id']}")
    assert deleted.status_code == 204
    assert client.get("/api/campaigns").json() == []


def test_campaign_validation_rejects_missing_test_prefix(client):
    response = client.post("/api/campaigns", json={
        "name": "summer_flow",
        "country_code": "SE",
        "offer_id": 184,
    })
    assert response.status_code == 422


def test_keitaro_campaign_sync_imports_campaigns_and_report_without_stream_fanout(client, monkeypatch):
    calls = []

    class FakeKeitaro:
        configured = True
        statistics_available = None

        async def list_campaigns(self):
            calls.append("campaigns")
            return [{"id": 912, "name": "test_existing_campaign", "state": "active"}]

        async def campaign_streams(self, campaign_id):
            raise AssertionError("campaign list sync should not request streams")

        async def campaign_report(self):
            calls.append("report")
            return {"rows": [{"campaign_id": 912, "clicks": 1250, "conversions": 75, "revenue": "825.50", "cost": "300.00"}]}

    monkeypatch.setattr(main, "keitaro", FakeKeitaro())
    response = client.get("/api/campaigns")
    assert response.status_code == 200
    response = wait_for_sync(client, 912)
    campaign = response.json()[0]
    assert campaign["keitaro_id"] == 912
    assert campaign["country_code"] is None
    assert campaign["offer_id"] is None
    assert campaign["offers"] == []
    assert campaign["visits"] == 1250
    assert campaign["conversions"] == 75
    assert campaign["profit"] == 525.5
    assert campaign["roi"] == 175.2
    assert main.keitaro.statistics_available is True
    assert client.get("/api/campaigns").status_code == 200
    assert calls == ["campaigns", "report"]


def test_keitaro_sync_does_not_block_campaign_list(client, monkeypatch):
    class SlowKeitaro:
        configured = True
        statistics_available = None

        async def list_campaigns(self):
            await asyncio.sleep(0.25)
            return [{"id": 914, "name": "test_slow_campaign", "state": "active"}]

        async def campaign_report(self):
            return {"rows": []}

    monkeypatch.setattr(main, "keitaro", SlowKeitaro())
    response = client.get("/api/campaigns")
    assert response.status_code == 200
    assert response.json() == []
    assert client.get("/api/health").json()["sync_in_progress"] is True
    result = wait_for_sync(client, 914)
    assert result.json()[0]["name"] == "test_slow_campaign"


def test_groups_resource_uses_campaign_group_type(client, monkeypatch):
    class FakeKeitaro:
        configured = True

        async def resources(self, path, *, params=None):
            assert path == "groups"
            assert params == {"type": "campaigns"}
            return [{"id": 7, "name": "QA"}]

    monkeypatch.setattr(main, "keitaro", FakeKeitaro())
    response = client.get("/api/resources/groups")
    assert response.status_code == 200
    assert response.json() == [{"id": 7, "name": "QA"}]


def test_campaign_detail_loads_streams_on_demand(client, monkeypatch):
    class FakeKeitaro:
        configured = True
        statistics_available = None

        async def list_campaigns(self):
            return [{"id": 913, "name": "test_partial_campaign", "state": "active"}]

        async def campaign_streams(self, campaign_id):
            assert campaign_id == 913
            return [
                {"type": "regular", "filters": [{"name": "country", "payload": ["DE"]}], "offers": []},
                {"type": "default", "filters": [], "offers": [{"offer_id": 412}]},
            ]

        async def campaign_report(self):
            return {"rows": []}

    monkeypatch.setattr(main, "keitaro", FakeKeitaro())
    response = client.get("/api/campaigns")
    assert response.status_code == 200
    response = wait_for_sync(client, 913)
    campaign = response.json()[0]
    assert campaign["keitaro_id"] == 913
    assert campaign["offers"] == []
    detail = client.get(f"/api/campaigns/{campaign['id']}")
    assert detail.status_code == 200
    assert detail.json()["offers"] == [412]
    assert detail.json()["country_code"] == "DE"
