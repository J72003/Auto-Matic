"""DealerLot -- used-car inventory manager with KBB-style valuation.

A single Flask service that exposes a REST API and serves the static UI.
Wiring lives here; domain logic lives in the `core` package.
"""
from __future__ import annotations

import os

from flask import Flask, jsonify, request, send_from_directory

from core.aging import AgingService
from core.database import connect, init_db
from core.models import ValidationError, Vehicle
from core.repository import VehicleRepository
from core.valuation import ValuationService

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def create_app() -> Flask:
    """Application factory -- makes testing and multiple configs trivial."""
    app = Flask(__name__, static_folder=None)
    init_db()
    valuator = ValuationService()   # load model once at startup
    ager = AgingService()           # holding-cost / markdown engine

    def repo(conn) -> VehicleRepository:
        return VehicleRepository(conn)

    def enrich(v: Vehicle) -> dict:
        """Attach valuation + aging intelligence to a vehicle dict."""
        d = v.to_dict()
        assessment = valuator.assess(
            v.asking_price, v.make, v.year, v.mileage, v.condition, v.accidents
        )
        d.update(assessment)
        aging_data = ager.evaluate(v, assessment)
        d.update(aging_data)
        return d

    # ----- frontend ------------------------------------------------------
    @app.get("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.get("/static/<path:filename>")
    def static_files(filename):
        return send_from_directory(STATIC_DIR, filename)

    # ----- monitoring ----------------------------------------------------
    @app.get("/healthz")
    def healthz():
        return jsonify(status="ok", model_r2=valuator.metrics["r2"])

    # ----- inventory -----------------------------------------------------
    @app.get("/api/vehicles")
    def list_vehicles():
        status = request.args.get("status")
        make = request.args.get("make")
        with connect() as conn:
            r = repo(conn)
            vehicles = [enrich(v) for v in r.list(status=status, make=make)]
            base_stats = r.stats()

        # market signals
        available = [v for v in vehicles if v["status"] == "available"]
        over = sum(1 for v in available if v["market_state"] == "over")
        under = sum(1 for v in available if v["market_state"] == "under")

        # aging signals (available cars only)
        total_holding = round(sum(v["holding_cost_to_date"] for v in available), 2)
        margin_at_risk = sum(v["market_delta"] for v in available if v["market_state"] == "over")
        aging_counts = {"fresh": 0, "aging": 0, "stale": 0, "critical": 0}
        for v in available:
            aging_counts[v["aging_band"].lower()] += 1

        base_stats["over_market"] = over
        base_stats["room_to_raise"] = under
        base_stats["total_holding_cost"] = total_holding
        base_stats["margin_at_risk"] = margin_at_risk
        base_stats["aging_counts"] = aging_counts

        return jsonify(vehicles=vehicles, stats=base_stats)

    @app.get("/api/vehicles/<int:vid>")
    def get_vehicle(vid: int):
        with connect() as conn:
            v = repo(conn).get(vid)
        if not v:
            return jsonify(error="Vehicle not found."), 404
        return jsonify(enrich(v))

    @app.post("/api/vehicles")
    def create_vehicle():
        try:
            v = Vehicle.from_payload(request.get_json(force=True, silent=True) or {})
        except ValidationError as e:
            return jsonify(error=str(e)), 400
        with connect() as conn:
            created = repo(conn).add(v)
        return jsonify(enrich(created)), 201

    @app.put("/api/vehicles/<int:vid>")
    def update_vehicle(vid: int):
        try:
            v = Vehicle.from_payload(request.get_json(force=True, silent=True) or {})
        except ValidationError as e:
            return jsonify(error=str(e)), 400
        with connect() as conn:
            updated = repo(conn).update(vid, v)
        if not updated:
            return jsonify(error="Vehicle not found."), 404
        return jsonify(enrich(updated))

    @app.post("/api/vehicles/<int:vid>/sold")
    def mark_sold(vid: int):
        with connect() as conn:
            updated = repo(conn).set_status(vid, "sold")
        if not updated:
            return jsonify(error="Vehicle not found."), 404
        return jsonify(enrich(updated))

    @app.delete("/api/vehicles/<int:vid>")
    def delete_vehicle(vid: int):
        with connect() as conn:
            ok = repo(conn).delete(vid)
        if not ok:
            return jsonify(error="Vehicle not found."), 404
        return ("", 204)

    # ----- valuation -----------------------------------------------------
    @app.post("/api/valuation")
    def valuation():
        data = request.get_json(force=True, silent=True) or {}
        try:
            result = valuator.estimate(
                make=str(data["make"]),
                year=int(data["year"]),
                mileage=int(data["mileage"]),
                condition=int(data["condition"]),
                accidents=int(data.get("accidents", 0)),
            )
        except (KeyError, TypeError, ValueError):
            return jsonify(error="Provide make, year, mileage, condition, accidents."), 400
        result["metrics"] = valuator.metrics
        return jsonify(result)

    @app.get("/api/makes")
    def makes():
        return jsonify(makes=valuator.known_makes())

    # ----- aging / action list -------------------------------------------
    @app.get("/api/actions")
    def actions():
        """Prioritized list of aging cars that have a markdown recommendation."""
        with connect() as conn:
            available = [enrich(v) for v in repo(conn).list(status="available")]

        recs = [v for v in available if v["recommendation"] is not None]
        recs.sort(key=lambda v: (-v["recommendation"]["drop"], -v["days_on_lot"]))

        return jsonify(
            actions=recs,
            summary={
                "count": len(recs),
                "total_drop": sum(v["recommendation"]["drop"] for v in recs),
                "total_holding_cost": round(
                    sum(v["holding_cost_to_date"] for v in available), 2
                ),
                "aging_counts": {
                    "fresh":    sum(1 for v in available if v["aging_band"] == "Fresh"),
                    "aging":    sum(1 for v in available if v["aging_band"] == "Aging"),
                    "stale":    sum(1 for v in available if v["aging_band"] == "Stale"),
                    "critical": sum(1 for v in available if v["aging_band"] == "Critical"),
                },
            },
        )

    @app.post("/api/vehicles/<int:vid>/reprice")
    def reprice(vid: int):
        """Apply a manager-approved price markdown (human-triggered, never automatic)."""
        with connect() as conn:
            v = repo(conn).get(vid)
        if not v:
            return jsonify(error="Vehicle not found."), 404

        data = request.get_json(force=True, silent=True) or {}
        new_price = data.get("price")

        if new_price is None:
            enriched = enrich(v)
            rec = enriched.get("recommendation")
            if rec is None:
                return jsonify(error="No recommendation exists and no price provided."), 400
            new_price = rec["target_price"]

        try:
            new_price = int(new_price)
            if new_price <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify(error="price must be a positive integer."), 400

        with connect() as conn:
            updated = repo(conn).update_price(vid, new_price)
        if not updated:
            return jsonify(error="Vehicle not found."), 404
        return jsonify(enrich(updated))

    return app


app = create_app()  # for gunicorn 'app:app'

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
