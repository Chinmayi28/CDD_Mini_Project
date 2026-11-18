"""Appliance consumption, calibration to meter, savings rules, what-if and reduction planning."""
from .tariff import compute_bill, marginal_rate, r2

PRESETS = [
    {"name": "Ceiling fan", "watts": 70, "hours_per_day": 10, "duty": 1.0},
    {"name": "LED bulb", "watts": 9, "hours_per_day": 6, "duty": 1.0},
    {"name": "Refrigerator", "watts": 150, "hours_per_day": 24, "duty": 0.4},
    {"name": "AC 1.5T", "watts": 1500, "hours_per_day": 6, "duty": 0.6},
    {"name": "Geyser", "watts": 2000, "hours_per_day": 0.5, "duty": 1.0},
    {"name": "TV", "watts": 100, "hours_per_day": 4, "duty": 1.0},
    {"name": "Washing machine", "watts": 500, "hours_per_day": 0.7, "duty": 1.0},
    {"name": "Mixer/grinder", "watts": 500, "hours_per_day": 0.3, "duty": 1.0},
    {"name": "Water pump", "watts": 750, "hours_per_day": 0.5, "duty": 1.0},
    {"name": "Wi-Fi router", "watts": 12, "hours_per_day": 24, "duty": 1.0},
]

# keyword -> (suggestion text, fractional energy saving)
RULES = [
    ("ac", "Set the AC to 24-26 C (about 6% saving per degree) or replace with a 5-star inverter AC", 0.25),
    ("geyser", "Use a timer / heat only what you need; shorten by 10 minutes", 0.20),
    ("bulb", "Switch remaining non-LED bulbs to LED", 0.0),
    ("fan", "Replace with a BLDC fan (roughly half the power)", 0.50),
    ("refrigerator", "Keep it away from walls, defrost regularly, avoid overfilling", 0.10),
    ("tv", "Use eco mode and switch off at the socket instead of standby", 0.15),
]


def monthly_kwh(a, days=30):
    return a["watts"] * a.get("qty", 1) * a["hours_per_day"] * a.get("days_per_month", days) / 30 * days * a.get("duty", 1.0) / 1000


def analyse(apps, actual_units=None):
    rows = [{**a, "est_kwh": round(monthly_kwh(a), 1)} for a in apps]
    est_total = sum(r["est_kwh"] for r in rows)
    factor = (actual_units / est_total) if (actual_units and est_total) else 1.0
    for r in rows:
        r["calibrated_kwh"] = round(r["est_kwh"] * factor, 1)
        r["share_pct"] = round(r["est_kwh"] / est_total * 100, 1) if est_total else 0
    unaccounted = round(actual_units - est_total, 1) if actual_units else None
    return {"appliances": sorted(rows, key=lambda r: -r["est_kwh"]), "estimated_total": round(est_total, 1),
            "actual_units": actual_units, "calibration_factor": round(factor, 3),
            "unaccounted_units": unaccounted,
            "accuracy_note": "Estimates are approximate. Calibration scales them to match the metered total."}


def suggestions(apps, base_units, t, kw=1.0, ent=0, factor=1.0):
    out, base = [], compute_bill(base_units, t, kw, ent)["total"]
    for a in apps:
        kwh = monthly_kwh(a) * factor
        for key, text, frac in RULES:
            if key in a["name"].lower() and frac > 0 and kwh > 0:
                new = compute_bill(max(base_units - kwh * frac, 0), t, kw, ent)["total"]
                out.append({"appliance": a["name"], "tip": text, "units_saved": round(kwh * frac, 1),
                            "rupees_saved_per_month": r2(base - new)})
    return sorted(out, key=lambda s: -s["rupees_saved_per_month"])


def what_if(apps, changes, base_units, t, kw=1.0, ent=0, factor=1.0):
    """changes: [{name, delta_hours_per_day}] -> before/after bill + slab impact."""
    by = {a["name"]: a for a in apps}
    delta_kwh, detail = 0.0, []
    for c in changes:
        a = by.get(c["name"])
        if not a:
            continue
        new_hours = min(max(a["hours_per_day"] + c["delta_hours_per_day"], 0), 24)
        d = (monthly_kwh({**a, "hours_per_day": new_hours}) - monthly_kwh(a)) * factor
        delta_kwh += d
        detail.append({"name": a["name"], "new_hours": round(new_hours, 2), "delta_kwh": round(d, 1)})
    new_units = max(base_units + delta_kwh, 0)
    b0, b1 = compute_bill(base_units, t, kw, ent), compute_bill(new_units, t, kw, ent)
    return {"before_units": round(base_units, 1), "after_units": round(new_units, 1),
            "before_bill": b0["total"], "after_bill": b1["total"], "bill_change": r2(b1["total"] - b0["total"]),
            "detail": detail, "marginal_rate_now": marginal_rate(base_units, t, kw, ent)}


def reduction_plan(apps, units_to_cut, factor=1.0, max_cut_fraction=0.5):
    """Minimum-sacrifice plan: cut the biggest hourly consumers first, never more than 50% of one appliance."""
    plan, remaining = [], units_to_cut
    ranked = sorted(apps, key=lambda a: -(a["watts"] * a.get("qty", 1) * a.get("duty", 1.0)))
    for a in ranked:
        if remaining <= 0:
            break
        kwh_per_hour_month = a["watts"] * a.get("qty", 1) * a.get("duty", 1.0) / 1000 * 30 * factor
        if kwh_per_hour_month <= 0:
            continue
        max_hours = a["hours_per_day"] * max_cut_fraction
        need_hours = remaining / kwh_per_hour_month
        cut = min(need_hours, max_hours)
        if cut > 0.05:
            plan.append({"name": a["name"], "reduce_hours_per_day": round(cut, 2),
                         "units_saved": round(cut * kwh_per_hour_month, 1)})
            remaining -= cut * kwh_per_hour_month
    return {"units_to_cut": round(units_to_cut, 1), "plan": plan, "fully_covered": remaining <= 0.5}
