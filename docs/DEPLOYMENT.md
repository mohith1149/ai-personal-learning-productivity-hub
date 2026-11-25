# Deployment

The hub is built for **one user on one machine**. This guide covers running it somewhere other than your dev terminal (a home server,
a small VPS) and keeping its data safe. It has not been load-tested because it does not need to be: one account, SQLite, one process.

## How the pieces fit

- The **backend** (FastAPI) serves only `/api/...`. It does not serve the web app.
- The **frontend** builds to static files in `frontend/dist`. Any web server can serve them.
- A **reverse proxy** puts both on **one public address**: static files for `/`, and `/api` forwarded to the backend. Same origin is
  what lets the session cookie work without cross-site settings.

## 1. Build the frontend

```powershell
cd frontend
npm ci
npm run build          # outputs frontend/dist
```

## 2. Production settings in `backend/.env`

```
ENVIRONMENT=production
SECRET_KEY=<new random 48+ chars; do not reuse the dev key>
ENCRYPTION_KEY=<new Fernet key>
COOKIE_SECURE=true
FRONTEND_URL=https://hub.example.com
BACKEND_URL=https://hub.example.com
```

- `FRONTEND_URL` and `BACKEND_URL` must be the **public address you type in the browser**. They drive the allowed origin for writes
  (anything else gets "Cross-origin request blocked") and the links inside e-mails.
- `COOKIE_SECURE=true` marks the session cookie HTTPS-only. Use it whenever the site is served over HTTPS (it should be). With plain
  `http://` on a remote address you will not be able to stay signed in, which is the correct failure: do not serve a login over HTTP.
- `ENVIRONMENT=production` turns off the interactive `/docs` and `/openapi.json` pages.
- Keep `SCHEDULER_MODE=internal` (default), or `n8n`/`off` as in [INTEGRATIONS.md](INTEGRATIONS.md).

## 3. Run the backend

Run **exactly one worker**. The built-in e-mail scheduler lives inside the process, so two workers would each send the same e-mail.

```powershell
cd backend
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers
```

Bind to `127.0.0.1` so only the proxy can reach it. Do not use `--reload` in production. To keep it running across logouts and
reboots, register that command with your platform's service manager (Windows: Task Scheduler "at startup" or a tool such as NSSM;
Linux: a systemd unit). The process must run as a user that can write `backend/data/`.

## 4. Reverse proxy

Caddy (automatic HTTPS) is the least work:

```
hub.example.com {
    encode gzip
    handle /api/* {
        reverse_proxy 127.0.0.1:8000
    }
    handle {
        root * C:/path/to/ai-learning-hub/frontend/dist
        try_files {path} /index.html
        file_server
    }
}
```

`try_files ... /index.html` matters: the app uses client-side routes such as `/reports`, which must load the app, not a 404.
nginx is equivalent: `location /api/ { proxy_pass http://127.0.0.1:8000; }` plus `try_files $uri /index.html;` for the rest.

If the machine is reachable from the internet, remember the app has one login and nothing else in front of it. Put it behind a VPN
(Tailscale, WireGuard) or an access proxy if you can, use a long password, and keep the box patched.

## 5. Verify

1. `https://hub.example.com/api/health` shows `{"status":"ok","database":"ok",...}`.
2. Sign in, reload the page (still signed in), open **Reports**.
3. Settings → **Send a test e-mail**, and AI assistant → **Test the connection**, if you use them.

## Backups

All your data is the one SQLite file `backend/data/hub.db`, plus `backend/.env` (your keys). Do **not** just copy `hub.db` while the app is
running: recent writes may still be in the `hub.db-wal` file. Use SQLite's own backup, which is safe while the app runs:

```powershell
cd backend
.venv\Scripts\python.exe -c "import sqlite3,sys; s=sqlite3.connect('data/hub.db'); d=sqlite3.connect(sys.argv[1]); s.backup(d); d.close(); s.close()" data/backups/hub-manual.db
```

Schedule that (Task Scheduler / cron) with a dated file name, and copy the result **off the machine**. Also keep a copy of `.env`
somewhere private so you do not have to recreate your keys (`ENCRYPTION_KEY` is reserved for encrypting stored tokens).

**Restore:** stop the backend, delete `hub.db-wal` and `hub.db-shm` next to the database, copy the backup over `hub.db`, run
`alembic upgrade head`, start the backend. Try a restore once, on a spare folder, before you need it.

Take a backup before every update that adds a migration.

## Upgrading the database later

SQLite is fine for one user. If you ever move to PostgreSQL, set `DATABASE_URL=postgresql+psycopg://user:pass@host/db`, run
`alembic upgrade head` against it, and copy your data across. The schema is plain SQLAlchemy, but the data copy is not automated and
has not been tried.

## Security checklist

- [ ] HTTPS only, `COOKIE_SECURE=true`, `ENVIRONMENT=production`.
- [ ] New `SECRET_KEY` and `ENCRYPTION_KEY` (not the development ones), stored outside git.
- [ ] Backend bound to `127.0.0.1`; only the proxy is public.
- [ ] `/docs` returns 404.
- [ ] Offsite backups of `hub.db` and `.env`, and a restore tried once.
- [ ] Provider keys (AI, YouTube, GitHub, SMTP) have only the permissions they need; revoke any that leaked.
