"""Unit/integration tests for the DealerLot API (Flask test client)."""


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"


def test_seed_inventory_and_stats(client):
    data = client.get("/api/vehicles").get_json()
    assert data["stats"]["total"] == 12
    assert data["stats"]["available"] == 10
    assert data["stats"]["sold"] == 2
    # every vehicle is enriched with a market assessment
    for v in data["vehicles"]:
        assert v["market_state"] in ("over", "under", "at")
        assert "est_value" in v and "condition_label" in v


def test_designed_market_mix(client):
    """The seed should reproduce the design: 4 over, 2 under, 4 at (available)."""
    stats = client.get("/api/vehicles").get_json()["stats"]
    assert stats["over_market"] == 4
    assert stats["room_to_raise"] == 2


def test_condition_labels(client):
    labels = {v["condition_label"] for v in client.get("/api/vehicles").get_json()["vehicles"]}
    assert labels <= {"Poor", "Fair", "Good", "Great", "Mint"}


def test_create_enriches_and_delete(client):
    payload = {"make": "Kia", "model": "Sportage", "year": 2021,
               "mileage": 40000, "condition": 4, "accidents": 0, "asking_price": 21500}
    r = client.post("/api/vehicles", json=payload)
    assert r.status_code == 201
    body = r.get_json()
    assert body["market_state"] in ("over", "under", "at")
    vid = body["id"]
    assert client.delete(f"/api/vehicles/{vid}").status_code == 204
    assert client.get(f"/api/vehicles/{vid}").status_code == 404


def test_validation_rejects_bad_year(client):
    bad = {"make": "Kia", "model": "X", "year": 1800, "mileage": 1,
           "condition": 4, "accidents": 0, "asking_price": 1000}
    r = client.post("/api/vehicles", json=bad)
    assert r.status_code == 400
    assert "year" in r.get_json()["error"]


def test_mark_sold(client):
    vid = client.get("/api/vehicles").get_json()["vehicles"][0]["id"]
    r = client.post(f"/api/vehicles/{vid}/sold")
    assert r.get_json()["status"] == "sold"


def test_valuation_endpoint(client):
    r = client.post("/api/valuation", json={"make": "BMW", "year": 2018,
                    "mileage": 64000, "condition": 3, "accidents": 1})
    body = r.get_json()
    assert r.status_code == 200
    assert body["low"] <= body["estimate"] <= body["high"]


def test_overpriced_car_flagged_over(client):
    """A car priced well above its market value must be flagged 'over'."""
    r = client.post("/api/vehicles", json={"make": "Honda", "model": "Fit",
        "year": 2015, "mileage": 120000, "condition": 2, "accidents": 0,
        "asking_price": 40000})  # absurdly high asking
    assert r.get_json()["market_state"] == "over"


def test_frontend_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"DealerLot" in r.data
