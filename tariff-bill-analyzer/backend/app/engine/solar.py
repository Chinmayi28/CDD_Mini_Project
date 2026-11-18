"""Solar payback: net-metering or net-billing, battery, loan, escalation, degradation, IRR/NPV, CO2."""
from .tariff import compute_bill


def central_subsidy(kw):
    """PM Surya Ghar-style schedule (verify current scheme before quoting)."""
    if kw <= 2:
        s = 30000 * kw
    else:
        s = 60000 + 18000 * (min(kw, 3) - 2)
    return min(s, 78000)


def irr(flows):
    lo, hi = -0.99, 1.0
    f = lambda r: sum(c / (1 + r) ** i for i, c in enumerate(flows))
    if f(lo) * f(hi) > 0:
        return None
    for _ in range(100):
        mid = (lo + hi) / 2
        if f(lo) * f(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return round((lo + hi) / 2 * 100, 2)


def _annual_bill(units_m, gen_m, p, t, kw, ent):
    """Return annual bill with solar for a given monthly generation."""
    if p["mode"] == "net_metering":
        net = units_m - gen_m
        bill = compute_bill(max(net, 0), t, kw, ent)["total"]
        credit = max(-net, 0) * p["export_rate"]
        return (bill - credit) * 12, 0.0
    self_direct = min(gen_m * p["daytime_share"], units_m)
    surplus = gen_m - self_direct
    shift = min(p["battery_kwh"] * 0.9 * 30, surplus, max(units_m - self_direct, 0))
    self_used = self_direct + shift
    exported = gen_m - self_used
    bill = compute_bill(max(units_m - self_used, 0), t, kw, ent)["total"] - exported * p["export_rate"]
    return bill * 12, exported * 12


def solar_payback(p, t, kw=1.0, ent=0):
    p = {"sun_hours": 5.0, "performance_ratio": 0.8, "cost_per_kw": 55000, "degradation": 0.005,
         "tariff_escalation": 0.03, "om_percent": 0.01, "export_rate": 3.0, "mode": "net_metering",
         "daytime_share": 0.35, "battery_kwh": 0.0, "battery_cost_per_kwh": 18000, "state_subsidy": 0.0,
         "loan_pct": 0.0, "loan_rate": 0.09, "loan_years": 5, "discount_rate": 0.08, "years": 25,
         "roof_area_m2": 30, "units_per_month": 200, **p}
    units_m = p["units_per_month"]
    need_kw = units_m * 12 / (p["sun_hours"] * 365 * p["performance_ratio"])
    roof_kw = p["roof_area_m2"] / 10.0
    kwp = p.get("system_kw") or max(round(min(need_kw, roof_kw) * 2) / 2, 0.5)
    cost = kwp * p["cost_per_kw"]
    batt_cost = p["battery_kwh"] * p["battery_cost_per_kwh"] if p["mode"] == "net_billing" else 0.0
    sub = central_subsidy(kwp) + p["state_subsidy"]
    net_cost = cost + batt_cost - sub
    base_year = compute_bill(units_m, t, kw, ent)["total"] * 12

    loan = net_cost * p["loan_pct"]
    r, n = p["loan_rate"] / 12, p["loan_years"] * 12
    emi = loan * r / (1 - (1 + r) ** -n) if loan and r else (loan / n if loan else 0)
    upfront = net_cost - loan

    rows, flows, cum = [], [-upfront], -upfront
    payback = None
    save10 = 0.0
    for y in range(1, p["years"] + 1):
        gen_year = kwp * p["sun_hours"] * 365 * p["performance_ratio"] * (1 - p["degradation"]) ** (y - 1)
        after, exported = _annual_bill(units_m, gen_year / 12, p, t, kw, ent)
        esc = (1 + p["tariff_escalation"]) ** (y - 1)
        saving = (base_year - after) * esc
        om = cost * p["om_percent"]
        inverter = cost * 0.10 if y == 12 else 0
        loan_pay = emi * 12 if y <= p["loan_years"] else 0
        net = saving - om - inverter - loan_pay
        prev = cum
        cum += net
        if payback is None and cum >= 0:
            payback = round(y - 1 + (-prev / net if net else 0), 1)
        if y <= 10:
            save10 += saving - om
        flows.append(net)
        rows.append({"year": y, "generation_kwh": round(gen_year), "gross_saving": round(saving),
                     "net_cash": round(net), "cumulative": round(cum)})
    npv = sum(c / (1 + p["discount_rate"]) ** i for i, c in enumerate(flows))
    return {
        "system_kw": kwp, "limited_by_roof": need_kw > roof_kw, "mode": p["mode"],
        "gross_cost": round(cost + batt_cost), "subsidy": round(sub), "net_cost": round(net_cost),
        "upfront_cash": round(upfront), "monthly_emi": round(emi),
        "year1_generation_kwh": rows[0]["generation_kwh"], "year1_saving": rows[0]["gross_saving"],
        "payback_years": payback, "ten_year_net_savings": round(save10 - upfront),
        "ten_year_gross_savings": round(save10),
        "irr_percent": irr(flows), "npv": round(npv),
        "co2_avoided_tonnes_per_year": round(rows[0]["generation_kwh"] * 0.82 / 1000, 2),
        "backup_hours_essential_load": round(p["battery_kwh"] * 0.9 / 0.5, 1) if p["battery_kwh"] else 0,
        "years": rows,
        "assumptions": "Flat consumption; tariff escalation applied to savings; inverter replacement in year 12; "
                       "free-unit schemes only considered if an entitlement is passed. Verify subsidy and export rate.",
    }
