# DealerLot: Used-Car Inventory and Valuation

A full-stack web app for a car dealership that combines two things in one place: lot inventory management and instant market valuation. It tackles the same two problems Cox Automotive solves every day with **vAuto** (inventory management) and **Kelley Blue Book** (vehicle valuation).

> Demo project. Pricing comes from a model trained on synthetic-but-realistic data, not live market data.

---

## What it does

- **Inventory at a glance.** Every car on one screen with live dashboard stats: units in stock, sold, total inventory value, and how many are flagged over market.
- **Automatic price check.** The API values each car and flags it as Over market, Room to raise, or At market by comparing the asking price to the model's confidence band. Filter and sort by it.
- **Aging and holding cost intelligence.** Every car shows how many days it has been on the lot, a color-coded aging band (Fresh / Aging / Stale / Critical), and the real dollar cost it is accumulating in floorplan interest and overhead each day.
- **Markdown recommendations.** When a car is aging and overpriced, the app recommends a specific price drop with a reason ("Critical age (64 days) + $2,000 over market"). A manager reviews and approves each one. Nothing changes automatically.
- **One-click valuation.** Estimate any car's fair market value with a confidence range before setting a price.
- **Full CRUD.** Add, edit, delete, and mark cars as sold.
- **Reports view.** Total inventory value, total holding cost burned, margin at risk, overpricing to correct, and a breakdown of cars by aging band.

---

## Architecture

A single Flask service exposes a REST API and serves a vanilla JS frontend. Business logic lives in `core/` and is completely separate from the framework, so it is easy to test and reason about independently.

```
dealerlot/
├── app.py                 # Flask app factory: routes + wiring (no business logic here)
├── core/
│   ├── models.py          # Vehicle domain model + validation (no Flask, no SQL)
│   ├── repository.py      # VehicleRepository: the only place that touches SQL
│   ├── valuation.py       # ValuationService: pure-Python RandomForest inference
│   ├── aging.py           # AgingService: days-on-lot, holding cost, markdown engine
│   └── database.py        # connection management, schema, migrations, and seed data
├── static/index.html      # single-page UI (vanilla JS + fetch)
├── tests/
│   ├── test_api.py        # API integration tests
│   └── test_aging.py      # aging and holding cost unit + integration tests
├── model.json             # RandomForest exported from ml/train.py
├── docs/
│   ├── PRD-01-days-on-lot.md   # product requirements document
│   └── SPEC-01-days-on-lot.md  # technical specification
└── requirements.txt / Procfile / render.yaml / vercel.json
```

**Design choices worth noting:**

- **Repository pattern.** All SQL lives in `VehicleRepository`. Route handlers never touch the database directly. Swapping SQLite for Postgres would mean rewriting one class, nothing else.
- **Application factory.** `create_app()` builds and returns the Flask app, making it easy to spin up isolated test instances with throwaway databases.
- **Parameterized SQL everywhere.** No string interpolation in any query, so SQL injection is not possible.
- **Dependency-free ML inference.** The RandomForest is exported to JSON and traversed in pure Python. The deployed service has no scikit-learn or numpy dependency, keeping the image small and cold starts fast.
- **Idempotent migrations.** `init_db()` checks `PRAGMA table_info` before running any `ALTER TABLE`, so it is safe to run on startup against both fresh and existing databases.

---

## Run it locally

```bash
cd dealerlot
pip install -r requirements-dev.txt
python app.py
```

Open [http://localhost:5000](http://localhost:5000).

---

## Run the tests

```bash
pytest -q
```

24 tests: health check, CRUD round-trip, input validation, valuation accuracy, aging band boundaries, holding cost formula, markdown step cap, action list ordering, and reprice endpoint.

---

## Deploy

**Vercel (current live demo):**  
Connect the repo on [vercel.com](https://vercel.com). The included `vercel.json` configures the Python runtime and sets `DATABASE_PATH=/tmp/dealerlot.db`. Vercel will redeploy automatically on every push.

Note: Vercel is serverless, so the SQLite database resets on cold starts. The seed data reloads automatically, which works fine for a demo.

**Render (persistent, recommended for real use):**  
On [render.com](https://render.com): New > Blueprint, point it at the repo. `render.yaml` configures the build command, start command, and health check endpoint automatically. The database persists across requests.

Manual Render setup if preferred:
- Build: `pip install -r requirements.txt`
- Start: `gunicorn 'app:app' --bind 0.0.0.0:$PORT`
- Env var: `DATABASE_PATH=/tmp/dealerlot.db`

The same start command works on Railway, Fly.io, or any container host.

---

## API reference

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/healthz` | Liveness check and model R2 score |
| GET | `/api/vehicles` | List inventory with stats (supports `?status=` and `?make=` filters) |
| POST | `/api/vehicles` | Add a vehicle |
| GET / PUT / DELETE | `/api/vehicles/<id>` | Read, update, or remove a vehicle |
| POST | `/api/vehicles/<id>/sold` | Mark a vehicle as sold |
| POST | `/api/vehicles/<id>/reprice` | Apply a manager-approved markdown |
| GET | `/api/actions` | Aging cars with recommendations, ranked by dollar impact |
| POST | `/api/valuation` | Estimate market value for any vehicle |
| GET | `/api/makes` | List supported makes |

---

## Retraining the model

```bash
cd ../ml && python3 train.py
cp ../ml/model.json ./model.json
```

To use a real dataset instead of synthetic data:

```bash
python3 train.py --csv your_data.csv
```

Expected columns: `make, base_price, age, mileage, condition, accidents, price`

---

## How this maps to the Cox Automotive SWE role

| Requirement | Where it shows up |
|-------------|-------------------|
| Object-oriented programming | `Vehicle`, `VehicleRepository`, `ValuationService`, `AgingService`: real classes with single responsibilities |
| Database concepts | SQLite schema, indexes, constraints, parameterized SQL, aggregate queries, idempotent migrations |
| Design patterns and best practices | Repository pattern, application factory, separation of concerns, input validation at the boundary, full test suite |
| Web technologies | Flask REST API, HTML and JavaScript frontend, JSON responses |
| Build, deploy, monitor, and manage a production system | One-command local run, gunicorn for production, `/healthz` monitoring endpoint, Vercel and Render deployment configs |
| Innovative solution | ML valuation model served dependency-free in pure Python; Aging Intelligence feature that surfaces the cost of time on a dealer's lot |
| Explore solutions that fit the organization | Feature designed around the seam between vAuto (inventory), Kelley Blue Book (valuation), and NextGear Capital (floorplan financing) |
