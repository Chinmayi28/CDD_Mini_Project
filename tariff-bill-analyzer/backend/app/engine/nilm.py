"""Smart-meter simulation (Tier-3 stand-in) + a lightweight NILM step-change disaggregator."""
import random


def simulate_day(apps, base_load_w=60, seed=7, noise_w=2.0):
    """1-minute aggregate power series (W) and ground-truth events from appliance list."""
    rnd = random.Random(seed)
    series = [base_load_w] * 1440
    truth = []
    for a in apps:
        if a["name"].lower().startswith(("refrigerator", "wi-fi")):
            continue  # always-on / cycling loads fold into the base load
        total_min = int(a["hours_per_day"] * 60)
        sessions = 1 if total_min < 90 else 2
        for _ in range(sessions):
            dur = max(total_min // sessions, 5)
            start = rnd.randint(0, 1440 - dur - 1)
            for m in range(start, start + dur):
                series[m] += a["watts"]
            truth.append({"name": a["name"], "start": start, "minutes": dur})
    series = [round(v + rnd.gauss(0, noise_w), 1) for v in series]
    return series, truth


def disaggregate(series, apps, tol=0.2, min_step=40):
    cands = [a for a in apps if not a["name"].lower().startswith(("refrigerator", "wi-fi"))]
    events = []
    for i in range(1, len(series)):
        d = series[i] - series[i - 1]
        if abs(d) >= min_step:
            events.append((i, d))
    open_ons, found = {}, {}
    for i, d in events:
        best = min(cands, key=lambda a: abs(abs(d) - a["watts"]), default=None)
        if not best or abs(abs(d) - best["watts"]) / best["watts"] > tol:
            continue
        n = best["name"]
        if d > 0:
            open_ons.setdefault(n, []).append(i)
        elif open_ons.get(n):
            start = open_ons[n].pop(0)
            f = found.setdefault(n, {"name": n, "sessions": 0, "minutes": 0})
            f["sessions"] += 1
            f["minutes"] += i - start
    by = {a["name"]: a for a in cands}
    for f in found.values():
        f["kwh_today"] = round(by[f["name"]]["watts"] * f["minutes"] / 60 / 1000, 2)
    return sorted(found.values(), key=lambda f: -f["kwh_today"])
