# Changelog

All notable changes to PMAS are documented here. The project uses a single product name — **PMAS** — with no version suffixes in user-facing branding; internal versions are tracked here for development history.

## [Unreleased]

### Deployed — governance implementation round (29 Sep 2026, G8/G9/G5)
- **G8 — patient-controlled credentials.** Enrollment no longer generates or returns a password. The pharmacist receives a one-time 6-digit activation code (valid 7 days); the patient activates the account on their own device ("Activate with code" in the patient app, translated in all 5 languages) and chooses their own password. The pharmacist never enters, receives, or sees the patient's password. Activation is throttled like login (5 failures → 15-minute lockout) and audit-logged (ACCOUNT_ACTIVATED). Unactivated accounts cannot log in (clear "not yet activated" message).
- **G9 — admin is governance, not clinical.** Enrollment and the pharmacist dashboard are now pharmacist-only. Admin reaches clinical data exclusively through the new break-glass route (`POST /api/v1/admin/break-glass`), which requires a written reason (min 10 chars), returns a single patient's summary, and persists the reason in the new `break_glass_access` table plus the audit trail with IP. No routine admin clinical access remains.
- **G5 — research export is consent-gated.** `/api/v1/research/export` now requires the patient's attested research consent (`consent_status=True` plus the full acknowledgement set from the §4A attestation). Authentication is not authorization; audit logging is not authorization.
- Schema notes: new tables `pending_activations` and `break_glass_access` are auto-created on deploy (no manual SQL needed). **Staged for after migrations/003 runs on the live database: G10 (consent-timestamp nullability).**


### Deployed — audit remediation round 2 (28 Sep 2026)
- **Per-pharmacist dashboard scoping** (`patient_profiles.enrolled_by`): every dashboard statistic and the recent-patients list are now limited to patients the calling pharmacist personally enrolled. Admins see only patients they enrolled themselves (admin is governance, not clinical superuser). Self-registered patients remain invisible to pharmacists until enrolled. Prerequisite migration `002_enrolled_by.sql` was run on the live database before this deploy.
- Patients enrolled before this change have no `enrolled_by` owner recorded and will not appear in any pharmacist's worklist until re-enrolled.


### Fixed — audit remediation round 1 (28 Sep 2026)
- **Patient adherence now actually syncs.** Offline-first records previously carried local medication IDs that the server rejected (silent 422s behind a success toast — the server never received any dose). Medications are now created/mapped server-side on first sync, and adherence records sync with change detection. Sync failures are now surfaced to the patient instead of being swallowed.
- **Enrolled patients can now log in.** Enrollment returns a one-time temporary password to the pharmacist (portal displays + copies it); patients change it at first login via the new change-password endpoint and patient-app control (5 languages). Previously the generated password was discarded and the account was unreachable.
- **Symptom duplicates eliminated.** Each symptom entry syncs exactly once (synced-state tracking); previously every reconnect re-uploaded the entire log.
- **Cross-patient adherence injection blocked** (medication ownership is validated server-side).
- **Weekly adherence no longer crashes on days 1–6 of a month** (date arithmetic bug).
- **Login throttling**: accounts lock for 15 minutes after 5 failed attempts.
- **XSS hardened**: patient names in the pharmacist portal and emergency-contact fields in the Health Summary are escaped before rendering.
- **Enrollment consent model (§4A)**: enrollment no longer auto-marks consent; the patient consents on-device and the app attests the record (checks, timestamp, version) on first sync.
- **Configuration guard**: the backend refuses to start without `JWT_SECRET`, without an explicit CORS allow-list, or with a wildcard origin. `python-dotenv` is now loaded so local `.env` files work.
- **Audit trail extended**: dashboard views, research exports, password changes and profile/consent attestations are now logged, with client IP captured on privileged events.
- **Validation tightened**: patient passwords ≥ 8 chars; medication end-date ≥ start-date; at least one dose slot required; time format checks; no far-future dose dates; API profile payloads no longer require explicit nulls (Pydantic v2 `Optional` default fix).
- **Health endpoint** now reports `privacy_posture: "dpdp_aligned_design"` instead of an unverifiable `dpdp_compliant: true`.
- Housekeeping: unused `psycopg2-binary` dependency and dead `require_role` helper removed; deprecated `datetime.utcnow`/`on_event` replaced; appointments sort ascending; service worker caches bumped to v5; homepage "never transmitted" claim corrected; `pmas_portal_api_url` isolates portal storage from the patient app.
- Staged (needs a one-time SQL migration on the live database before deploy): per-pharmacist dashboard scoping via `patient_profiles.enrolled_by` — see `backend/migrations/002_enrolled_by.sql`.


### Deployed
- **PMAS is live end-to-end (27 Sep 2026)** — platform + patient app on GitHub Pages, backend API on Render, PostgreSQL on Supabase (Mumbai), all free tier. Live URLs in `docs/09-deployment.md`.
- First live patient-loop verification from a mobile device on the deployed app: account registration → medication plan → dose logged → sign-in and symptom sync confirmed. (The 28 Sep audit later found adherence records were silently failing to sync — fixed in the remediation round above.)
- Deploy fixes: backend Docker image binds to Render's `PORT`; `requirements.txt` lists PyJWT (was: unused python-jose, which broke the clean-environment build).
- Known limitation: the free-tier API sleeps after ~15 min idle — the first request takes ~30–60 s (the patient app remains fully usable offline).

### Security
- **Privacy disclosure updated for optional cloud sync (DPDP-aligned)** — privacy page now accurately states offline-by-default with opt-in sync, names the hosting services involved (GitHub Pages, Render, Supabase Mumbai region), adds an adults-only (18+) account confirmation in all 5 languages, and a grievance channel via the contact page. Homepage/about/README claims updated to match.
- **Self-registration is now patient-only.** The register endpoint no longer accepts a client-supplied role, closing a privilege-escalation path (previously anyone could POST `role: "pharmacist"` or `"admin"`).
- New admin account-governance API — list users, create staff accounts, change roles, suspend/reactivate — administrator-only and audit-logged. Admins cannot change their own role or status.
- First-run administrator bootstrap via `ADMIN_PHONE` / `ADMIN_PASSWORD` environment variables.
- Pharmacist portal: staff self-registration removed; patient accounts are created in the patient app.

### Changed
- Project reframed as an **independent telepharmacy research project by Kartik H** — institutional affiliations, dissertation framing and third-party references removed across docs, marketing pages, consent screens and app strings (all 5 languages).
- Product model formalised in the PRD: the 90-day telepharmacy care loop for rural and remote chronic-care patients.

### Added
- Product Requirements Document: `docs/00-product-requirements.md` (problem statement, personas, scope, functional & non-functional requirements, success metrics, risks).
- Architecture Decision Record: `docs/adr/ADR-001` — clinical scope and diagnostic boundary (why PMAS excludes diagnostic/prediction features; the AI boundary).
- This repository: consolidated project structure (`patient-app/`, `backend/`, `pharmacist-portal/`, `docs/`).
- Complete documentation set: vision, architecture, data model, security/DPDP mapping, HEOR research design, multilingual content model, AI integration strategy, roadmap, deployment, funding & business, AI-usage disclosure.
- API sync layer (`demo/js/api.js`) added to the patient app source (wiring into the app shell is next — see roadmap).

## History (pre-repository)

### Platform v3 — PWA + AI-era layer
- Installable PWA demo with offline service worker and install prompt.
- AI-crawler/AI-era web layer: `llms.txt`, JSON-LD, canonical URLs, Open Graph / Twitter cards, robots directives.
- Platform website: landing, about, contact, privacy, terms, 404.

### Full-stack iteration
- FastAPI backend: 20+ endpoints (`/api/v1`), JWT auth with RBAC (patient / pharmacist / admin).
- Dual-vault PostgreSQL schema: 8 tables across Vault A (identity/PII) and Vault B (clinical/HEOR).
- Pharmacist portal: enrolment, medication plan assignment, adherence dashboard.
- Research export endpoint producing de-identified, Study-ID-keyed JSON.
- Deployment guide for Netlify + Render + Supabase (free tiers).

### v1.1 feature review (all 10 items implemented)
- Adherence tracking (taken / delayed / missed, per-slot).
- Granular, per-purpose consent capture.
- Study ID + de-identified export path.
- Safety escalation redesign for symptom red flags.
- Complete 5-language translations (English, Telugu, Kannada, Tamil, Hindi).
- Local medication reminders (in-app + browser notifications).
- Patient PDF report.
- Fixed next-due logic and appointment sorting.
- Removed `user-scalable=no` (accessibility fix).

### v1.0 — original prototype
- Single-file offline-first demo (early prototype): consent, profile, medications, dose logging, symptom logging, multilingual UI.
- One-page research concept note (study design, outcomes, population, ethics pathway).

### Branding
- Hexagon-cube logo adopted as the brand icon across the platform; all "Lite" and version suffixes removed from naming — the product is **PMAS**, full stop.
