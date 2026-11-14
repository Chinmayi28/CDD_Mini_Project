# 🔐 SecureVault – Simple Version
**CDD Mini Project · Team 10 · C1 Batch**

A small web app to store documents safely: upload, tag, search, share, keep versions, see activity. Files are **encrypted on disk**.

## What is inside (only 5 important files)
| File | What it does |
|---|---|
| `app/main.py` | the whole backend (FastAPI + SQLite) |
| `static/index.html` | the whole website (plain HTML + JavaScript) |
| `tests/test_app.py` | automatic tests |
| `Dockerfile`, `docker-compose.yml` | run everything in Docker |
| `.github/workflows/ci.yml` | GitHub Actions (CI/CD) |

## Features
1. Register / login (passwords stored as salted hashes)
2. Upload documents with title, category, tags
3. Search by text, category or tag
4. Versions – upload a new version, download any old one
5. Sharing – give another user **view** or **edit** permission; or make an **expiring link**
6. Activity history – who did what and when
7. Extra challenge: **roles** (first user = admin; admin pages are protected) and **encrypted files**

## Step 1 – Run with Docker (easiest)
```bash
docker compose up --build
```
Open **http://localhost:8000** → click Register. The **first account becomes the admin**.
Stop with `Ctrl+C`.

## Step 1 (alternative) – Run without Docker
```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Open **http://localhost:8000**.

## Step 2 – Try it (demo script)
1. Register the first user (admin). Open a private window and register a second user.
2. Upload a document with a category and tags. Try the search boxes.
3. Click **Open** → upload a new version → both versions appear → download an old one.
4. **Share** it with the second user as *view* – they can download but cannot add versions. Change to *edit*.
5. Create a **share link**, open it in a window where nobody is logged in.
6. Click **Activity** to show the history. Log in as admin → **Admin** page.
7. Show the encryption: files in `data/files/` are unreadable
   (Docker: `docker compose exec securevault sh -c "head -c 100 /code/data/files/*.enc | head -c 200"`).

## Step 3 – Run the tests
```bash
pip install -r requirements.txt
pytest -v
```

## Step 4 – GitHub + CI/CD
```bash
git init
git add .
git commit -m "SecureVault"
git branch -M main
git remote add origin https://github.com/<your-username>/<repo>.git
git push -u origin main
```
Open the repo → **Actions** tab. The pipeline (1) installs dependencies and runs the tests, then (2) builds the Docker image, starts the container and checks `/api/health`. Take a screenshot of the green ticks for your report.

## Step 5 – Work split (5 members)
| Member | Part |
|---|---|
| Ganavi K | Login, register, roles/admin (`register`, `login`, `admin_*` in `main.py`) |
| GP Chinmayi | Upload, list, search |
| Khushi R | Versions + download |
| Keerthana SM | Website (`index.html`) |
| Keerthana YT | Sharing, encryption, Docker, CI/CD, tests |

## Viva answers in one line
* **How is the file protected?** Encrypted with Fernet (AES) before saving; key comes from `SECRET_KEY`.
* **How are permissions checked?** `get_access()` runs on every request: owner / edit / view, otherwise "not found".
* **How do versions work?** Every upload adds a row in the `versions` table; old files are never overwritten.
* **How do share links stay safe?** Random token + expiry time; every public download is logged.
* **Where is data stored?** SQLite database + encrypted files in the `data/` folder (a Docker volume).

## Important
Keep `SECRET_KEY` the same forever. If it changes, old files can no longer be decrypted.
Set your own with `SECRET_KEY=something-long docker compose up --build`.
