"""Data-access layer for vehicles (Repository pattern).

The repository is the *only* place that knows SQL. Route handlers depend on
this interface, not on sqlite -- so the storage engine could be swapped for
Postgres later without touching the API or the domain model.
"""
from __future__ import annotations

import sqlite3
from typing import Optional

from .models import Vehicle


class VehicleRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def list(self, status: Optional[str] = None, make: Optional[str] = None) -> list[Vehicle]:
        sql = "SELECT * FROM vehicles WHERE 1=1"
        params: list = []
        if status:
            sql += " AND status = ?"
            params.append(status)
        if make:
            sql += " AND make = ?"
            params.append(make)
        sql += " ORDER BY created_at DESC, id DESC"
        rows = self._conn.execute(sql, params).fetchall()
        return [Vehicle.from_row(r) for r in rows]

    def get(self, vehicle_id: int) -> Optional[Vehicle]:
        row = self._conn.execute(
            "SELECT * FROM vehicles WHERE id = ?", (vehicle_id,)
        ).fetchone()
        return Vehicle.from_row(row) if row else None

    def add(self, v: Vehicle) -> Vehicle:
        cur = self._conn.execute(
            """INSERT INTO vehicles
               (make, model, year, mileage, condition, accidents, asking_price, status,
                intake_date, cost_basis)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (v.make, v.model, v.year, v.mileage, v.condition,
             v.accidents, v.asking_price, v.status, v.intake_date, v.cost_basis),
        )
        return self.get(cur.lastrowid)  # type: ignore[arg-type]

    def update(self, vehicle_id: int, v: Vehicle) -> Optional[Vehicle]:
        cur = self._conn.execute(
            """UPDATE vehicles SET
                 make = ?, model = ?, year = ?, mileage = ?, condition = ?,
                 accidents = ?, asking_price = ?, status = ?,
                 intake_date = ?, cost_basis = ?
               WHERE id = ?""",
            (v.make, v.model, v.year, v.mileage, v.condition,
             v.accidents, v.asking_price, v.status,
             v.intake_date, v.cost_basis, vehicle_id),
        )
        return self.get(vehicle_id) if cur.rowcount else None

    def update_price(self, vehicle_id: int, price: int) -> Optional[Vehicle]:
        cur = self._conn.execute(
            "UPDATE vehicles SET asking_price = ? WHERE id = ?", (price, vehicle_id)
        )
        return self.get(vehicle_id) if cur.rowcount else None

    def set_status(self, vehicle_id: int, status: str) -> Optional[Vehicle]:
        cur = self._conn.execute(
            "UPDATE vehicles SET status = ? WHERE id = ?", (status, vehicle_id)
        )
        return self.get(vehicle_id) if cur.rowcount else None

    def delete(self, vehicle_id: int) -> bool:
        cur = self._conn.execute("DELETE FROM vehicles WHERE id = ?", (vehicle_id,))
        return cur.rowcount > 0

    def stats(self) -> dict:
        row = self._conn.execute(
            """SELECT
                 COUNT(*)                                        AS total,
                 SUM(status = 'available')                       AS available,
                 SUM(status = 'sold')                            AS sold,
                 COALESCE(SUM(CASE WHEN status='available'
                                   THEN asking_price END), 0)    AS inventory_value
               FROM vehicles"""
        ).fetchone()
        return dict(row)
