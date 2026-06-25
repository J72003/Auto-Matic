"""KBB-style valuation service.

Loads a RandomForest exported to JSON (trained in ../ml/train.py) and runs
inference in pure Python -- no sklearn/numpy needed at runtime, so the
deployed service stays tiny. The model predicts log-price; we exponentiate
and use the spread across trees as a simple confidence band.
"""
from __future__ import annotations

import json
import math
import os
import statistics
from typing import Optional

_LEAF = -2  # sklearn marks leaf nodes with feature == -2
_DEFAULT_MODEL = os.path.join(os.path.dirname(os.path.dirname(__file__)), "model.json")


class ValuationService:
    def __init__(self, model_path: Optional[str] = None):
        with open(model_path or _DEFAULT_MODEL) as f:
            self._model = json.load(f)
        self._trees = self._model["trees"]
        self._makes = self._model["makes"]
        self._current_year = self._model["current_year"]
        # fallback base price for makes not in the training set
        self._median_base = statistics.median(m["base_price"] for m in self._makes.values())

    @property
    def metrics(self) -> dict:
        return self._model["metrics"]

    def known_makes(self) -> list[str]:
        return sorted(self._makes.keys())

    @staticmethod
    def _predict_tree(tree: dict, x: list[float]) -> float:
        node = 0
        feature = tree["feature"]
        while feature[node] != _LEAF:
            f = feature[node]
            node = tree["left"][node] if x[f] <= tree["threshold"][node] else tree["right"][node]
        return tree["value"][node]  # log-price at leaf

    def estimate(self, make: str, year: int, mileage: int,
                 condition: int, accidents: int) -> dict:
        base = self._makes.get(make, {}).get("base_price", self._median_base)
        age = max(0, self._current_year - int(year))
        x = [base, age, int(mileage), int(condition), int(accidents)]

        logs = [self._predict_tree(t, x) for t in self._trees]
        mean_log = sum(logs) / len(logs)
        std = statistics.pstdev(logs)

        def r100(n: float) -> int:
            return max(500, round(n / 100) * 100)

        est = r100(math.exp(mean_log))
        low = r100(math.exp(mean_log - 1.5 * std))
        high = r100(math.exp(mean_log + 1.5 * std))
        return {
            "estimate": est,
            "low": min(low, est),
            "high": max(high, est),
            "make_recognized": make in self._makes,
        }

    def assess(self, asking_price: int, make: str, year: int, mileage: int,
               condition: int, accidents: int) -> dict:
        """Estimate value AND compare it to the asking price.

        Uses the model's confidence band: if the asking price is above the
        band it's flagged 'over' (reprice down), below the band 'under'
        (room to raise), otherwise 'at' market. This is the business logic
        the dealer actually cares about.
        """
        val = self.estimate(make, year, mileage, condition, accidents)
        est, low, high = val["estimate"], val["low"], val["high"]
        if asking_price > high:
            state, delta = "over", asking_price - est
            note = f"+${delta:,} over"
        elif asking_price < low:
            state, delta = "under", est - asking_price
            note = f"${delta:,} under"
        else:
            state, delta, note = "at", 0, "within range"
        return {
            "est_value": est,
            "est_low": low,
            "est_high": high,
            "market_state": state,   # over | under | at
            "market_delta": delta,
            "market_note": note,
            "make_recognized": val["make_recognized"],
        }
