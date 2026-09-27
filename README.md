<p align="center">
  <img src="assets/logo.svg" width="140" alt="PMAS logo — hexagon cube">
</p>

<h1 align="center">PMAS</h1>

<p align="center">
  <strong>Pharmacist-led Medication & Adherence Support</strong><br>
  An offline-first, multilingual medication adherence platform with a dual-vault,
  DPDP-aligned architecture built for real-world health economics & outcomes research (HEOR).
</p>

<p align="center">
  <em>Independent project by Kartik H, pharmacist — telepharmacy for rural & remote chronic care. No institutional affiliation.</em>
</p>

<p align="center">
  <a href="https://kartik-h6.github.io/PMAS/">🌐 Live site + patient demo</a> ·
  <a href="https://pmas-bkwu.onrender.com/docs">⚙️ API docs</a> ·
  <a href="https://pmas-bkwu.onrender.com/api/v1/health">🩺 API health</a>
</p>

---

## The problem

Medication non-adherence is one of the largest unsolved problems in chronic disease management. Roughly half of patients with chronic conditions do not take medicines as prescribed, and the problem is worse in India where counselling is brief, instructions are in English, and health literacy varies widely.

A machine translation of "Take Metformin 500 mg twice daily after food" into Telugu changes the **language**. It does not change **comprehension**. Patients forget whether the tablet is before or after food, why the medicine matters, or what to do about a missed dose — and adherence collapses.

## The PMAS answer

PMAS positions a **clinical pharmacist in the loop** and gives the patient a phone-first experience that works **in their own language and their own literacy level**:

| Capability | What it means in practice |
|---|---|
| **Vernacular comprehension** | Pharmacist-written plain-language medication counselling in English, Telugu, Kannada, Tamil and Hindi — clinical simplification, not word-for-word translation |
| **Adherence tracking** | Morning / afternoon / night dose slots with taken / delayed / missed status and automatic adherence percentage |
| **Safety escalation** | Symptom logging with severity rules that escalate to pharmacist contact for red-flag symptoms |
| **Dual-vault architecture** | Vault A (identifiable patient data) is separated by design from Vault B (de-identified clinical/HEOR data) |
| **DPDP Act 2023 alignment** | Granular, purpose-limited consent; audit trail; right to erasure — privacy by architecture, not by policy patch |
| **Offline-first PWA** | The patient app is installable on a phone and works fully without internet; data syncs when connectivity returns |
| **Pharmacist portal** | Patient enrolment, medication plan assignment, and an adherence monitoring dashboard |
| **HEOR-ready exports** | Study-ID-keyed, de-identified exports structured for pharmacoeconomic research |

## Repository structure

```
PMAS/
├── patient-app/          # Patient-facing platform (website + installable PWA demo)
│   ├── index.html        #   Landing page
│   ├── demo/             #   The offline-first PWA application itself
│   │   ├── index.html    #     App shell (5 languages, consent, meds, adherence…)
│   │   └── js/           #     i18n, db, adherence, reminders, export, api sync
│   └── assets/           #   Styles, scripts, logo, OG images
├── backend/              # FastAPI service (auth, medications, adherence, pharmacist, research export)
│   ├── main.py           #   20+ REST endpoints under /api/v1
│   ├── database.py       #   SQLAlchemy models — dual-vault split
│   ├── auth.py           #   JWT + role-based access (patient / pharmacist / admin)
│   ├── schemas.py        #   Pydantic contracts
│   └── migrations/       #   PostgreSQL schema (8 tables)
├── pharmacist-portal/    # Pharmacist dashboard (enrolment, med assignment, monitoring)
├── assets/               # Brand assets (logo)
└── docs/                 # Complete project documentation (see below)
```

## Documentation index

Every aspect of the project is documented in [`docs/`](docs/):

| Document | Covers |
|---|---|
| [00 — Product Requirements](docs/00-product-requirements.md) | PRD v1.0 — problem statement, users, product model, scope, requirements, metrics, risks |
| [ADR-001 — Clinical Scope & Diagnostic Boundary](docs/adr/ADR-001-clinical-scope-and-diagnostic-boundary.md) | Decision record: why PMAS excludes diagnostic/prediction features; the AI boundary |
| [01 — Vision & Problem](docs/01-vision-and-problem.md) | Origin story, adherence problem, thesis argument, target users, competitive landscape |
| [02 — Architecture](docs/02-architecture.md) | System design, dual-vault, offline-first model, API layer, integration principles |
| [03 — Data Model](docs/03-data-model.md) | Database schema, data dictionary, de-identification strategy, health data contract |
| [04 — Security & DPDP Compliance](docs/04-security-and-dpdp-compliance.md) | DPDP Act 2023 obligation mapping, auth, audit, encryption posture |
| [05 — HEOR & Research Design](docs/05-heor-research.md) | Outcomes measures, study design, export schemas, publication pathway |
| [06 — Multilingual Counselling Content](docs/06-multilingual-counselling-content.md) | The vernacular comprehension model and the content database schema |
| [07 — AI Integration Strategy](docs/07-ai-integration-strategy.md) | How PMAS will (and will not) integrate AI/healthcare-intelligence services |
| [08 — Roadmap](docs/08-roadmap.md) | Phase plan from demo → pilot → research → scale, with current status |
| [09 — Deployment](docs/09-deployment.md) | Local development and free-tier cloud deployment (GitHub Pages + Render + Supabase) — live URLs included |
| [10 — Funding & Business](docs/10-funding-and-business.md) | Market analysis, revenue model, grant landscape, cost structure |

## Quick start (local)

**Patient app** — it is a static site; open it and go:

```bash
cd patient-app
python3 -m http.server 5500     # then open http://localhost:5500/demo/
```

**Backend** — Python 3.11+, PostgreSQL (or Supabase connection string):

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env             # fill in DATABASE_URL and JWT_SECRET
python -m uvicorn main:app --reload
# API docs at http://localhost:8000/docs
```

See [docs/09-deployment.md](docs/09-deployment.md) for the full cloud deployment guide.

## Important disclaimers

- **PMAS is a research prototype**, not a medical device or a diagnostic system. It supports medication adherence and pharmacist counselling; it does not diagnose disease.
- All patient-facing informational content is for education and counselling support, and must be reviewed by a registered pharmacist before use with real patients.
- The study described in [docs/05](docs/05-heor-research.md) requires Institutional Ethics Committee approval before any human-participant data collection.

## Author

**Kartik H** — B.Pharm, pharmacist and independent researcher. All platform
conception, clinical reasoning, and validation decisions are the author's.

## AI usage disclosure

Parts of this codebase and documentation were developed with AI assistance (prompted, reviewed and validated by the author). Details: [docs/11-ai-usage-disclosure.md](docs/11-ai-usage-disclosure.md). This disclosure is maintained as a matter of research transparency.

## License

© 2026 Kartik H — all rights reserved. Source is visible for academic review and collaboration; commercial use requires written permission from the author. An open-source license may be adopted later (see [LICENSE](LICENSE)).
