# Unit Ledger - Tariff-Aware Electricity Bill Analyzer & Solar Planner

Mini project (Team 10). Households enter bills, see exactly how each rupee is calculated, track slabs live,
forecast the next bill, simulate usage changes and evaluate rooftop solar.

## Quick start

**Docker (recommended)**
```bash
cp .env.example .env        # set SECRET_KEY and DB_PASSWORD
docker compose up --build
# UI: http://localhost:3000   API docs: http://localhost:8000/docs
```

**Without Docker**
```bash
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload     # SQLite by default
cd frontend && npm install && npm run dev                                           # http://localhost:5173
cd backend && pytest -q                                                              # tests
```
Register with the email in `ADMIN_EMAIL` (default `admin@example.com`) to get the admin role.
Import `sample_data/bills.csv` from the Bills tab for instant demo data.

## Structure
```
backend/app/engine/   tariff.py  analytics.py  appliances.py  solar.py  nilm.py   (pure Python, unit-tested)
backend/app/          main.py (REST API)  security.py (JWT, RBAC, Fernet)  models.py  schemas.py
backend/tariffs/      JSON tariff files (config-as-code: new utility = new file, no code change)
backend/tests/        tariff, engine and API tests
frontend/src/         React dashboard (Vite)
.github/workflows/    CI: lint, tariff validation, tests, build, docker smoke test, deploy hook
```

## Features required by the brief
Register/login (JWT) - bill entry + CSV import - bill breakdown (energy, fixed, fuel adj., duty, subsidy) -
slab tracker + month-end projection - appliance profile & share of consumption - savings suggestions - forecast
(moving average + trend + seasonal blend) - z-score anomaly alerts - what-if simulator - solar payback - RBAC -
encrypted consumer number - Docker/Compose - GitHub Actions CI/CD.

## Extra features that typical bill calculators don't have
1. **Bill Auditor** - compares your actual bill with the tariff-computed one and flags arrears/penalty/meter errors.
2. **Real marginal cost** - "what does the next unit cost me right now" including fuel adj., duty, subsidy edges.
3. **Cliff warnings** - supports whole-consumption slabs (`slab_mode: cliff`) and the free-unit entitlement edge,
   where one extra unit can cost hundreds of rupees.
4. **Daily unit budget + minimum-sacrifice plan** - "stay under X units/day; cut the geyser by 15 min".
5. **Meter-calibrated appliance estimates** - scales your wattage x hours guess to match the metered total and
   shows unaccounted (phantom) units.
6. **Tariff-change impact** - replay your last 12 bills under a revised tariff file (v1 vs v2) before it hits you.
7. **Solar planner beyond payback** - net metering vs net billing, battery, loan EMI, degradation, tariff escalation,
   inverter replacement, IRR/NPV, CO2 avoided, scenario table.
8. **Smart-meter simulator + NILM-lite** - minute-level synthetic readings and step-change appliance detection
   (Tier 3 without hardware).
9. **Household benchmarking** and **privacy tools** (data erasure endpoint `DELETE /auth/me`, masked consumer number).

## IMPORTANT: verify numbers
`backend/tariffs/*.json`, the solar subsidy schedule (`solar.central_subsidy`), emission factor and benchmark table
are **sample values**. Before quoting anything, copy slabs, fixed charges, duty and subsidy rules for your utility
(e.g. your ESCOM) from its official tariff order, and update them via a pull request - CI will run the tariff tests.
The free-unit rule is a simplified model (entitlement = 12-month average + buffer, capped); adjust to the scheme's real rules.

## Not implemented (future work)
OCR of bill images (add Tesseract in a `bill-parsing` service; the manual-correction step already exists as bill entry),
email/Telegram notifications (alerts are stored and shown in the UI; call `/alerts/refresh` from Celery/cron),
Prophet/ARIMA (the forecaster is dependency-free; swap `forecast_next`), Terraform.

## Testing status
The engine tests (`test_tariff.py`, `test_engines.py`, 20 tests) were run and pass. The API tests (`test_api.py`) and the
React build need `pip install` / `npm install`, so run `pytest -q` and `npm run build` on your machine first.
