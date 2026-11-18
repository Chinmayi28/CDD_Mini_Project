"""Configuration-driven tariff engine.

Rules live in JSON files (backend/tariffs/*.json). Adding a utility == adding a file.
Supports telescopic slabs, whole-consumption ("cliff") slabs, fixed charges,
fuel adjustment, duty/tax and free-unit subsidy schemes.
"""
import json, math
from functools import lru_cache
from pathlib import Path

TARIFF_DIR = Path(__file__).resolve().parents[2] / "tariffs"
r2 = lambda x: round(x + 1e-9, 2)


@lru_cache(maxsize=None)
def _load(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def list_tariffs():
    out = []
    for p in sorted(TARIFF_DIR.glob("*.json")):
        t = _load(str(p))
        out.append({k: t[k] for k in ("id", "utility", "category", "version", "slab_mode")})
    return out


def get_tariff(tariff_id: str) -> dict:
    p = TARIFF_DIR / f"{tariff_id}.json"
    if not p.exists():
        raise KeyError(f"Unknown tariff '{tariff_id}'")
    return _load(str(p))


def energy_charge(units: float, t: dict):
    """Return (total, lines). lines = per-slab breakdown."""
    lines, slabs = [], t["slabs"]
    if units <= 0:
        return 0.0, lines
    if t.get("slab_mode", "telescopic") == "telescopic":
        prev, rem = 0.0, units
        for s in slabs:
            cap = (s["upto"] - prev) if s["upto"] is not None else math.inf
            used = min(rem, cap)
            if used > 0:
                lines.append({"from": prev, "to": prev + used, "units": r2(used),
                              "rate": s["rate"], "amount": r2(used * s["rate"])})
            rem -= used
            if s["upto"] is not None:
                prev = s["upto"]
            if rem <= 0:
                break
    else:  # cliff: every unit is billed at the rate of the slab the total lands in
        for s in slabs:
            if s["upto"] is None or units <= s["upto"]:
                lines.append({"from": 0, "to": units, "units": r2(units), "rate": s["rate"],
                              "amount": r2(units * s["rate"])})
                break
    return r2(sum(l["amount"] for l in lines)), lines


def entitlement(t: dict, history_units=None) -> int:
    """Free units a household is entitled to (avg of last 12 months + buffer, capped)."""
    sub = t.get("subsidy", {})
    if not sub.get("enabled"):
        return 0
    hist = [h for h in (history_units or []) if h is not None][-12:]
    if not hist:
        return int(min(sub["cap_units"], sub.get("default_units_no_history", 0)))
    avg = sum(hist) / len(hist)
    return int(min(sub["cap_units"], math.ceil(avg * (1 + sub.get("buffer_percent", 0) / 100))))


def compute_bill(units: float, t: dict, sanctioned_kw: float = 1.0, entitled_units: int = 0) -> dict:
    units = max(float(units), 0.0)
    energy, lines = energy_charge(units, t)
    fc = t["fixed_charges"]
    fixed = r2(fc["per_kw"] * max(sanctioned_kw, fc.get("min_kw", 0)))
    fuel = r2(units * t.get("fuel_adjustment_per_unit", 0))

    subsidy = 0.0
    if entitled_units > 0 and units > 0:
        covered = min(units, entitled_units)
        subsidy = energy_charge(covered, t)[0] + r2(covered * t.get("fuel_adjustment_per_unit", 0))
        if units <= entitled_units:      # fully covered -> fixed charge waived too
            subsidy += fixed
    taxable = max(energy + fixed + fuel - subsidy, 0)
    duty = r2(taxable * t.get("electricity_duty_percent", 0) / 100)
    total = r2(taxable + duty)
    return {
        "units": units, "energy_charges": energy, "slab_lines": lines, "fixed_charges": fixed,
        "fuel_adjustment": fuel, "subsidy": r2(subsidy), "electricity_duty": duty,
        "total": total, "effective_rate": r2(total / units) if units else 0.0,
        "entitled_units": entitled_units, "tariff_version": t["version"],
    }


def marginal_rate(units: float, t: dict, kw=1.0, ent=0) -> float:
    """Real rupee cost of ONE more unit right now (captures cliffs & subsidy edges)."""
    return r2(compute_bill(units + 1, t, kw, ent)["total"] - compute_bill(units, t, kw, ent)["total"])


def boundaries(units: float, t: dict, kw=1.0, ent=0):
    """Upcoming cost boundaries: tariff slabs and the free-unit entitlement edge."""
    out = []
    for i, s in enumerate(t["slabs"]):
        if s["upto"] is not None and units <= s["upto"]:
            extra = r2(compute_bill(s["upto"] + 1, t, kw, ent)["total"] - compute_bill(s["upto"], t, kw, ent)["total"])
            out.append({"type": "slab", "label": f"Slab {i + 2} ({t['slabs'][i + 1]['rate']}/unit)",
                        "at_units": s["upto"], "units_left": r2(s["upto"] - units),
                        "next_unit_cost": extra,
                        "cliff_jump": r2(compute_bill(s["upto"] + 1, t, kw, ent)["total"] - compute_bill(s["upto"], t, kw, ent)["total"]) if t.get("slab_mode") == "cliff" else 0})
    if ent > 0 and units <= ent:
        out.append({"type": "subsidy", "label": "Free-unit entitlement ends", "at_units": ent,
                    "units_left": r2(ent - units),
                    "next_unit_cost": r2(compute_bill(ent + 1, t, kw, ent)["total"] - compute_bill(ent, t, kw, ent)["total"]),
                    "cliff_jump": r2(compute_bill(ent + 1, t, kw, ent)["total"] - compute_bill(ent, t, kw, ent)["total"])})
    return sorted(out, key=lambda b: b["units_left"])


def slab_status(units: float, t: dict, kw=1.0, ent=0) -> dict:
    cur = next((i for i, s in enumerate(t["slabs"]) if s["upto"] is None or units <= s["upto"]), len(t["slabs"]) - 1)
    b = boundaries(units, t, kw, ent)
    return {"current_slab": cur + 1, "current_rate": t["slabs"][cur]["rate"],
            "marginal_cost_per_unit": marginal_rate(units, t, kw, ent),
            "next_boundary": b[0] if b else None, "all_boundaries": b}


def compare_tariffs(history_units, t_old, t_new, kw=1.0):
    rows = []
    for m, u in history_units:
        o = compute_bill(u, t_old, kw)["total"]; n = compute_bill(u, t_new, kw)["total"]
        rows.append({"month": m, "units": u, "old": o, "new": n, "diff": r2(n - o)})
    return {"rows": rows, "old_version": t_old["version"], "new_version": t_new["version"],
            "total_diff": r2(sum(r["diff"] for r in rows)),
            "annualised_diff": r2(sum(r["diff"] for r in rows) / max(len(rows), 1) * 12)}
