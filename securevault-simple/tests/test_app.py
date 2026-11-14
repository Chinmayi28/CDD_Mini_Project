import glob
import os
import tempfile

# configure BEFORE importing the app
tmp = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(tmp, "test.db")
os.environ["FILES_DIR"] = os.path.join(tmp, "files")
os.environ["SECRET_KEY"] = "test-secret"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)
SECRET_TEXT = b"my very secret rent agreement"


def register(name, email):
    r = client.post("/api/register", json={"name": name, "email": email, "password": "secret123"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


@pytest.fixture(scope="module")
def admin():  # the first user to register becomes the admin
    return register("Admin", "admin@test.com")


@pytest.fixture(scope="module")
def alice(admin):
    return register("Alice", "alice@test.com")


@pytest.fixture(scope="module")
def bob(admin):
    return register("Bob", "bob@test.com")


def upload(headers, title="Rent", content=SECRET_TEXT):
    r = client.post(
        "/api/documents",
        headers=headers,
        files={"file": ("rent.txt", content, "text/plain")},
        data={"title": title, "category": "Legal", "tags": "home, 2026"},
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_login_and_wrong_password(alice):
    ok = client.post("/api/login", json={"email": "alice@test.com", "password": "secret123"})
    bad = client.post("/api/login", json={"email": "alice@test.com", "password": "nope-nope"})
    assert ok.status_code == 200 and bad.status_code == 401


def test_login_required():
    assert client.get("/api/documents").status_code == 401


def test_upload_is_encrypted_on_disk_and_downloads_back(alice):
    doc_id = upload(alice)
    for path in glob.glob(os.path.join(os.environ["FILES_DIR"], "*.enc")):
        assert SECRET_TEXT not in open(path, "rb").read()
    r = client.get(f"/api/documents/{doc_id}/download", headers=alice)
    assert r.status_code == 200 and r.content == SECRET_TEXT


def test_search_by_text_category_and_tag(alice):
    upload(alice, title="Passport")
    assert any(d["title"] == "Passport" for d in client.get("/api/documents?q=pass", headers=alice).json())
    assert client.get("/api/documents?category=legal", headers=alice).json()
    assert client.get("/api/documents?tag=2026", headers=alice).json()
    assert client.get("/api/documents?tag=zzz", headers=alice).json() == []


def test_versions(alice):
    doc_id = upload(alice, title="Versioned")
    r = client.post(
        f"/api/documents/{doc_id}/versions", headers=alice, files={"file": ("rent.txt", b"second", "text/plain")}
    )
    assert r.json()["version"] == 2
    assert client.get(f"/api/documents/{doc_id}/download", headers=alice).content == b"second"
    assert client.get(f"/api/documents/{doc_id}/download?version=1", headers=alice).content == SECRET_TEXT
    assert [v["number"] for v in client.get(f"/api/documents/{doc_id}/versions", headers=alice).json()] == [2, 1]


def test_sharing_permissions(alice, bob):
    doc_id = upload(alice, title="Shared")
    assert client.get(f"/api/documents/{doc_id}/download", headers=bob).status_code == 404  # no access yet

    client.post(f"/api/documents/{doc_id}/share", headers=alice, json={"email": "bob@test.com", "level": "view"})
    assert client.get(f"/api/documents/{doc_id}/download", headers=bob).content == SECRET_TEXT
    no_edit = client.post(
        f"/api/documents/{doc_id}/versions", headers=bob, files={"file": ("x.txt", b"x", "text/plain")}
    )
    assert no_edit.status_code == 403

    client.post(f"/api/documents/{doc_id}/share", headers=alice, json={"email": "bob@test.com", "level": "edit"})
    ok = client.post(f"/api/documents/{doc_id}/versions", headers=bob, files={"file": ("x.txt", b"x", "text/plain")})
    assert ok.status_code == 200
    assert client.delete(f"/api/documents/{doc_id}", headers=bob).status_code == 403  # only the owner deletes


def test_share_link(alice):
    doc_id = upload(alice, title="Link")
    link = client.post(f"/api/documents/{doc_id}/link", headers=alice, json={"hours": 1}).json()
    r = client.get(link["url"])  # no login needed
    assert r.status_code == 200 and r.content == SECRET_TEXT
    assert client.get("/api/link/not-a-token").status_code == 404


def test_activity_history(alice):
    doc_id = upload(alice, title="Logged")
    client.get(f"/api/documents/{doc_id}/download", headers=alice)
    actions = [a["action"] for a in client.get("/api/activity", headers=alice).json()]
    assert "upload" in actions and "download" in actions


def test_delete_document(alice):
    doc_id = upload(alice, title="Temp")
    assert client.delete(f"/api/documents/{doc_id}", headers=alice).status_code == 200
    assert client.get(f"/api/documents/{doc_id}/download", headers=alice).status_code == 404


def test_only_admin_can_use_admin_pages(alice, admin):
    assert client.get("/api/admin/users", headers=alice).status_code == 403
    assert client.get("/api/admin/users", headers=admin).status_code == 200
    doc_id = upload(alice, title="Private")
    assert client.get(f"/api/documents/{doc_id}/download", headers=admin).status_code == 404
