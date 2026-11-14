"""SecureVault - the whole backend in one file (FastAPI + SQLite + encrypted files)."""
import base64
import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from cryptography.fernet import Fernet
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ------------------------------------------------------------------ settings
DB_PATH = os.getenv("DB_PATH", "data/securevault.db")
FILES_DIR = os.getenv("FILES_DIR", "data/files")
SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
MAX_MB = 25
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# Files are encrypted with a key made from SECRET_KEY (Fernet = AES + HMAC).
fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode()).digest()))


# ------------------------------------------------------------------ database helpers
def query(sql, args=(), one=False):
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(sql, args).fetchall()]
    con.close()
    if one:
        return rows[0] if rows else None
    return rows


def run(sql, args=()):
    con = sqlite3.connect(DB_PATH)
    cur = con.execute(sql, args)
    con.commit()
    last_id = cur.lastrowid
    con.close()
    return last_id


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    os.makedirs(FILES_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT UNIQUE,
            password TEXT, role TEXT, created TEXT);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER);
        CREATE TABLE IF NOT EXISTS documents(
            id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER, title TEXT,
            category TEXT, tags TEXT, created TEXT);
        CREATE TABLE IF NOT EXISTS versions(
            id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id INTEGER, number INTEGER,
            filename TEXT, stored TEXT, size INTEGER, uploaded_by INTEGER, created TEXT);
        CREATE TABLE IF NOT EXISTS shares(
            doc_id INTEGER, user_id INTEGER, level TEXT, UNIQUE(doc_id, user_id));
        CREATE TABLE IF NOT EXISTS links(
            token TEXT PRIMARY KEY, doc_id INTEGER, expires TEXT);
        CREATE TABLE IF NOT EXISTS activity(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, doc_id INTEGER,
            doc_title TEXT, action TEXT, detail TEXT, created TEXT);
        """
    )
    con.commit()
    con.close()


init_db()


# ------------------------------------------------------------------ passwords, login, roles
def hash_pw(password, salt=None):
    salt = salt or secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()
    return f"{salt}${digest}"


def check_pw(password, stored):
    salt, digest = stored.split("$")
    return hmac.compare_digest(hash_pw(password, salt).split("$")[1], digest)


def current_user(authorization: str = Header(default="")):
    token = authorization.replace("Bearer ", "").strip()
    user = query(
        "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ?", (token,), one=True
    )
    if not user:
        raise HTTPException(401, "Please log in")
    return user


def admin_only(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin access required")
    return user


def login_response(user_id):
    token = secrets.token_hex(24)
    run("INSERT INTO sessions(token, user_id) VALUES(?, ?)", (token, user_id))
    u = query("SELECT id, name, email, role FROM users WHERE id = ?", (user_id,), one=True)
    return {"token": token, "user": u}


def log(user_id, doc, action, detail=""):
    run(
        "INSERT INTO activity(user_id, doc_id, doc_title, action, detail, created) VALUES(?,?,?,?,?,?)",
        (user_id, doc["id"] if doc else None, doc["title"] if doc else None, action, detail, now()),
    )


# ------------------------------------------------------------------ document access
# roles: "view" (see + download) < "edit" (+ upload new versions) < "owner" (+ share, delete)
def get_access(doc_id, user):
    doc = query("SELECT * FROM documents WHERE id = ?", (doc_id,), one=True)
    if not doc:
        raise HTTPException(404, "Document not found")
    if doc["owner_id"] == user["id"]:
        return doc, "owner"
    share = query("SELECT level FROM shares WHERE doc_id = ? AND user_id = ?", (doc_id, user["id"]), one=True)
    if share:
        return doc, share["level"]
    raise HTTPException(404, "Document not found")  # hide documents you cannot access


def require(role, *allowed):
    if role not in allowed:
        raise HTTPException(403, "You do not have permission to do this")


# ------------------------------------------------------------------ encrypted files
async def read_upload(file: UploadFile):
    data = await file.read()
    if not data:
        raise HTTPException(400, "The file is empty")
    if len(data) > MAX_MB * 1024 * 1024:
        raise HTTPException(413, f"File is larger than {MAX_MB} MB")
    return data


def add_version(doc_id, number, filename, data, user_id):
    stored = secrets.token_hex(16) + ".enc"
    with open(os.path.join(FILES_DIR, stored), "wb") as f:
        f.write(fernet.encrypt(data))  # only encrypted bytes ever touch the disk
    run(
        "INSERT INTO versions(doc_id, number, filename, stored, size, uploaded_by, created) VALUES(?,?,?,?,?,?,?)",
        (doc_id, number, filename, stored, len(data), user_id, now()),
    )


def send_version(v):
    with open(os.path.join(FILES_DIR, v["stored"]), "rb") as f:
        data = fernet.decrypt(f.read())
    return Response(
        data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(v["filename"])},
    )


def latest_version(doc_id):
    return query("SELECT * FROM versions WHERE doc_id = ? ORDER BY number DESC LIMIT 1", (doc_id,), one=True)


# ------------------------------------------------------------------ app
app = FastAPI(title="SecureVault")


class Register(BaseModel):
    name: str
    email: str
    password: str


class Login(BaseModel):
    email: str
    password: str


class ShareIn(BaseModel):
    email: str
    level: str  # "view" or "edit"


class LinkIn(BaseModel):
    hours: int = 24


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ---------- accounts
@app.post("/api/register")
def register(d: Register):
    email = d.email.strip().lower()
    if not d.name.strip() or "@" not in email or len(d.password) < 6:
        raise HTTPException(400, "Enter a name, a valid email and a password of at least 6 characters")
    if query("SELECT id FROM users WHERE email = ?", (email,), one=True):
        raise HTTPException(409, "Email already registered")
    first_user = query("SELECT COUNT(*) AS n FROM users", one=True)["n"] == 0
    uid = run(
        "INSERT INTO users(name, email, password, role, created) VALUES(?,?,?,?,?)",
        (d.name.strip(), email, hash_pw(d.password), "admin" if first_user else "user", now()),
    )
    log(uid, None, "register")
    return login_response(uid)


@app.post("/api/login")
def login(d: Login):
    user = query("SELECT * FROM users WHERE email = ?", (d.email.strip().lower(),), one=True)
    if not user or not check_pw(d.password, user["password"]):
        raise HTTPException(401, "Wrong email or password")
    log(user["id"], None, "login")
    return login_response(user["id"])


# ---------- documents: upload, list/search
@app.post("/api/documents")
async def upload(
    file: UploadFile = File(...),
    title: str = Form(""),
    category: str = Form("General"),
    tags: str = Form(""),
    user=Depends(current_user),
):
    data = await read_upload(file)
    filename = file.filename or "document"
    clean_tags = ",".join(t.strip().lower() for t in tags.split(",") if t.strip())
    doc_id = run(
        "INSERT INTO documents(owner_id, title, category, tags, created) VALUES(?,?,?,?,?)",
        (user["id"], title.strip() or filename, category.strip() or "General", clean_tags, now()),
    )
    add_version(doc_id, 1, filename, data, user["id"])
    log(user["id"], {"id": doc_id, "title": title.strip() or filename}, "upload", filename)
    return {"id": doc_id}


@app.get("/api/documents")
def list_documents(q: str = "", category: str = "", tag: str = "", user=Depends(current_user)):
    sql = """
        SELECT d.*, u.name AS owner_name,
               CASE WHEN d.owner_id = ? THEN 'owner' ELSE s.level END AS my_role,
               (SELECT MAX(number) FROM versions WHERE doc_id = d.id) AS version
        FROM documents d
        JOIN users u ON u.id = d.owner_id
        LEFT JOIN shares s ON s.doc_id = d.id AND s.user_id = ?
        WHERE (d.owner_id = ? OR s.user_id = ?)
    """
    args = [user["id"]] * 4
    if q.strip():
        sql += " AND (d.title LIKE ? OR d.category LIKE ? OR d.tags LIKE ?)"
        args += [f"%{q.strip()}%"] * 3
    if category.strip():
        sql += " AND LOWER(d.category) = LOWER(?)"
        args.append(category.strip())
    if tag.strip():
        sql += " AND d.tags LIKE ?"
        args.append(f"%{tag.strip().lower()}%")
    rows = query(sql + " ORDER BY d.id DESC", args)
    for r in rows:
        r["tags"] = [t for t in r["tags"].split(",") if t]
    return rows


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: int, user=Depends(current_user)):
    doc, role = get_access(doc_id, user)
    require(role, "owner")
    for v in query("SELECT stored FROM versions WHERE doc_id = ?", (doc_id,)):
        try:
            os.remove(os.path.join(FILES_DIR, v["stored"]))
        except FileNotFoundError:
            pass
    for table in ("versions", "shares", "links"):
        run(f"DELETE FROM {table} WHERE doc_id = ?", (doc_id,))
    run("DELETE FROM documents WHERE id = ?", (doc_id,))
    log(user["id"], doc, "delete")
    return {"ok": True}


# ---------- versions + download
@app.get("/api/documents/{doc_id}/versions")
def versions(doc_id: int, user=Depends(current_user)):
    get_access(doc_id, user)
    return query(
        """SELECT v.number, v.filename, v.size, v.created, u.name AS uploaded_by
           FROM versions v JOIN users u ON u.id = v.uploaded_by
           WHERE v.doc_id = ? ORDER BY v.number DESC""",
        (doc_id,),
    )


@app.post("/api/documents/{doc_id}/versions")
async def new_version(doc_id: int, file: UploadFile = File(...), user=Depends(current_user)):
    doc, role = get_access(doc_id, user)
    require(role, "owner", "edit")
    data = await read_upload(file)
    number = latest_version(doc_id)["number"] + 1
    add_version(doc_id, number, file.filename or "document", data, user["id"])
    log(user["id"], doc, "new_version", f"v{number}")
    return {"version": number}


@app.get("/api/documents/{doc_id}/download")
def download(doc_id: int, version: int = 0, user=Depends(current_user)):
    doc, _ = get_access(doc_id, user)
    if version:
        v = query("SELECT * FROM versions WHERE doc_id = ? AND number = ?", (doc_id, version), one=True)
    else:
        v = latest_version(doc_id)
    if not v:
        raise HTTPException(404, "Version not found")
    response = send_version(v)
    log(user["id"], doc, "download", f"v{v['number']}")
    return response


# ---------- sharing: with other users, and with an expiring link
@app.post("/api/documents/{doc_id}/share")
def share(doc_id: int, d: ShareIn, user=Depends(current_user)):
    doc, role = get_access(doc_id, user)
    require(role, "owner")
    if d.level not in ("view", "edit"):
        raise HTTPException(400, "Level must be 'view' or 'edit'")
    target = query("SELECT id FROM users WHERE email = ?", (d.email.strip().lower(),), one=True)
    if not target:
        raise HTTPException(404, "No user with that email")
    if target["id"] == user["id"]:
        raise HTTPException(400, "You already own this document")
    run("INSERT OR REPLACE INTO shares(doc_id, user_id, level) VALUES(?,?,?)", (doc_id, target["id"], d.level))
    log(user["id"], doc, "share", f"{d.email} -> {d.level}")
    return {"ok": True}


@app.get("/api/documents/{doc_id}/shares")
def list_shares(doc_id: int, user=Depends(current_user)):
    _, role = get_access(doc_id, user)
    require(role, "owner")
    return query(
        "SELECT u.id AS user_id, u.name, u.email, s.level FROM shares s JOIN users u ON u.id = s.user_id WHERE s.doc_id = ?",
        (doc_id,),
    )


@app.delete("/api/documents/{doc_id}/shares/{user_id}")
def unshare(doc_id: int, user_id: int, user=Depends(current_user)):
    doc, role = get_access(doc_id, user)
    require(role, "owner")
    run("DELETE FROM shares WHERE doc_id = ? AND user_id = ?", (doc_id, user_id))
    log(user["id"], doc, "unshare")
    return {"ok": True}


@app.post("/api/documents/{doc_id}/link")
def create_link(doc_id: int, d: LinkIn, user=Depends(current_user)):
    doc, role = get_access(doc_id, user)
    require(role, "owner")
    hours = max(1, min(d.hours, 720))
    token = secrets.token_urlsafe(24)
    expires = (datetime.now(timezone.utc) + timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    run("INSERT INTO links(token, doc_id, expires) VALUES(?,?,?)", (token, doc_id, expires))
    log(user["id"], doc, "create_link", f"valid {hours}h")
    return {"url": f"/api/link/{token}", "expires": expires}


@app.get("/api/link/{token}")
def open_link(token: str):
    link = query("SELECT * FROM links WHERE token = ?", (token,), one=True)
    if not link:
        raise HTTPException(404, "Link not found")
    if link["expires"] < now():
        raise HTTPException(410, "This link has expired")
    doc = query("SELECT * FROM documents WHERE id = ?", (link["doc_id"],), one=True)
    if not doc:
        raise HTTPException(404, "Document no longer exists")
    response = send_version(latest_version(doc["id"]))
    log(None, doc, "public_download", "via share link")
    return response


# ---------- activity history
@app.get("/api/activity")
def my_activity(user=Depends(current_user)):
    return query(
        """SELECT a.created, a.action, a.detail, a.doc_title, COALESCE(u.name, 'Public link') AS who
           FROM activity a LEFT JOIN users u ON u.id = a.user_id
           WHERE a.user_id = ? OR a.doc_id IN (SELECT id FROM documents WHERE owner_id = ?)
           ORDER BY a.id DESC LIMIT 100""",
        (user["id"], user["id"]),
    )


# ---------- admin only (role-based access control)
@app.get("/api/admin/users")
def admin_users(admin=Depends(admin_only)):
    return query(
        """SELECT u.id, u.name, u.email, u.role, u.created,
                  (SELECT COUNT(*) FROM documents WHERE owner_id = u.id) AS documents
           FROM users u ORDER BY u.id"""
    )


@app.get("/api/admin/activity")
def admin_activity(admin=Depends(admin_only)):
    return query(
        """SELECT a.created, a.action, a.detail, a.doc_title, COALESCE(u.name, 'Public link') AS who
           FROM activity a LEFT JOIN users u ON u.id = a.user_id
           ORDER BY a.id DESC LIMIT 200"""
    )


# The website (static/index.html) is served by the same app.
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
