# ATX Tee Times Watcher

Monitors Austin municipal golf courses and emails you the moment a tee time opens
in your chosen window. It does not auto-book - it watches for cancellations and
notifies you so you can grab the slot.

## How it works

- A background scanner polls the WebTrac search every 5 minutes, Tuesday 6:00am
  through Sunday night (Central Time). Mondays are off.
- Each user creates one or more **watches**: party size (1-4), 9/18 holes,
  course(s), target weekday(s), and a time window (e.g. Saturday 7:00-11:00am).
- When an available slot matches a watch, the user gets an email with the course,
  date, time, and number of open slots, plus a link to WebTrac to book it.

The scraper uses `curl_cffi` (Chrome TLS impersonation) to pass the site's
Cloudflare bot check. No login or stored credentials are required to read
availability.

## Stack

- Backend: FastAPI, SQLAlchemy (SQLite), APScheduler, Resend (email), curl_cffi + BeautifulSoup.
- Frontend: React + Vite + Tailwind (monochrome control-panel UI).
- Auth: email/password with bcrypt hashing and JWT bearer tokens.

## Project layout

```
backend/app/
  main.py            FastAPI app + lifespan (starts the scheduler)
  scheduler.py       APScheduler: 5-min scan, daily cleanup, weekly reminder
  config.py          Settings (env-driven)
  models.py          User, Watch, FoundSlot
  schemas.py         Pydantic request/response models
  auth/security.py   bcrypt + JWT, get_current_user
  routers/
    auth.py          signup / login / me
    watches.py       watch CRUD, found-slots, scan-now, scan-status
  services/
    scraper.py       WebTrac fetch + parse (curl_cffi, Playwright fallback)
    monitor_job.py   scan cycle: match watches, de-dupe, email
    email.py         Resend notifications
    cleanup.py       prune old found slots
    reminder_job.py  weekly "set up your watches" nudge
frontend/src/        React app (Dashboard, Watches, Opportunities, auth)
```

## Run locally

Prerequisites: Python 3.11+ with [uv](https://github.com/astral-sh/uv), Node 20+.

**1. Create `backend/.env`:**

```bash
# Generate: python3 -c "import secrets; print(secrets.token_urlsafe(48))"
JWT_SECRET=your-strong-secret

# Optional for local dev - leave RESEND_API_KEY blank to skip real emails
RESEND_API_KEY=
EMAIL_FROM=alerts@stoutoilandgas.com
BASE_URL=http://localhost:5173

DATABASE_URL=sqlite:///./atxteetimes.db
TIMEZONE=America/Chicago
ENABLE_SCHEDULER=true
DEBUG=true
```

With `DEBUG=true`, an insecure/missing `JWT_SECRET` only warns. In production
(`DEBUG=false`) the app refuses to start without a strong secret.

**2. Run both services** from the repo root with `./start.sh` (stop with
`./stop.sh`), or manually:

```bash
# backend - http://localhost:8000 (docs at /docs)
cd backend && uv sync && uv run uvicorn app.main:app --reload --port 8000

# frontend - http://localhost:5173 (proxies /api to :8000)
cd frontend && npm install && npm run dev
```

**3. Try it:** sign up, create a watch under **Watches**, and click **Scan now**
to run an immediate scan against the live site (ignores the Tue-Sun window and
is scoped to your own watches). Matches appear under **Opportunities**.

## Deploy

See [DEPLOY.md](DEPLOY.md) - a single $6/month DigitalOcean droplet runs the API,
scanner, database, and UI via Docker Compose.

## Configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `JWT_SECRET` | Signs auth tokens (required in production) | insecure default (dev only) |
| `RESEND_API_KEY` | Resend API key for emails | empty (emails skipped) |
| `EMAIL_FROM` | From address (must be on a Resend-verified domain) | `alerts@stoutoilandgas.com` |
| `BASE_URL` | Public app URL used in email links | `http://localhost:8000` |
| `ALLOW_SIGNUP` | Allow new account creation | `true` |
| `DATABASE_URL` | SQLAlchemy URL | `sqlite:///./atxteetimes.db` |
| `TIMEZONE` | Scan/schedule timezone | `America/Chicago` |
| `ENABLE_SCHEDULER` | Start the background scanner | `true` |
| `SCAN_INTERVAL_MINUTES` | Scan frequency | `5` |
| `SEND_WEEKLY_REMINDER` | Weekly setup-reminder email | `true` |
| `FOUND_SLOT_RETENTION_DAYS` | Days to keep found-slot history | `10` |
| `USE_PLAYWRIGHT_FALLBACK` | Use a browser if curl_cffi is blocked | `false` |
| `DEBUG` | Relaxes the JWT-secret startup check | `false` |
