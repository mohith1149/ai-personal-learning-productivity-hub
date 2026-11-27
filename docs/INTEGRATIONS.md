# Integrations

Every integration is optional and off until configured. All settings go in `backend/.env`; restart the backend after changing it.
Keys stay on the backend: they are never sent to the browser, logged or returned by the API.

| Integration | Needed for | Cost |
|---|---|---|
| [E-mail (SMTP / Gmail)](#e-mail-reminders) | daily plan, overdue nudge and weekly report e-mails | free |
| [GitHub](#github) | verifying challenge commits, filling a project from a repo | free |
| [YouTube](#youtube) | importing a channel or playlist into a video collection | free quota |
| [AI assistant](#ai-assistant) | chat, project autofill | Groq/Gemini free tiers; Anthropic paid |
| [n8n](#n8n-instead-of-the-built-in-scheduler) | running reminders from n8n instead of the app | free |

## E-mail reminders

Gmail with an App Password (a normal password will not work):

1. Turn on 2-Step Verification for the Google account.
2. Google Account → Security → 2-Step Verification → **App passwords** → create one → copy the 16 characters.
3. In `.env`:

```
EMAIL_PROVIDER=smtp
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=you@gmail.com
SMTP_PASSWORD=<the app password>
EMAIL_FROM=you@gmail.com
```

4. Restart the backend. Open **Settings**, set the reminder address, switch the reminders you want on, press **Send a test e-mail**.

The page reports the real outcome: *Sent* only after the mail server accepted the message, otherwise *Failed* with the reason.
Other SMTP providers work with their own host, port (587 STARTTLS) and credentials. Sending through the Gmail API (OAuth) is not built.

How sending behaves:

- Three kinds: the **daily plan** (at your reminder time), an **evening overdue** nudge, and a **weekly report** (on the weekday and time you choose).
- The built-in scheduler checks every minute. Each e-mail goes out at most once per day (weekly: once per week). An empty plan sends nothing.
- If the backend was off at the scheduled time, the e-mail goes out when it next runs later that same day (weekly: that same weekday); a missed day is not sent afterwards.
- A failed send is retried up to 3 times, at least 10 minutes apart. Times are in your timezone. Every attempt is listed on the Settings page.

## GitHub

Works with no setup for **public** repos:

- **Verify on GitHub** (daily challenge) checks that the commit exists, matches your message, was made that day and changes code.
- **Fill from GitHub** (new project) reads name, description or README intro, languages and topics.
- The assistant's repo lookup reads the same public data when you paste a repo link in the chat.

For **private** repos, or to avoid the unauthenticated rate limit, add a personal access token:

1. GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate.
2. Repository access: the repos you want checked. Permissions: **Contents: read-only** (and Metadata: read, which is automatic).
3. `GITHUB_TOKEN=<token>` in `.env`.

`GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` are reserved for "Sign in with GitHub", which is not built; leave them empty.

## YouTube

Needed only to import channels and playlists. Pasting individual video links needs no key.

1. https://console.cloud.google.com → create or pick a project.
2. APIs & Services → Library → enable **YouTube Data API v3**.
3. APIs & Services → Credentials → Create credentials → API key. Restrict it to the YouTube Data API.
4. `YOUTUBE_API_KEY=<key>` in `.env`.

Every API call costs 1 unit of the default 10,000 per day, and 50 videos cost 2 calls, so a personal playlist import is far inside the free quota.

## AI assistant

`AI_PROVIDER` is the **default** provider (`none`, `groq`, `gemini` or `anthropic`). A key alone never turns AI on, but every provider that
has a key appears in the chat's **model menu**, so you can switch provider and model per message. Your pick is remembered in the browser.

| Provider | Setup | Limits |
|---|---|---|
| **Groq** (recommended start) | key from https://console.groq.com/keys → `GROQ_API_KEY`, `GROQ_MODEL=openai/gpt-oss-120b` | generous free tier; may keep free-tier prompts |
| **Gemini** | key from https://aistudio.google.com/apikey → `GEMINI_API_KEY`, `GEMINI_MODEL=gemini-3.5-flash` | about 5 requests a minute free; a tool-using chat can hit it |
| **Anthropic** | key from https://console.anthropic.com → `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL=claude-opus-5-5` | pay-as-you-go. Tested against a fake server only |

```
AI_PROVIDER=groq
GROQ_API_KEY=<key>
```

Then open **AI assistant** and press **Test the connection** (one tiny real request). The chat appears once a test passes.
The model menu fetches each provider's current model list (names get retired) and falls back to a short built-in list.

What the assistant can and cannot do:

- It has 19 tools. The 14 read tools (today's and pending tasks, plan, dashboard, courses, next videos, active projects, roadmap, habits,
  challenge, weekly report, slipping tasks, goals and pace, GitHub repo lookup) run immediately. The 5 write tools (create, complete and reschedule a task; log project
  progress; plan a challenge) only **propose** a change, which waits in the approval queue on the AI assistant page.
- It cannot complete a challenge, delete anything or change anything without your approval.
- **Morning check-in** and **Evening check-out** buttons start a guided review of your day.
- Prompts and the data the tools return are sent to the provider you choose. Keep that in mind for free tiers that may retain prompts.

## n8n instead of the built-in scheduler

Use this only if you already run n8n. Never run both schedulers: you would get duplicate e-mails.

1. `.env`: `SCHEDULER_MODE=n8n` and `AUTOMATION_API_KEY=<a long random string>`; restart the backend.
2. In n8n: Import from file → `docs/n8n-run-due.json`.
3. Open the **Run due e-mails** node, replace `PASTE_YOUR_AUTOMATION_API_KEY` with the same key. Activate the workflow.

The workflow calls `POST /api/automation/run-due` every minute with header `X-Automation-Key`. That endpoint does only what is due
(same once-a-day rules). In the node use `127.0.0.1`, not `localhost`: n8n resolves `localhost` to IPv6 and the backend listens on IPv4.
If n8n runs in Docker, use `http://host.docker.internal:8000`. `SCHEDULER_MODE=off` disables all automatic sending.
