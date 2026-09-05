# OA Reminder System

A small personal web app to track upcoming online assessments (OAs) and get
push notifications on your phone (via [ntfy](https://ntfy.sh)) 24h, 6h, and
2h before each one. Built for one placement season — fully free to run.

## Architecture

```
Browser (dashboard) ──HTTP──▶ Render (FastAPI, free, sleeps when idle)
                                     │
                           SQLAlchemy / Session Pooler
                                     ▼
                            Supabase Postgres (free)
                                     ▲
                           same tick logic, on-demand
                                     │
GitHub Actions cron (~10 min) ──HTTP (X-API-Key)──▶ POST /api/scheduler/tick
                                     │
                               (tick logic) ──▶ ntfy.sh ──▶ phone
```

No in-process scheduler, no "keep Render alive 24/7" workaround needed:
GitHub Actions' free cron pings the app on a schedule, which both wakes it
from sleep and runs the reminder check. Reminder correctness comes entirely
from DB flags (`reminder_24_sent_at` etc.), not timer precision — safe across
restarts, cold starts, and cron delays.

## One-time deployment steps

### 1. Supabase project + schema
1. Create a free project at [supabase.com](https://supabase.com).
2. Open **SQL Editor** → paste in [`schema.sql`](schema.sql) → **Run**.
3. Get your connection string: dashboard → **Connect** button → **Direct
   connection** tab → pick **Session pooler** (NOT Direct connection —
   Render's networking is IPv4-only and Direct connection is IPv6).
4. It looks like `postgresql://postgres.xxxx:[PASSWORD]@aws-0-<region>.pooler.supabase.com:5432/postgres`.
   Fill in your real password, and change the scheme to `postgresql+psycopg://`.

### 2. ntfy topic
1. Install the ntfy app: [Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy) / [iOS](https://apps.apple.com/us/app/ntfy/id1625396347).
2. Pick a private, hard-to-guess topic name (it's the only thing protecting
   it on the free public server) and subscribe to it in the app.

### 3. Push this repo to GitHub
```
git add -A
git commit -m "Initial OA reminder system"
```
Create a **public** repo on github.com (public → unlimited free GitHub
Actions minutes; no secrets are ever committed, so this is safe), then:
```
git remote add origin https://github.com/<you>/<repo>.git
git branch -M main
git push -u origin main
```

### 4. Render web service
1. New → Web Service → connect the GitHub repo → it should auto-detect
   `render.yaml` (Docker runtime).
2. Set these environment variables in the Render dashboard:
   | Key | Value |
   |---|---|
   | `DATABASE_URL` | your Session Pooler connection string (step 1) |
   | `API_KEY` | a long random string — this is your app's password |
   | `NTFY_SERVER` | `https://ntfy.sh` |
   | `NTFY_TOPIC` | your topic name (step 2) |
   | `NTFY_TOKEN` | leave blank unless your topic needs auth |
   | `TIMEZONE` | `Asia/Kolkata` (already defaults in render.yaml) |
3. Deploy. Note your service's URL, e.g. `https://oa-reminder-xxxx.onrender.com`.

### 5. GitHub Actions secret + variable
In the GitHub repo: **Settings → Secrets and variables → Actions**:
- **Secrets** tab → New repository secret → `API_KEY` = same value as Render's `API_KEY`.
- **Variables** tab → New repository variable → `RENDER_URL` = your Render URL from step 4 (no trailing slash).

### 6. Test everything
1. Open your Render URL in a browser (and on your phone) — the dashboard should load.
2. Add a real OA through the UI.
3. In GitHub → **Actions** tab → "Reminder tick" workflow → **Run workflow** (manual trigger) to confirm it returns success without waiting for the cron schedule.
4. Once confirmed, the `*/10 * * * *` schedule takes over automatically — no further action needed.

## Local development

```
python -m venv .venv
.venv/Scripts/activate   # or source .venv/bin/activate on macOS/Linux
pip install -r requirements-dev.txt
cp .env.example .env     # fill in DATABASE_URL, API_KEY, NTFY_SERVER, NTFY_TOPIC
uvicorn backend.main:app --reload
```

Run tests:
```
pytest
```

## Environment variables

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | yes | Supabase **Session pooler** connection string, `postgresql+psycopg://...` |
| `API_KEY` | yes | Shared secret for all write endpoints (`X-API-Key` header) and the scheduler tick |
| `NTFY_SERVER` | yes | `https://ntfy.sh` unless self-hosting |
| `NTFY_TOPIC` | yes | Your private topic name |
| `NTFY_TOKEN` | no | Only if your ntfy topic requires auth |
| `TIMEZONE` | no | Informational; defaults to `Asia/Kolkata` in render.yaml |

Never commit `.env` — it's git-ignored. Use `.env.example` as the template.
