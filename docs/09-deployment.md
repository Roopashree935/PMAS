# 09 — Deployment

Everything runs on free tiers at pilot scale. Two paths: local development, and the free-tier cloud stack (GitHub Pages + Render + Supabase).

## Local development

**Patient app** (static — any static file server works):

```bash
cd patient-app
python3 -m http.server 5500
# Patient app:    http://localhost:5500/demo/
# Platform site:  http://localhost:5500/
```

> Do not open `demo/index.html` via `file://` — service workers and localStorage behave differently; always use a local server.

**Backend** (Python 3.11+; PostgreSQL 14+ running locally or a Supabase connection string):

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then edit values
python -m uvicorn main:app --reload
# Swagger docs: http://localhost:8000/docs
```

Environment variables (from `.env.example`):

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string (local or Supabase) |
| `JWT_SECRET` | Long random string — generate with `openssl rand -hex 32` |
| `JWT_EXPIRY_HOURS` | Token lifetime (24 default) |
| `CORS_ORIGINS` | Comma-separated allowed origins (add your GitHub Pages URL) |
| `HOST` / `PORT` | Bind address |

**Database migration:**

```bash
psql "$DATABASE_URL" -f backend/migrations/001_initial_schema.sql
```

## Cloud deployment (free tier)

### Live deployment (verified 27 Sep 2026)

| Component | URL | Host |
|---|---|---|
| Platform + patient app | https://kartik-h6.github.io/PMAS/ | GitHub Pages (`.github/workflows/static.yml`) |
| Backend API | https://pmas-bkwu.onrender.com | Render (Docker runtime, free tier) |
| API docs (Swagger) | https://pmas-bkwu.onrender.com/docs | — |
| Health check | https://pmas-bkwu.onrender.com/api/v1/health | — |
| Database | Supabase PostgreSQL — Mumbai (ap-south-1) | Free tier |

First live end-to-end pass (27 Sep 2026, from a mobile device on the deployed patient app): account registration → medication plan created → dose logged → cloud sync confirmed.

Environment variables set on Render (values are secrets — never commit them): `DATABASE_URL` (Supabase session-pooler URI, scheme `postgresql+asyncpg://`), `JWT_SECRET`, `ADMIN_PHONE`, `ADMIN_PASSWORD`, `CORS_ORIGINS` (the GitHub Pages origin).

### 1. Database — Supabase

1. Create a free project at supabase.com (region: Mumbai/ap-south-1 if offered).
2. Copy the **Session pooler** connection string (Connect → Session pooler, port 5432) — the direct-connection hostname is IPv6-first and can fail on some hosts; the pooler always works. Set the URL scheme to `postgresql+asyncpg://`. If the database password contains `@` or other URI special characters, percent-encode it (`@` → `%40`) or the string will not parse.
3. No manual SQL is required: the backend creates all tables on startup (`create_all`). `backend/migrations/001_initial_schema.sql` remains the reference schema.

### 2. Backend — Render

1. Push this repository to GitHub.
2. On render.com: **New → Web Service** → connect the repo.
3. Settings (as deployed):
   - Root directory: `backend`
   - Runtime: **Docker** (auto-detected from `backend/Dockerfile`; the image binds to Render's `PORT`)
   - Instance type: **Free**
   - Environment variables: `DATABASE_URL`, `JWT_SECRET`, `ADMIN_PHONE`, `ADMIN_PASSWORD`, `CORS_ORIGINS`
4. Deploy. Note the URL, e.g. `https://pmas-api.onrender.com`.

> **Free-tier behaviour:** the service sleeps after ~15 minutes of inactivity; the first request after sleep takes ~30 s. Harmless for a pilot (the patient app is offline-first) — if unacceptable later, the lowest paid tier (~$7/month) keeps it always on.

### 3. Patient app + platform site — GitHub Pages

1. In the repository: **Settings → Pages → Source: GitHub Actions**.
2. The workflow `.github/workflows/static.yml` deploys `patient-app/` on every push to `main`.
3. The site is at `https://<user>.github.io/PMAS/`; the patient demo at `/PMAS/demo/`.

### 4. Wiring it together

1. No code wiring needed: in the patient app's **Account & Cloud Sync** card, the patient enters the backend address (e.g. `https://pmas-bkwu.onrender.com`) — the sync layer stores it on the device.
2. Set `CORS_ORIGINS` on Render to the GitHub Pages origin; redeploy the backend after any change.
3. Pharmacist-side flows (enrollment, dashboard, de-identified export) are exercised once the pharmacist portal exists (issues #19–#22).

### 5. DNS (optional)

If using a custom domain through Cloudflare: CNAME the domain to the GitHub Pages site (`<user>.github.io`); keep HTTPS enforced. No special config needed for the API at pilot scale.

## Deployment checklist (before any demo)

- [x] Patient app loads on an Android phone over HTTPS. *(verified 27 Sep 2026)*
- [ ] Installable (browser shows "Add to Home Screen"; logo correct after install).
- [ ] Airplane-mode test: app opens offline with data intact.
- [x] Login works against the deployed backend. *(verified 27 Sep 2026 — registration, sign-in, medication + dose sync)*
- [ ] Dose logging appears on the pharmacist dashboard.
- [ ] Language switch works in all 5 languages.
- [ ] Research export returns de-identified JSON (spot-check for absence of names/phones).

## Cost summary

| Item | Cost |
|---|---|
| GitHub Pages (static hosting) | ₹0 |
| Render free web service | ₹0 |
| Supabase free tier (500 MB, 50 connections) | ₹0 |
| Cloudflare DNS | ₹0 |
| Domain (optional, e.g. `pmas.in`) | ~₹800–1,200/year |
| Google Play developer (only if/when wrapping as an Android app) | ₹2,100 one-time |

Operating cost at pilot scale: **₹0/month** (excluding an optional domain).

A legacy deployment guide from the earlier full-stack iteration is retained at [DEPLOYMENT_GUIDE_LEGACY.md](DEPLOYMENT_GUIDE_LEGACY.md) for reference.
