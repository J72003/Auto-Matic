# DealerLot — Used-Car Inventory & Valuation

A small full-stack web app for a car dealership: manage lot inventory **and** get an
instant Kelley Blue Book–style market valuation for any vehicle. It pairs the two
problems Cox Automotive solves every day — **inventory management** (vAuto, Dealer.com)
and **vehicle valuation** (Kelley Blue Book) — in one deployable service.

> Demo project. Pricing comes from a model trained on synthetic-but-realistic data, not live market data.

## What it does
- **Inventory at a glance** — every car on one screen with live dashboard stats (in stock, sold, inventory value, # flagged over market).
- **Automatic price check** — the API values each car with the model and flags it **Over market**, **Room to raise**, or **At market** by comparing the asking price to the model's confidence band. Filter and sort by it ("flagged first").
- **One-click valuation** — estimate any car's fair market value (with a range) before setting a price.
- **Add / edit / delete / mark sold**, plus a Reports view summarizing overpricing to correct and upside left on the table.

The market-flag logic lives in `ValuationService.assess()` and is computed server-side, so the API returns real business logic, not plain CRUD.

## Architecture
A single Flask service exposes a REST API and serves a vanilla-JS frontend. Domain logic
is separated from the framework so it's easy to test and reason about.

```
dealerlot/
├── app.py                 # Flask app factory: routes + wiring (no business logic)
├── core/
│   ├── models.py          # Vehicle domain model + validation (no Flask, no SQL)
│   ├── repository.py      # VehicleRepository — the only place that knows SQL (Repository pattern)
│   ├── valuation.py       # ValuationService — pure-Python RandomForest inference
│   └── database.py        # connection management + schema/seed
├── static/index.html      # single-page UI (fetch + REST)
├── tests/test_api.py      # pytest suite against the Flask test client
├── model.json             # RandomForest exported from ../ml/train.py
├── requirements.txt · Procfile · render.yaml
```

Design choices worth noting:
- **Repository pattern** keeps SQL in one class; the API depends on an interface, so SQLite could become Postgres without touching routes.
- **Application factory** (`create_app()`) makes testing and multiple configs clean.
- **Parameterized SQL everywhere** — no string interpolation, so no SQL injection.
- The ML model is **exported to JSON and traversed in pure Python**, so the deployed service has zero heavy ML dependencies (just Flask) and tiny cold starts.

## Run it locally
```bash
cd dealerlot
python3 -m venv .venv && source .venv/bin/activate   # optional
pip install -r requirements-dev.txt
python app.py                 # http://localhost:5000
```

## Test
```bash
pytest -q                     # 7 tests: health, CRUD, validation, valuation
```

## Deploy (Render free tier)
1. Push this folder to a GitHub repo.
2. On [render.com](https://render.com): **New → Blueprint**, point it at the repo. `render.yaml` configures everything (build, start command, `/healthz` health check).
3. Or **New → Web Service** manually:
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn 'app:app' --bind 0.0.0.0:$PORT`
   - Env: `DATABASE_PATH=/tmp/dealerlot.db`

The same one-line start command works on Railway, Fly.io, or any container host.

## API
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/healthz` | liveness + model R² (for monitoring) |
| GET | `/api/vehicles?status=&make=` | list inventory + summary stats |
| POST | `/api/vehicles` | add a vehicle |
| GET/PUT/DELETE | `/api/vehicles/<id>` | read / update / remove |
| POST | `/api/vehicles/<id>/sold` | mark sold |
| POST | `/api/valuation` | estimate market value |
| GET | `/api/makes` | supported makes |

## Retraining the model
The model lives one level up in `../ml/train.py` (scikit-learn). Retrain and re-export:
```bash
cd ../ml && python3 train.py        # writes app/data/model.json
cp ../app/data/model.json ./model.json   # (run from dealerlot/) refresh the served copy
```
Swap in a real Kaggle used-car dataset with `python3 train.py --csv your_data.csv`
(columns: `make,base_price,age,mileage,condition,accidents,price`).

## How this maps to the Cox SWE job description
- **OOP (required):** `Vehicle`, `VehicleRepository`, `ValuationService` — real classes with clear responsibilities.
- **Database concepts (required):** SQLite schema, indexes, constraints, parameterized SQL, aggregate stats query.
- **Design patterns / best practices:** repository pattern, application factory, separation of concerns, input validation, tests.
- **Web technologies (plus):** HTML + JavaScript frontend over a REST API.
- **Build, deploy, monitor, manage a production system:** one-command run, gunicorn, `/healthz`, Render blueprint.
- **Innovative solution / new tech:** an ML valuation feature served dependency-free.
