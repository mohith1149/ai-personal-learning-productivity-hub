# Troubleshooting

Find your symptom, apply the fix. Messages quoted here are the ones the app shows.

## Startup and sign-in

| Symptom | Cause and fix |
|---|---|
| Backend exits with a validation error mentioning `secret_key` | `SECRET_KEY` missing or shorter than 32 characters in `backend/.env`. Generate one (see [SETUP.md](SETUP.md)). |
| `no such table` errors, or a page shows a server error right after an update | The database is behind the code. Run `alembic upgrade head` in `backend`, restart. |
| Page loads but every call fails / blank data | Backend not running, or not on port 8000. Check http://localhost:8000/api/health. The dev server proxies `/api` to port 8000 (override with the `API_TARGET` environment variable). |
| New page (e.g. Reports) missing or 404 | Old backend still running, or stale browser cache. Restart the backend and hard-refresh (Ctrl+Shift+R). |
| "Too many failed attempts. Try again later." | 5 wrong passwords in 15 minutes locks sign-in for the window. Wait 15 minutes. |
| Forgot the password | There is no reset screen. Your data is safe in `hub.db`; the account row can only be replaced by editing the database. Keep the password in a password manager. |
| Signed out on every reload (deployed) | `COOKIE_SECURE=true` over plain `http://`, or the site address differs from `FRONTEND_URL`. Serve over HTTPS and set both URLs to the exact public address. |
| "Cross-origin request blocked" | The address in the browser is not `FRONTEND_URL`/`BACKEND_URL`. Fix the two settings and restart. |

## Tests

| Symptom | Fix |
|---|---|
| `npm test` fails to load Vitest | Run it from a path with an uppercase drive letter (`D:\...`), not Git Bash's `/d/...`. |
| A backend test uses my real keys or database | It should not: `tests/conftest.py` forces AI off and blanks keys. A failure here is a bug; report it. |

## E-mail

| Symptom | Fix |
|---|---|
| Test e-mail is *Failed* with an authentication error | Use a Gmail **App Password**, not your normal password; 2-Step Verification must be on. |
| Nothing is *Sent* and nothing is listed in history | `EMAIL_PROVIDER` is still `none`, the reminder switch is off, or the plan was empty (empty plans send nothing). |
| Duplicate e-mails | Two schedulers are running: the built-in one and n8n, or two backend workers. Use one (`SCHEDULER_MODE`) and one worker. |
| n8n node fails to connect | Use `127.0.0.1` instead of `localhost` (IPv6), or `host.docker.internal` from Docker. A 401 means the key in the node differs from `AUTOMATION_API_KEY`; a 503 means `AUTOMATION_API_KEY` is not set in `.env`. |
| An e-mail did not arrive on a day the backend was off | A missed day is not sent afterwards. Only the same day is caught up. |

## AI assistant

| Symptom | Fix |
|---|---|
| No chat window | Chat shows only after a successful **Test the connection**, and only if `AI_PROVIDER` is not `none` and that provider's key is set. |
| "The Gemini API rejected the request. Check GEMINI_API_KEY and GEMINI_MODEL" | Wrong key, or the model name was retired. Pick a current model in the menu, or fix `GEMINI_MODEL`. |
| "Gemini doesn't know that model" / Groq model not found | Model names get retired. Choose another in the model menu (it lists the provider's live models) or update `*_MODEL` in `.env`. |
| HTTP 429 / "rate limit" | Free-tier limits. Gemini allows about 5 requests a minute and a tool-using answer uses several: wait a minute, or switch to Groq in the model menu. |
| HTTP 503 | The provider is overloaded. Try again shortly. |
| "the secure connection was rejected (a certificate check failed)" | Antivirus HTTPS scanning or a proxy is re-signing traffic. The app already uses the Windows certificate store; add the scanner's root certificate to Windows, or turn off HTTPS scanning for the python process. The app never disables certificate checks. |
| "Couldn't reach the … API. Check your connection" | Network or firewall. A brief outage is retried automatically 3 times. |
| The assistant says it cannot open links | Only GitHub repo links are looked up (public repos). It has no general web access by design. |
| The assistant proposed something but nothing changed | Proposals wait for you on the AI assistant page: **Approve** or reject them. |

## GitHub, YouTube, data

| Symptom | Fix |
|---|---|
| Verify on GitHub: repo not found | Private repo: set `GITHUB_TOKEN` (Contents: read) and restart. Check the URL. |
| GitHub rate-limit errors | Unauthenticated calls are limited per hour. Set `GITHUB_TOKEN`. |
| YouTube import says the key is missing or invalid | Set `YOUTUBE_API_KEY`, and make sure **YouTube Data API v3** is enabled for that Google Cloud project. |
| Report numbers differ from what I expected | Days are your **local** calendar days (your profile timezone). Future days are blank and the previous-period comparison uses the same number of days. |
| `alembic check` or a migration complains about `ai_memories` | That table is from the removed memory feature. It is deliberately ignored by migrations; leave it or drop it by hand after a backup. |
| Database is locked | Two processes writing at once (a second backend, or a tool holding the file open). Stop the extras. Back up with SQLite's backup command, never by copying a running database. |

## Still stuck

Backend logs print to the terminal (or your service manager's log). Reproduce the problem, copy the last error lines, and look at
`/docs` (development only) to try the endpoint directly.
