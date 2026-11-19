import csv, io
from datetime import date, datetime, timedelta
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from . import config, schemas as S
from .db import Base, engine, get_db
from .models import User, Bill, Appliance, Reading, Alert, PasswordReset
from .security import (hash_password, verify_password, make_token, current_user, require_role, encrypt, decrypt)
from .engine import tariff as T, analytics as A, appliances as AP, solar as SO, nilm, ocr

import hashlib, secrets
from .mailer import send_reset_email, email_configured

app = FastAPI(title="Tariff-Aware Electricity Bill Analyzer & Solar Planner", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def startup():
    Base.metadata.create_all(engine)
    print("Email sending: " + ("READY" if email_configured() else "NOT CONFIGURED (check backend/.env)"), flush=True)


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- helpers ----------
def tariff_for(user):
    try:
        return T.get_tariff(user.tariff_id)
    except KeyError:
        raise HTTPException(400, f"Unknown tariff '{user.tariff_id}'")


def user_bills(db, user):
    return list(db.scalars(select(Bill).where(Bill.user_id == user.id).order_by(Bill.month)))


def ent_for(t, bills, before_month=None):
    hist = [b.units for b in bills if before_month is None or b.month < before_month]
    return T.entitlement(t, hist)


def appliance_dicts(db, user):
    rows = db.scalars(select(Appliance).where(Appliance.user_id == user.id))
    return [dict(id=a.id, name=a.name, watts=a.watts, hours_per_day=a.hours_per_day, qty=a.qty,
                 duty=a.duty, days_per_month=a.days_per_month) for a in rows]


def cycle_state(db, user):
    """Units used this calendar month from daily readings."""
    today = date.today()
    start = today.replace(day=1)
    rows = list(db.scalars(select(Reading).where(Reading.user_id == user.id, Reading.day >= start).order_by(Reading.day)))
    nxt = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return {"units_so_far": round(sum(r.units for r in rows), 1), "day": max(today.day, 1),
            "days_in_cycle": (nxt - start).days, "daily": [r.units for r in rows]}


# ---------- auth ----------
@app.post("/auth/register", status_code=201)
def register(body: S.RegisterIn, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(409, "Email already registered")
    try:
        T.get_tariff(body.tariff_id)
    except KeyError:
        raise HTTPException(400, "Unknown tariff")
    u = User(email=body.email.lower(), name=body.name, password_hash=hash_password(body.password),
             household_size=body.household_size, sanctioned_kw=body.sanctioned_kw, tariff_id=body.tariff_id,
             consumer_no_enc=encrypt(body.consumer_no) if body.consumer_no else None,
             role="admin" if body.email.lower() == config.ADMIN_EMAIL.lower() else "user")
    db.add(u); db.commit()
    return {"token": make_token(u), "user": profile(u)}


@app.post("/auth/login")
def login(body: S.LoginIn, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.email == body.email.lower()))
    if not u or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "Invalid credentials")
    return {"token": make_token(u), "user": profile(u)}


def _hash_token(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


@app.post("/auth/forgot-password")
def forgot_password(body: S.ForgotIn, bg: BackgroundTasks, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.email == body.email.lower()))
    if u:
        db.execute(delete(PasswordReset).where(PasswordReset.user_id == u.id))   # cancel older links
        raw = secrets.token_urlsafe(32)
        db.add(PasswordReset(user_id=u.id, token_hash=_hash_token(raw),
                             expires_at=datetime.utcnow() + timedelta(minutes=config.RESET_MINUTES)))
        db.commit()
        bg.add_task(send_reset_email, u.email, f"{config.FRONTEND_URL}/?reset={raw}")
    return {"message": "If that email is registered, a reset link has been sent."}


@app.post("/auth/reset-password")
def reset_password(body: S.ResetIn, db: Session = Depends(get_db)):
    r = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == _hash_token(body.token)))
    if not r or r.used or r.expires_at < datetime.utcnow():
        raise HTTPException(400, "This reset link is invalid or has expired. Please request a new one.")
    u = db.get(User, r.user_id)
    if not u:
        raise HTTPException(400, "This reset link is invalid or has expired. Please request a new one.")
    u.password_hash = hash_password(body.new_password)
    r.used = True
    db.commit()
    return {"message": "Password updated. You can now sign in."}

def profile(u):
    masked = None
    if u.consumer_no_enc:
        n = decrypt(u.consumer_no_enc)
        masked = "*" * max(len(n) - 3, 0) + n[-3:]
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role, "household_size": u.household_size,
            "sanctioned_kw": u.sanctioned_kw, "tariff_id": u.tariff_id, "consumer_no": masked}


@app.get("/auth/me")
def me(user: User = Depends(current_user)):
    return profile(user)


@app.patch("/auth/me")
def update_me(body: S.ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.tariff_id:
        try:
            T.get_tariff(body.tariff_id)
        except KeyError:
            raise HTTPException(400, "Unknown tariff")
        user.tariff_id = body.tariff_id
    if body.household_size: user.household_size = body.household_size
    if body.sanctioned_kw: user.sanctioned_kw = body.sanctioned_kw
    db.add(user); db.commit()
    return profile(user)


@app.delete("/auth/me", status_code=204)
def delete_account(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Privacy: user can erase all their data."""
    for m in (Bill, Appliance, Reading, Alert, PasswordReset):
        db.execute(delete(m).where(m.user_id == user.id))
    db.delete(user); db.commit()


# ---------- tariffs ----------
@app.get("/tariffs")
def tariffs():
    return T.list_tariffs()


@app.get("/tariffs/{tid}")
def tariff_detail(tid: str):
    try:
        return T.get_tariff(tid)
    except KeyError:
        raise HTTPException(404, "Unknown tariff")


@app.post("/calc")
def calc(body: S.CalcIn):
    try:
        t = T.get_tariff(body.tariff_id)
    except KeyError:
        raise HTTPException(404, "Unknown tariff")
    return T.compute_bill(body.units, t, body.sanctioned_kw, body.entitled_units)


@app.post("/tariffs/compare")
def compare(body: S.TariffCompareIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        old, new = T.get_tariff(body.old_id), T.get_tariff(body.new_id)
    except KeyError:
        raise HTTPException(404, "Unknown tariff")
    hist = [(b.month, b.units) for b in user_bills(db, user)][-12:]
    if not hist:
        raise HTTPException(400, "Add at least one bill first")
    return T.compare_tariffs(hist, old, new, user.sanctioned_kw)


# ---------- bills ----------
def bill_out(b, t, kw, ent):
    c = T.compute_bill(b.units, t, kw, ent)
    audit = None
    if b.amount_actual is not None:
        diff = round(b.amount_actual - c["total"], 2)
        flag = abs(diff) > max(20, 0.03 * c["total"])
        audit = {"expected": c["total"], "actual": b.amount_actual, "difference": diff, "flag": flag,
                 "message": (f"Your bill is Rs {abs(diff)} {'higher' if diff > 0 else 'lower'} than the tariff rules predict. "
                             "Check arrears, penalties, meter reading date/units or a tariff revision.") if flag
                 else "Bill matches the tariff calculation."}
    return {"id": b.id, "month": b.month, "units": b.units, "days": b.days, "breakdown": c, "audit": audit}


@app.post("/bills", status_code=201)
def add_bill(body: S.BillIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if db.scalar(select(Bill).where(Bill.user_id == user.id, Bill.month == body.month)):
        raise HTTPException(409, "A bill for this month already exists")
    b = Bill(user_id=user.id, **body.model_dump())
    db.add(b); db.commit()
    t = tariff_for(user)
    return bill_out(b, t, user.sanctioned_kw, ent_for(t, user_bills(db, user), b.month))


@app.get("/bills")
def list_bills(user: User = Depends(current_user), db: Session = Depends(get_db)):
    t, bills = tariff_for(user), user_bills(db, user)
    return [bill_out(b, t, user.sanctioned_kw, ent_for(t, bills, b.month)) for b in bills]


@app.delete("/bills/{bid}", status_code=204)
def del_bill(bid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    b = db.get(Bill, bid)
    if not b or b.user_id != user.id:
        raise HTTPException(404, "Not found")
    db.delete(b); db.commit()


@app.post("/bills/import-csv")
async def import_csv(file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """CSV columns: month,units[,amount_actual][,days]"""
    text = (await file.read()).decode("utf-8-sig")
    added, errors = 0, []
    for i, row in enumerate(csv.DictReader(io.StringIO(text)), start=2):
        try:
            data = S.BillIn(month=row["month"].strip(), units=float(row["units"]),
                            amount_actual=float(row["amount_actual"]) if row.get("amount_actual") else None,
                            days=int(row.get("days") or 30))
            if db.scalar(select(Bill).where(Bill.user_id == user.id, Bill.month == data.month)):
                errors.append(f"line {i}: {data.month} already exists"); continue
            db.add(Bill(user_id=user.id, **data.model_dump())); added += 1
        except Exception as e:
            errors.append(f"line {i}: {e}")
    db.commit()
    return {"added": added, "errors": errors}

@app.post("/bills/ocr")
async def bill_ocr(file: UploadFile = File(...), user: User = Depends(current_user)):
    if file.content_type not in ("image/png", "image/jpeg"):
        raise HTTPException(400, "Upload a .png or .jpg image")
    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(413, "Image larger than 8 MB")
    try:
        text = ocr.ocr_image(data)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception:
        raise HTTPException(422, "Could not read this image")
    return ocr.extract_bill_fields(text)

# ---------- readings / slab tracker ----------
@app.post("/readings", status_code=201)
def add_reading(body: S.ReadingIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = db.scalar(select(Reading).where(Reading.user_id == user.id, Reading.day == body.day))
    if r: r.units = body.units
    else: db.add(Reading(user_id=user.id, day=body.day, units=body.units))
    db.commit()
    return {"ok": True}


@app.get("/slab-tracker")
def slab_tracker(units_so_far: float | None = None, day: int | None = None, days_in_cycle: int | None = None,
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    t, bills = tariff_for(user), user_bills(db, user)
    ent = ent_for(t, bills)
    cs = cycle_state(db, user)
    manual = units_so_far is not None
    used = units_so_far if manual else cs["units_so_far"]
    d = day or cs["day"]; dic = days_in_cycle or cs["days_in_cycle"]
    proj = A.project_month_end(used, d, dic, None if manual else cs["daily"])
    status_now = T.slab_status(used, t, user.sanctioned_kw, ent)
    status_end = T.slab_status(proj["projected_units"], t, user.sanctioned_kw, ent)
    nb = status_now["next_boundary"]
    nudge, budget, plan = None, None, None
    if nb:
        budget = A.daily_budget(used, nb["at_units"], proj["days_left"])
        will_cross = proj["projected_units"] > nb["at_units"]
        if will_cross:
            over = proj["projected_units"] - nb["at_units"]
            apps = appliance_dicts(db, user)
            plan = AP.reduction_plan(apps, over) if apps else None
            nudge = (f"You are {nb['units_left']} units from '{nb['label']}'. At your current pace you will cross it by "
                     f"~{round(over, 1)} units. Keep usage under {budget['safe_daily_units']} units/day for the last "
                     f"{proj['days_left']} days to stay below it.")
        else:
            nudge = f"On track: you should finish ~{round(nb['at_units'] - proj['projected_units'], 1)} units below the next boundary."
    return {"units_so_far": used, "projection": proj, "status_now": status_now,
            "bill_so_far": T.compute_bill(used, t, user.sanctioned_kw, ent)["total"],
            "projected_bill": T.compute_bill(proj["projected_units"], t, user.sanctioned_kw, ent),
            "projected_slab": status_end["current_slab"], "entitled_units": ent,
            "daily_budget": budget, "nudge": nudge, "reduction_plan": plan}


# ---------- appliances ----------
@app.get("/appliances/presets")
def presets():
    return AP.PRESETS


@app.post("/appliances", status_code=201)
def add_app(body: S.ApplianceIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = Appliance(user_id=user.id, **body.model_dump())
    db.add(a); db.commit()
    return {"id": a.id}


@app.get("/appliances")
def list_apps(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return appliance_dicts(db, user)


@app.delete("/appliances/{aid}", status_code=204)
def del_app(aid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = db.get(Appliance, aid)
    if not a or a.user_id != user.id:
        raise HTTPException(404, "Not found")
    db.delete(a); db.commit()


def latest_units(bills, user, db):
    if bills: return bills[-1].units
    cs = cycle_state(db, user)
    return cs["units_so_far"] or None


@app.get("/appliances/analysis")
def analysis(user: User = Depends(current_user), db: Session = Depends(get_db)):
    t, bills, apps = tariff_for(user), user_bills(db, user), appliance_dicts(db, user)
    actual = latest_units(bills, user, db)
    res = AP.analyse(apps, actual)
    base = actual or res["estimated_total"]
    res["suggestions"] = AP.suggestions(apps, base, t, user.sanctioned_kw, ent_for(t, bills), res["calibration_factor"])
    return res


@app.post("/whatif")
def whatif(body: S.WhatIfIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t, bills, apps = tariff_for(user), user_bills(db, user), appliance_dicts(db, user)
    if not apps:
        raise HTTPException(400, "Add appliances first")
    actual = latest_units(bills, user, db)
    est = AP.analyse(apps, actual)
    base = body.base_units or actual or est["estimated_total"]
    return AP.what_if(apps, [c.model_dump() for c in body.changes], base, t, user.sanctioned_kw,
                      ent_for(t, bills), est["calibration_factor"])


# ---------- forecast / alerts ----------
@app.get("/forecast")
def forecast(user: User = Depends(current_user), db: Session = Depends(get_db)):
    t, bills = tariff_for(user), user_bills(db, user)
    hist = [b.units for b in bills]
    f = A.forecast_next(hist)
    if not f:
        raise HTTPException(400, "Add at least one bill first")
    ent = ent_for(t, bills)
    f["bill"] = T.compute_bill(f["units"], t, user.sanctioned_kw, ent)["total"]
    f["bill_low"] = T.compute_bill(f["low"], t, user.sanctioned_kw, ent)["total"]
    f["bill_high"] = T.compute_bill(f["high"], t, user.sanctioned_kw, ent)["total"]
    return {"history": [{"month": b.month, "units": b.units} for b in bills], "forecast": f,
            "anomaly": A.detect_anomaly(hist[:-1], hist[-1]) if len(hist) > 1 else None,
            "benchmark": A.benchmark(hist[-1], user.household_size) if hist else None}


@app.post("/alerts/refresh")
def refresh_alerts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    t, bills = tariff_for(user), user_bills(db, user)
    ent = ent_for(t, bills)
    db.execute(delete(Alert).where(Alert.user_id == user.id))
    new = []
    cs = cycle_state(db, user)
    if cs["units_so_far"] > 0:
        st = T.slab_status(cs["units_so_far"], t, user.sanctioned_kw, ent)
        nb = st["next_boundary"]
        proj = A.project_month_end(cs["units_so_far"], cs["day"], cs["days_in_cycle"], cs["daily"])
        if nb and nb["units_left"] <= 15:
            new.append(("slab", "warning", f"Only {nb['units_left']} units left before '{nb['label']}'. Next unit costs Rs {nb['next_unit_cost']}."))
        if nb and proj["projected_units"] > nb["at_units"]:
            new.append(("projection", "warning", f"Projected month-end usage {proj['projected_units']} units will cross '{nb['label']}'."))
    if len(bills) >= 5:
        an = A.detect_anomaly([b.units for b in bills[:-1]], bills[-1].units)
        if an["anomaly"]:
            new.append(("anomaly", "critical", f"Last bill ({bills[-1].units} units) is {an['pct_vs_mean']}% {an['direction']}er than your average (z={an['z_score']})."))
    if bills:
        f = A.forecast_next([b.units for b in bills])
        if ent and f["units"] > ent:
            new.append(("subsidy", "warning", f"Forecast {f['units']} units exceeds your free-unit entitlement of {ent}. You would lose the subsidy benefit."))
    for b in bills[-3:]:
        o = bill_out(b, t, user.sanctioned_kw, ent_for(t, bills, b.month))
        if o["audit"] and o["audit"]["flag"]:
            new.append(("audit", "warning", f"{b.month}: {o['audit']['message']}"))
    for k, sev, msg in new:
        db.add(Alert(user_id=user.id, kind=k, severity=sev, message=msg))
    db.commit()
    return list_alerts(user, db)


@app.get("/alerts")
def list_alerts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Alert).where(Alert.user_id == user.id).order_by(Alert.id.desc()))
    return [{"id": a.id, "kind": a.kind, "severity": a.severity, "message": a.message,
             "created_at": a.created_at.isoformat()} for a in rows]


# ---------- solar ----------
@app.post("/solar")
def solar(body: S.SolarIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t, bills = tariff_for(user), user_bills(db, user)
    units = body.units_per_month or (sum(b.units for b in bills[-12:]) / len(bills[-12:]) if bills else None)
    if not units:
        raise HTTPException(400, "Provide units_per_month or add bills")
    p = {**body.model_dump(exclude_none=True), "units_per_month": units}
    result = SO.solar_payback(p, t, user.sanctioned_kw, 0)
    variants = []
    for label, over in [("Grid-tied, net metering", {"mode": "net_metering", "battery_kwh": 0}),
                        ("Net billing, no battery", {"mode": "net_billing", "battery_kwh": 0}),
                        ("Net billing + 5 kWh battery", {"mode": "net_billing", "battery_kwh": 5})]:
        r = SO.solar_payback({**p, **over}, t, user.sanctioned_kw, 0)
        variants.append({"label": label, "payback_years": r["payback_years"], "net_cost": r["net_cost"],
                         "ten_year_net_savings": r["ten_year_net_savings"], "irr_percent": r["irr_percent"]})
    return {"result": result, "scenarios": variants}


# ---------- smart meter simulation (Tier 3 stand-in) ----------
@app.post("/simulate/meter")
def simulate(days: int = 30, user: User = Depends(current_user), db: Session = Depends(get_db)):
    apps = appliance_dicts(db, user) or [{**p, "qty": 1, "days_per_month": 30} for p in AP.PRESETS]
    today = date.today()
    total = 0
    last_series, last_truth = None, None
    for i in range(days):
        d = today - timedelta(days=days - 1 - i)
        series, truth = nilm.simulate_day(apps, seed=i + user.id)
        units = round(sum(series) / 60 / 1000, 2)
        r = db.scalar(select(Reading).where(Reading.user_id == user.id, Reading.day == d))
        if r: r.units = units
        else: db.add(Reading(user_id=user.id, day=d, units=units))
        total += units
        last_series, last_truth = series, truth
    db.commit()
    found = nilm.disaggregate(last_series, apps)
    return {"days_generated": days, "total_units": round(total, 1), "nilm_today": found,
            "ground_truth_today": last_truth, "power_series_w": last_series[::10]}


# ---------- admin (RBAC) ----------
@app.get("/admin/users")
def admin_users(_: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    return [{"id": u.id, "email": u.email, "role": u.role, "tariff_id": u.tariff_id,
             "created_at": u.created_at.isoformat()} for u in db.scalars(select(User))]
