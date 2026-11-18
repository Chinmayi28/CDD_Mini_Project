"""Tariff tests built from hand-calculated bills (the CI gate for any tariff change)."""
import pytest
from app.engine import tariff as T

V1 = T.get_tariff("karnataka_sample_v1")


def test_telescopic_250_units():
    b = T.compute_bill(250, V1, sanctioned_kw=2)
    assert b["energy_charges"] == 100 * 4.15 + 100 * 5.60 + 50 * 7.15      # 1332.50
    assert b["fixed_charges"] == 120.0
    assert b["fuel_adjustment"] == 90.0
    assert b["total"] == pytest.approx((1332.5 + 120 + 90) * 1.09, abs=0.02)


def test_zero_units_pays_only_fixed():
    b = T.compute_bill(0, V1)
    assert b["energy_charges"] == 0 and b["total"] == pytest.approx(60 * 1.09, abs=0.02)


def test_cliff_mode_reprices_all_units():
    c = T.get_tariff("cliff_demo")
    assert T.compute_bill(150, c)["energy_charges"] == 150 * 4.5
    assert T.compute_bill(151, c)["energy_charges"] == 151 * 6.0
    assert T.compute_bill(151, c)["total"] - T.compute_bill(150, c)["total"] > 200   # a real cliff


def test_slab_status_units_left():
    s = T.slab_status(88, V1)
    assert s["next_boundary"]["units_left"] == 12 and s["current_slab"] == 1


def test_free_units_fully_covered():
    ent = T.entitlement(V1, [120] * 12)           # 120 * 1.1 = 132
    assert ent == 132
    assert T.compute_bill(130, V1, 1, ent)["total"] == 0


def test_free_units_cliff_when_exceeded():
    ent = 132
    assert T.compute_bill(133, V1, 1, ent)["total"] > 50   # fixed charge + 1 unit return


def test_entitlement_capped_and_default():
    assert T.entitlement(V1, [400] * 12) == 200
    assert T.entitlement(V1, []) == 53


def test_marginal_rate_includes_duty_and_fuel():
    assert T.marginal_rate(10, V1) == pytest.approx((4.15 + 0.36) * 1.09, abs=0.01)


def test_tariff_revision_compare():
    v2 = T.get_tariff("karnataka_sample_v2")
    r = T.compare_tariffs([("2026-01", 200), ("2026-02", 250)], V1, v2)
    assert r["total_diff"] > 0 and len(r["rows"]) == 2


def test_unknown_tariff():
    with pytest.raises(KeyError):
        T.get_tariff("nope")
