"""Domain model for a vehicle in dealer inventory.

Kept deliberately framework-agnostic (no Flask, no SQL here) so the same
object can be used by the repository, the API layer, and the tests.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime, timezone
from typing import Any

VALID_STATUSES = ("available", "sold")
CONDITION_LABELS = {1: "Poor", 2: "Fair", 3: "Good", 4: "Great", 5: "Mint"}


class ValidationError(ValueError):
    """Raised when a Vehicle fails business-rule validation."""


@dataclass
class Vehicle:
    make: str
    model: str
    year: int
    mileage: int
    condition: int          # 1-5
    accidents: int          # 0-3
    asking_price: int       # what the lot is selling it for
    status: str = "available"
    id: int | None = None
    created_at: str | None = None
    intake_date: str | None = None
    cost_basis: int | None = None

    # --- factory helpers -------------------------------------------------
    @classmethod
    def from_row(cls, row: Any) -> "Vehicle":
        """Build a Vehicle from a sqlite3.Row (or any mapping)."""
        return cls(
            id=row["id"],
            make=row["make"],
            model=row["model"],
            year=row["year"],
            mileage=row["mileage"],
            condition=row["condition"],
            accidents=row["accidents"],
            asking_price=row["asking_price"],
            status=row["status"],
            created_at=row["created_at"],
            intake_date=row["intake_date"],
            cost_basis=row["cost_basis"],
        )

    @classmethod
    def from_payload(cls, data: dict) -> "Vehicle":
        """Build a Vehicle from a JSON request body, coercing/validating types."""
        try:
            v = cls(
                make=str(data["make"]).strip(),
                model=str(data["model"]).strip(),
                year=int(data["year"]),
                mileage=int(data["mileage"]),
                condition=int(data["condition"]),
                accidents=int(data.get("accidents", 0)),
                asking_price=int(data["asking_price"]),
                status=str(data.get("status", "available")),
                intake_date=(
                    str(data["intake_date"])
                    if data.get("intake_date")
                    else date.today().isoformat()
                ),
                cost_basis=(
                    int(data["cost_basis"])
                    if data.get("cost_basis") is not None
                    else None
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError(f"Missing or invalid field: {exc}") from exc
        v.validate()
        return v

    # --- business rules --------------------------------------------------
    def validate(self) -> None:
        now = datetime.now(timezone.utc).year
        if not self.make or not self.model:
            raise ValidationError("make and model are required.")
        if not (1990 <= self.year <= now + 1):
            raise ValidationError(f"year must be between 1990 and {now + 1}.")
        if not (0 <= self.mileage <= 400_000):
            raise ValidationError("mileage must be between 0 and 400,000.")
        if self.condition not in CONDITION_LABELS:
            raise ValidationError("condition must be 1-5.")
        if not (0 <= self.accidents <= 3):
            raise ValidationError("accidents must be 0-3.")
        if self.asking_price <= 0:
            raise ValidationError("asking_price must be positive.")
        if self.status not in VALID_STATUSES:
            raise ValidationError(f"status must be one of {VALID_STATUSES}.")

    # --- serialization ---------------------------------------------------
    def to_dict(self) -> dict:
        d = asdict(self)
        d["condition_label"] = CONDITION_LABELS.get(self.condition, "?")
        return d
