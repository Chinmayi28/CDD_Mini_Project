"""Forecasting, anomaly detection, month-end projection, benchmarking."""
import math, statistics as st


def forecast_next(history):
    """Blend of 3-point moving average + short trend (+ same-month-last-year if 13+ points)."""
    h = [float(x) for x in history]
    n = len(h)
    if n == 0:
        return None
    if n < 3:
        m = st.mean(h)
        return {"units": round(m, 1), "low": round(m * .85, 1), "high": round(m * 1.15, 1), "method": "mean"}
    ma = st.mean(h[-3:])
    w = h[-6:]
    xs = list(range(len(w)))
    xm, ym = st.mean(xs), st.mean(w)
    slope = sum((x - xm) * (y - ym) for x, y in zip(xs, w)) / max(sum((x - xm) ** 2 for x in xs), 1e-9)
    pred, method = ma + slope * 2, "moving-average + trend"
    if n >= 13:
        prev = h[n - 12]
        base = st.mean(h[n - 15:n - 12]) if n >= 15 else prev
        growth = (ma / base) if base else 1
        pred = 0.5 * pred + 0.5 * prev * growth
        method = "seasonal blend (same month last year) + trend"
    errs = [h[i] - st.mean(h[i - 3:i]) for i in range(3, n)] or [h[-1] - ma]
    sd = st.pstdev(errs) if len(errs) > 1 else abs(errs[0])
    pred = max(pred, 0)
    return {"units": round(pred, 1), "low": round(max(pred - 1.28 * sd, 0), 1),
            "high": round(pred + 1.28 * sd, 1), "method": method}


def detect_anomaly(history, current):
    h = [float(x) for x in history]
    if len(h) < 4:
        return {"anomaly": False, "reason": "Need at least 4 past months"}
    mu, sd = st.mean(h), st.pstdev(h)
    z = (current - mu) / sd if sd > 1e-6 else 0.0
    pct = (current - mu) / mu * 100 if mu else 0
    flag = abs(z) >= 2 or (sd < 1e-6 and abs(pct) > 30)
    return {"anomaly": bool(flag), "z_score": round(z, 2), "mean": round(mu, 1),
            "pct_vs_mean": round(pct, 1), "direction": "high" if current > mu else "low"}


def project_month_end(units_so_far, day, days_in_cycle, daily_readings=None):
    day = max(1, min(day, days_in_cycle))
    recent = [d for d in (daily_readings or [])][-7:]
    pace = (sum(recent) / len(recent)) if recent else units_so_far / day
    left = days_in_cycle - day
    return {"projected_units": round(units_so_far + pace * left, 1), "daily_pace": round(pace, 2),
            "days_left": left, "basis": "last-7-days pace" if recent else "cycle-average pace"}


def daily_budget(units_so_far, boundary_at, days_left):
    left = boundary_at - units_so_far
    if left < 0:
        return {"safe_daily_units": 0, "already_crossed": True}
    return {"safe_daily_units": round(left / days_left, 2) if days_left > 0 else round(left, 2),
            "already_crossed": False}


# Illustrative benchmark table: replace with utility-published averages.
BENCHMARK = {1: 90, 2: 130, 3: 170, 4: 210, 5: 250, 6: 290}


def benchmark(units, household_size):
    avg = BENCHMARK.get(min(max(household_size, 1), 6))
    sd = avg * 0.30
    z = (units - avg) / sd
    pct = 0.5 * (1 + math.erf(z / math.sqrt(2))) * 100
    label = "below typical" if units < avg * .85 else "above typical" if units > avg * 1.15 else "typical"
    return {"household_size": household_size, "typical_units": avg, "your_units": units,
            "percentile_estimate": round(pct), "label": label,
            "note": "Illustrative reference data; anonymised cohort data would replace it."}
