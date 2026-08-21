from fastapi.testclient import TestClient

from ncaaf_engine.api.app import app

client = TestClient(app)


def test_health_exposes_blockers_and_synthetic_only():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["real_money_execution"] is False
    assert "independent_power_model" in body["blocked_features"]


def test_amm_quote_endpoint():
    r = client.post("/api/v0/amm/quote? q_yes=0&q_no=0".replace(" ", ""), json={"direction": "YES", "quantity": 25})
    assert r.status_code == 200
    body = r.json()
    assert body["probability_after"] > body["probability_before"]


def test_amm_order_limit():
    r = client.post("/api/v0/amm/quote", json={"direction": "YES", "quantity": 101})
    assert r.status_code == 422
