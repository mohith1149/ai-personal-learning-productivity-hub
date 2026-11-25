# Setup

Get the hub running on one Windows machine for development or personal use. For a server, read [DEPLOYMENT.md](DEPLOYMENT.md) after this.
Optional services (e-mail, GitHub, YouTube, AI, n8n) are in [INTEGRATIONS.md](INTEGRATIONS.md); problems are in [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## You need

- Python 3.11 and Node 20 (with npm).
- Git. Nothing else: the database is a SQLite file the app creates itself.

## First-time install

```powershell
git clone <your repo url> ai-learning-hub
cd ai-learning-hub\backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

Open `backend\.env` and fill in the two required values. Everything else can stay empty.

| Setting | How to get it |
|---|---|
| `SECRET_KEY` (required, 32+ characters) | `.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `ENCRYPTION_KEY` | `.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

The backend refuses to start without `SECRET_KEY`. Changing it later signs you out; it does not damage data.

Create the database, then install the frontend:

```powershell
.venv\Scripts\python.exe -m alembic upgrade head
cd ..\frontend
npm install
```

## Run it

Two terminals:

```powershell
cd backend;  .venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
cd frontend; npm run dev
```

Open http://localhost:5173. The first visit asks you to create the one account; after that the same page is the sign-in. There is
exactly one account, so keep the password somewhere safe (there is no password reset).

Starter content such as the AI-engineering roadmap and course outlines is added the first time you open the page that uses it.
Check the backend is up: http://localhost:8000/api/health should answer `{"status":"ok","database":"ok",...}`. API docs are at
http://localhost:8000/docs while `ENVIRONMENT=development`.

## Updating

```powershell
git pull
cd backend;  .venv\Scripts\python.exe -m pip install -r requirements.txt
             .venv\Scripts\python.exe -m alembic upgrade head      # applies new database changes
cd ..\frontend; npm install
```

Restart the backend. Back up first if the pull changes anything under `backend\alembic\versions` (see [DEPLOYMENT.md](DEPLOYMENT.md#backups)).

## Run the tests

```powershell
cd backend;  .venv\Scripts\python.exe -m pytest -q
cd frontend; npm run typecheck; npm test; npm run build
```

Tests never touch your real database or call a real AI/GitHub/e-mail service: the backend suite forces AI off and blanks every key.
Run `npm test` from a path with an uppercase drive letter (`D:\...`); from Git Bash's `/d/...` Vitest fails to load.

## Where things live

| Path | What |
|---|---|
| `backend/.env` | Your settings and secrets. Git-ignored. |
| `backend/data/hub.db` | Your data (SQLite; `-wal` and `-shm` files next to it are normal while running). Git-ignored. |
| `backend/data/backups/` | Pre-change database copies. Git-ignored. |
| `backend/alembic/versions/` | Database migrations. |
| `backend/app/` | Backend: `routers` (HTTP), `services` (logic), `models`, `ai` (providers and tools). |
| `frontend/src/` | React app. |
| `docs/` | These guides and the n8n workflow. |
