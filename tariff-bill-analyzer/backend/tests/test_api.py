import os
os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["SECRET_KEY"] = "test-secret"
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine

Base.metadata.drop_all(engine)
client = TestClient(app)
client.__enter__()


def auth(email="a@example.com"):
    r = client.post("/auth/register", json={"email": email, "name": "A", "password": "password123", "consumer_no": "1234567890"})
    if r.status_code == 409:
        r = client.post("/auth/login", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_requires_auth():
    assert client.get("/bills").status_code == 401


def test_consumer_number_masked():
    h = auth()
    assert client.get("/auth/me", headers=h).json()["consumer_no"].endswith("890")
    assert "1234567" not in client.get("/auth/me", headers=h).text


def test_bill_flow_and_audit():
    h = auth()
    r = client.post("/bills", headers=h, json={"month": "2026-01", "units": 250, "amount_actual": 2000})
    assert r.status_code == 201 and r.json()["audit"]["flag"]
    assert client.post("/bills", headers=h, json={"month": "2026-01", "units": 1}).status_code == 409


def test_isolation_between_users():
    h1, h2 = auth("one@example.com"), auth("two@example.com")
    client.post("/bills", headers=h1, json={"month": "2026-02", "units": 100})
    assert client.get("/bills", headers=h2).json() == []


def test_admin_forbidden_for_user():
    assert client.get("/admin/users", headers=auth()).status_code == 403


def test_admin_allowed():
    h = auth("admin@example.com")
    assert client.get("/admin/users", headers=h).status_code == 200


def test_forecast_solar_whatif():
    h = auth("flow@example.com")
    for i, u in enumerate([180, 190, 200, 230, 260, 250]):
        client.post("/bills", headers=h, json={"month": f"2026-{i+1:02d}", "units": u})
    assert client.get("/forecast", headers=h).json()["forecast"]["units"] > 0
    assert client.post("/solar", headers=h, json={}).status_code == 200
    client.post("/appliances", headers=h, json={"name": "AC 1.5T", "watts": 1500, "hours_per_day": 6, "duty": .6})
    r = client.post("/whatif", headers=h, json={"changes": [{"name": "AC 1.5T", "delta_hours_per_day": -1}]})
    assert r.json()["bill_change"] < 0
    assert client.get("/slab-tracker?units_so_far=88&day=15&days_in_cycle=30", headers=h).status_code == 200
