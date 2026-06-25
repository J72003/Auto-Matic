"""Inventory aging, holding cost, and markdown recommendation engine.

Tracks how long each car has been on the lot, translates that into a dollar
holding cost (floorplan interest + daily overhead), and recommends a concrete
price markdown when a car ages past a healthy threshold AND sits above market.

This is the seam between vAuto (inventory/pricing) and NextGear Capital
(floorplan financing) — two Cox products — made visible and actionable.
"""
from __future__ import annotations

import os
from datetime import date
from typing import Optional


_APR = float(os.environ.get("HOLDING_APR", "0.09"))
_DAILY_OVERHEAD = float(os.environ.get("HOLDING_DAILY_OVERHEAD", "12"))

# (max days inclusive, band name)  — Critical is the open-ended fallthrough
_BAND_THRESHOLDS = [(30, "Fresh"), (45, "Aging"), (60, "Stale")]


def _aging_band(days: int) -> str:
    for threshold, name in _BAND_THRESHOLDS:
        if days <= threshold:
            return name
    return "Critical"


class AgingService:
    def __init__(
        self,
        apr: float = _APR,
        daily_overhead: float = _DAILY_OVERHEAD,
    ) -> None:
        self._apr = apr
        self._daily_overhead = daily_overhead

    def evaluate(
        self,
        vehicle,         # core.models.Vehicle
        valuation: dict, # from ValuationService.assess() — must include est_value, est_low, est_high
        today: Optional[date] = None,
    ) -> dict:
        """Return aging enrichment: days-on-lot, band, holding cost, recommendation."""
        if today is None:
            today = date.today()

        intake = date.fromisoformat(vehicle.intake_date) if vehicle.intake_date else today
        days = max(0, (today - intake).days)
        band = _aging_band(days)

        # Use cost_basis if recorded; fall back to 90% of est_value (documented proxy)
        basis = (
            vehicle.cost_basis
            if vehicle.cost_basis is not None
            else round(valuation["est_value"] * 0.90)
        )
        per_day = round(basis * self._apr / 365 + self._daily_overhead, 2)
        to_date = round(per_day * days, 2)

        rec = self._recommend(
            asking=vehicle.asking_price,
            band=band,
            est_low=valuation["est_low"],
            est_high=valuation["est_high"],
            days=days,
        )

        return {
            "days_on_lot": days,
            "aging_band": band,
            "holding_cost_per_day": per_day,
            "holding_cost_to_date": to_date,
            "recommendation": rec,
        }

    # ------------------------------------------------------------------
    # Balanced markdown engine (recommendation only — human approves)
    # ------------------------------------------------------------------
    # Fresh/Aging : only flag when far over market (>10% above band high)
    # Stale       : nudge to market high if asking > high
    # Critical    : drop toward market low if asking > low
    # Step cap    : never recommend more than max($2,500, 10%) in one move
    # ------------------------------------------------------------------
    def _recommend(
        self,
        asking: int,
        band: str,
        est_low: int,
        est_high: int,
        days: int,
    ) -> Optional[dict]:
        target: Optional[int] = None
        reason_parts: list[str] = []

        if band in ("Fresh", "Aging"):
            if asking > est_high * 1.10:
                target = est_high
                pct = round((asking / est_high - 1) * 100)
                reason_parts.append(f"far over market (+{pct}%)")
        elif band == "Stale":
            if asking > est_high:
                target = est_high
                reason_parts.append(f"Stale age ({days} days)")
                reason_parts.append(f"${asking - est_high:,} over market")
        elif band == "Critical":
            if asking > est_low:
                target = est_low
                reason_parts.append(f"Critical age ({days} days)")
                if asking > est_high:
                    reason_parts.append(f"${asking - est_high:,} over market")
                else:
                    reason_parts.append("above market floor")

        if target is None or target >= asking:
            return None

        raw_drop = asking - target
        cap = max(2500, round(0.10 * asking))
        drop = min(raw_drop, cap)
        new_price = round((asking - drop) / 100) * 100

        return {
            "target_price": new_price,
            "drop": drop,
            "reason": " + ".join(reason_parts),
        }
