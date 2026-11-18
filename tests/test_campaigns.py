from app import main


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


def test_keitaro_campaign_sync_imports_streams_and_report(client, monkeypatch):
    class FakeKeitaro:
        configured = True
        statistics_available = None

        async def list_campaigns(self):
            return [{"id": 912, "name": "test_existing_campaign", "state": "active"}]

        async def campaign_streams(self, campaign_id):
            assert campaign_id == 912
            return [
                {"type": "regular", "filters": [{"name": "country", "payload": ["DE"]}], "offers": []},
                {"type": "default", "filters": [], "offers": [{"offer_id": 412}]},
            ]

        async def campaign_report(self):
            return {"rows": [{"campaign_id": 912, "clicks": 1250, "conversions": 75, "revenue": "825.50", "cost": "300.00"}]}

    monkeypatch.setattr(main, "keitaro", FakeKeitaro())
    response = client.get("/api/campaigns")
    assert response.status_code == 200
    campaign = response.json()[0]
    assert campaign["keitaro_id"] == 912
    assert campaign["country_code"] == "DE"
    assert campaign["offers"] == [412]
    assert campaign["visits"] == 1250
    assert campaign["conversions"] == 75
    assert campaign["profit"] == 525.5
    assert campaign["roi"] == 175.2
    assert main.keitaro.statistics_available is True
