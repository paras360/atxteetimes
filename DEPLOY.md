# Deploying to a DigitalOcean droplet

Everything (API, the 5-minute scanner, SQLite, and the React UI) runs in one
container. A $6/month droplet is plenty.

## 1. Create the droplet
- DigitalOcean -> Create -> Droplet
- Image: **Ubuntu 24.04 LTS**
- Plan: **Basic / Regular, 1 GB RAM / 1 vCPU ($6/mo)**
- Add your SSH key, create.

## 2. Install Docker
```bash
ssh root@YOUR_DROPLET_IP
curl -fsSL https://get.docker.com | sh
```

## 3. Get the code + configure
```bash
git clone YOUR_REPO_URL atxteetimes && cd atxteetimes
cp .env.example .env
# generate a JWT secret:
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
nano .env   # paste JWT_SECRET, RESEND_API_KEY, EMAIL_FROM, BASE_URL=http://YOUR_DROPLET_IP
```

`JWT_SECRET` and `BASE_URL` are required - compose refuses to start without
them. After you've created your own account, set `ALLOW_SIGNUP=false` in `.env`
and re-run `docker compose up -d` to lock out strangers.

## 4. Run
```bash
docker compose up -d --build
docker compose logs -f        # watch it boot + scan
docker compose ps             # "healthy" once /api/health responds
```
The app is now at `http://YOUR_DROPLET_IP`. Sign up, create a watch, and use
"Scan now" to verify.

## 5. Updates
```bash
git pull && docker compose up -d --build
```
The SQLite database is stored in the `teetimes-data` Docker volume, so it
survives rebuilds.

## Notes / costs
- Droplet: ~$6/month. Email (Resend free tier): $0 (3000/month).
- The scanner runs every 5 minutes, Tue 06:00 -> Sun 23:59 CT (configurable in
  `backend/app/config.py`). Mondays are off.
- Cloudflare: the scraper uses `curl_cffi` Chrome impersonation, which passes
  the site's passive bot check.

## Cloudflare blocks (403 "Attention Required")

If scans start logging `bootstrap status 403`, the droplet's IP has been banned
by the site's WAF. Confirm with:

```bash
docker compose exec -T app python -c "from curl_cffi import requests as r; print(r.Session(impersonate='chrome').get('https://txaustinweb.myvscloud.com/webtrac/web/search.html?display=detail&module=GR', timeout=(10,30)).status_code)"
```

`403` means a hard IP ban. This is **not** a solvable JS challenge, so
`USE_PLAYWRIGHT_FALLBACK` will not help - a real browser on the same IP is
blocked too. The fix is to change the egress IP:

```bash
# in .env on the droplet
SCRAPER_PROXY=http://username:password@proxy-host:port
```

Use a residential/ISP proxy; datacenter proxies are usually banned in the same
ranges. Then `docker compose up -d` and re-run the check above until it prints
`200`.

A circuit breaker backs off exponentially (5 min up to 60 min) once blocked, so
the app stops hammering the WAF - repeated retries are what entrench a ban. The
current state is visible at `/api/scan-status` under `scraper`, and account
owners get a warning email after `BLOCKED_ALERT_AFTER_MINUTES` (default 120).

## Optional: HTTPS + domain
Point a domain's A record at the droplet, then put Caddy in front (automatic
Let's Encrypt certificates). Change the app's port mapping in
`docker-compose.yml` from `"80:8000"` to `"127.0.0.1:8000:8000"`, install Caddy
on the host, and use this `/etc/caddy/Caddyfile`:

```
teetimes.example.com {
    reverse_proxy localhost:8000
}
```

Then update `.env`: `BASE_URL=https://teetimes.example.com` and
`ALLOWED_ORIGINS=https://teetimes.example.com`, and `docker compose up -d`.
