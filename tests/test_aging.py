"""Tests for the Aging & Holding-Cost Intelligence feature (PRD-01 / SPEC-01).

Unit tests use AgingService directly (no Flask, no DB).
Integration tests use the Flask test client (via the conftest fixture).
"""
from datetime import date, timedelta

import pytest

from core.aging import AgingService, _aging_band


# ---------------------------------------------------------------------------
# Unit: band boundaries
# ---------------------------------------------------------------------------

def test_band_boundaries():
    assert _aging_band(0)  == "Fresh"
    assert _aging_band(30) == "Fresh"
    assert _aging_band(31) == "Aging"
    assert _aging_band(45) == "Aging"
    assert _aging_band(46) == "Stale"
    assert _aging_band(60) == "Stale"
    assert _aging_band(61) == "Critical"
    assert _aging_band(99) == "Critical"


# ---------------------------------------------------------------------------
# Unit: days-on-lot math
# ---------------------------------------------------------------------------

class _FakeVehicle:
    """Minimal stand-in so AgingService doesn't need real Vehicle objects."""
    def __init__(self, intake_days_ago, asking_price, cost_basis=None):
        self.intake_date = (date.today() - timedelta(days=intake_days_ago)).isoformat()
        self.asking_price = asking_price
        self.cost_basis = cost_basis


_VALUATION = {"est_value": 15000, "est_low": 12000, "est_high": 16000}


def test_days_on_lot_math():
    svc = AgingService()
    result = svc.evaluate(_FakeVehicle(10, 15000), _VALUATION)
    assert result["days_on_lot"] == 10


def test_days_on_lot_today_is_fresh():
    svc = AgingService()
    result = svc.evaluate(_FakeVehicle(0, 15000), _VALUATION)
    assert result["days_on_lot"] == 0
    assert result["aging_band"] == "Fresh"


# ---------------------------------------------------------------------------
# Unit: holding cost formula
# ---------------------------------------------------------------------------

def test_holding_cost_known_inputs():
    # basis=10000, APR=0.12, overhead=10 → per_day = 10000*0.12/365 + 10 = 3.288 + 10 = 13.29
    svc = AgingService(apr=0.12, daily_overhead=10)
    v = _FakeVehicle(intake_days_ago=20, asking_price=12000, cost_basis=10000)
    result = svc.evaluate(v, _VALUATION)
    expected_per_day = round(10000 * 0.12 / 365 + 10, 2)
    expected_to_date = round(expected_per_day * 20, 2)
    assert result["holding_cost_per_day"] == expected_per_day
    assert result["holding_cost_to_date"] == expected_to_date


def test_null_cost_basis_uses_proxy():
    # cost_basis=None → uses est_value * 0.90 = 15000 * 0.9 = 13500
    svc = AgingService(apr=0.09, daily_overhead=12)
    v = _FakeVehicle(intake_days_ago=10, asking_price=15000, cost_basis=None)
    result = svc.evaluate(v, _VALUATION)
    proxy_basis = round(15000 * 0.90)
    expected_per_day = round(proxy_basis * 0.09 / 365 + 12, 2)
    assert result["holding_cost_per_day"] == expected_per_day
    assert result["recommendation"] is None or isinstance(result["recommendation"], dict)


# ---------------------------------------------------------------------------
# Unit: markdown engine
# ---------------------------------------------------------------------------

def test_fresh_no_recommendation_when_slightly_over():
    # Fresh + asking only 5% over high → no rec (threshold is >10%)
    svc = AgingService()
    v = _FakeVehicle(intake_days_ago=10, asking_price=16700, cost_basis=14000)
    val = {"est_value": 15000, "est_low": 12000, "est_high": 16000}
    result = svc.evaluate(v, val)
    assert result["recommendation"] is None


def test_fresh_fires_when_far_over_market():
    # Fresh + asking 15% over high (18400 vs high 16000) → rec fires
    svc = AgingService()
    v = _FakeVehicle(intake_days_ago=10, asking_price=18400, cost_basis=14000)
    val = {"est_value": 15000, "est_low": 12000, "est_high": 16000}
    result = svc.evaluate(v, val)
    assert result["recommendation"] is not None
    assert result["recommendation"]["target_price"] < 18400


def test_critical_recommendation_respects_step_cap():
    # Critical age + asking $20,000 vs est_low $10,000 → raw drop $10,000
    # cap = max(2500, round(0.10 * 20000)) = max(2500, 2000) = 2500
    # so drop = 2500, new_price = 17500
    svc = AgingService()
    v = _FakeVehicle(intake_days_ago=65, asking_price=20000, cost_basis=10000)
    val = {"est_value": 12000, "est_low": 10000, "est_high": 14000}
    result = svc.evaluate(v, val)
    rec = result["recommendation"]
    assert rec is not None
    assert rec["drop"] == 2500
    assert rec["target_price"] == 17500


def test_under_market_no_recommendation():
    # Asking price is below est_low → no markdown needed
    svc = AgingService()
    v = _FakeVehicle(intake_days_ago=65, asking_price=9000, cost_basis=8000)
    val = {"est_value": 12000, "est_low": 10000, "est_high": 14000}
    result = svc.evaluate(v, val)
    assert result["recommendation"] is None


def test_stale_nudges_to_market_high():
    # Stale (50 days) + asking $17,000 > high $15,000 → target = high = 15000
    # raw_drop = 2000, cap = max(2500, 1700) = 2500 → drop = min(2000, 2500) = 2000
    svc = AgingService()
    v = _FakeVehicle(intake_days_ago=50, asking_price=17000, cost_basis=13000)
    val = {"est_value": 14000, "est_low": 12000, "est_high": 15000}
    result = svc.evaluate(v, val)
    rec = result["recommendation"]
    assert rec is not None
    assert rec["drop"] == 2000
    assert rec["target_price"] == 15000
    assert "Stale" in rec["reason"]


# ---------------------------------------------------------------------------
# Integration: /api/actions ordering and /reprice
# ---------------------------------------------------------------------------

def test_actions_sorted_by_impact(client):
    """Actions endpoint returns recommendations sorted by drop amount descending."""
    data = client.get("/api/actions").get_json()
    assert "actions" in data and "summary" in data
    drops = [a["recommendation"]["drop"] for a in data["actions"]]
    assert drops == sorted(drops, reverse=True)


def test_reprice_updates_asking_price(client):
    """POST /reprice applies a new price and returns the updated enriched vehicle."""
    # Find a car with a recommendation
    data = client.get("/api/actions").get_json()
    if not data["actions"]:
        pytest.skip("No actionable cars in current seed — check seed aging spread")

    car = data["actions"][0]
    vid = car["id"]
    rec_price = car["recommendation"]["target_price"]

    r = client.post(f"/api/vehicles/{vid}/reprice", json={"price": rec_price})
    assert r.status_code == 200
    body = r.get_json()
    assert body["asking_price"] == rec_price
    assert "days_on_lot" in body
    assert "aging_band" in body


def test_reprice_404_on_unknown(client):
    r = client.post("/api/vehicles/99999/reprice", json={"price": 10000})
    assert r.status_code == 404


def test_stats_include_aging_fields(client):
    """GET /api/vehicles stats must include the new holding-cost and aging-count fields."""
    stats = client.get("/api/vehicles").get_json()["stats"]
    assert "total_holding_cost" in stats
    assert "margin_at_risk" in stats
    assert "aging_counts" in stats
    ac = stats["aging_counts"]
    assert set(ac.keys()) == {"fresh", "aging", "stale", "critical"}
    # counts should sum to the number of available cars
    assert sum(ac.values()) == stats["available"]
