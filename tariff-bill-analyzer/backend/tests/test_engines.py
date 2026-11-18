from app.engine import analytics as A, appliances as AP, solar as SO, nilm
from app.engine.tariff import get_tariff

T1 = get_tariff("karnataka_sample_v1")
APPS = [{**p, "qty": 1, "days_per_month": 30} for p in AP.PRESETS]


def test_forecast_rising_series():
    f = A.forecast_next([180, 190, 200, 230, 260, 250])
    assert f["low"] <= f["units"] <= f["high"] and f["units"] > 200


def test_anomaly_flags_spike():
    assert A.detect_anomaly([200, 205, 198, 202, 201], 330)["anomaly"]
    assert not A.detect_anomaly([200, 205, 198, 202, 201], 204)["anomaly"]


def test_projection_and_budget():
    p = A.project_month_end(88, 15, 30)
    assert p["projected_units"] == 176.0
    assert A.daily_budget(88, 100, 15)["safe_daily_units"] == 0.8


def test_appliance_calibration_matches_meter():
    r = AP.analyse(APPS, 320)
    assert abs(sum(a["calibrated_kwh"] for a in r["appliances"]) - 320) < 2


def test_whatif_reduces_bill():
    r = AP.what_if(APPS, [{"name": "AC 1.5T", "delta_hours_per_day": -1}], 320, T1)
    assert r["after_units"] < r["before_units"] and r["bill_change"] < 0


def test_reduction_plan_covers_gap():
    assert AP.reduction_plan(APPS, 20)["fully_covered"]


def test_solar_payback_sane():
    s = SO.solar_payback({"units_per_month": 300, "roof_area_m2": 30}, T1)
    assert 0 < s["payback_years"] < 12 and s["subsidy"] > 0 and len(s["years"]) == 25


def test_solar_roof_limit():
    s = SO.solar_payback({"units_per_month": 900, "roof_area_m2": 15}, T1)
    assert s["system_kw"] <= 1.5 and s["limited_by_roof"]


def test_central_subsidy_cap():
    assert SO.central_subsidy(10) == 78000


def test_nilm_finds_big_loads():
    ser, _ = nilm.simulate_day(APPS)
    names = [f["name"] for f in nilm.disaggregate(ser, APPS)]
    assert "AC 1.5T" in names
