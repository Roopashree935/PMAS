# 04 — Security & DPDP Act 2023 Compliance

## Framing

PMAS processes digital personal data of patients in India; as a research prototype it is being built to the standard the **Digital Personal Data Protection Act, 2023** (and the DPDP Rules, 2025, being phased in) will require of a production health platform. Treating compliance as architecture — rather than as a policy document bolted on later — is both a research contribution and an incubation differentiator.

This document maps each core DPDP obligation to what PMAS implements today and what is planned.

## DPDP obligation mapping

| DPDP obligation | What the Act expects | PMAS implementation | Status |
|---|---|---|---|
| **Notice & consent** (§5, §6) | Clear, plain-language notice; free, specific, informed, unconditional consent, limited to specified purposes | Consent screen in the patient's own language with six granular acknowledgement checkboxes; `consent_checks` JSONB records each flag separately; `consent_timestamp` + `consent_version` stored; consent is attested from the patient's device on first sync (PRD v1.1 §4A) | ✅ Implemented |
| **Purpose limitation** (§4(2)) | Processing limited to consented purposes | Dual-vault architecture (see [doc 03](03-data-model.md)); the patient self-export is scoped to the patient's own data. The researcher-facing study export (gated on the research-consent flag) is a portal-phase capability | 🔶 Patient self-export shipped; researcher export pending |
| **Consent withdrawal & erasure** (§6(4), §12) | Withdrawal as easy as giving; erasure unless retention is legally required | Device-side erasure ("Delete All My Data") clears all local data incl. the cloud-sync token; account-level deletion/withdrawal is handled on request via the contact page | 🔶 Device erasure shipped; account deletion on request |
| **Data minimisation** (§4) | Only data necessary for the stated purpose | Every field in the schema maps to a clinical or consent purpose; no trackers, no analytics SDKs, no third-party pixels | ✅ Implemented |
| **Security safeguards** (§8(5)) | Reasonable technical & organisational measures | Parameterised queries via SQLAlchemy (no string SQL); JWT with expiry; role-based access control; CORS allow-list; secrets via environment variables (`.env.example` documents; nothing hard-coded) | ✅ Implemented |
| **Breach notification** (§8(6)) | Intimation to the Data Protection Board and affected data principals | `security_audit_trail` records privileged actions; the 72-hour notification SOP is documented below | 🔶 SOP documented; automated alerting is Phase 2 |
| **Grievance redressal** | Data principal can raise grievances | Pharmacist + investigator contact channels; formal in-app mechanism is Phase 2 | 🔶 Partial |
| **Audit trail** | Accountability of processing | Append-only `security_audit_trail` (who, action, resource, IP, timestamp) written on registration, login, password change, profile/consent attestation, medication changes, enrollment, dashboard views, research exports and admin actions | ✅ Implemented for all privileged routes; per-record clinical reads land with the portal |
| **Children's data** (§9) | Verifiable parental consent for under-18s | Study population is adults (18+); enrolment captures DOB; a hard age check is planned for Phase 2 | 🔶 Partial |
| **Significant Data Fiduciary duties** (§10) | DPO, DPIA, audits if designated | Not applicable at pilot scale; DPIA template drafted in this doc's appendix | ℹ️ N/A yet |

Status key: ✅ shipped in code · 🔶 designed, partially shipped · ℹ️ not yet applicable.

## Authentication & authorisation

- **Identity:** phone number + password (phone-first for India). Passwords stored only as salted hashes (`backend/auth.py`).
- **Session:** short-lived JWTs; expiry configured via `JWT_EXPIRY_HOURS`.
- **Authorisation:** three roles (`patient`, `pharmacist`, `admin`) enforced per endpoint. Ownership checks ensure a patient can read only their own record — authorisation is never "is logged in" but "who, what resource, whose resource".
- **Pharmacist enrolment:** patients are linked to a pharmacist through a controlled enrolment endpoint rather than open self-signup into a care relationship.

## Secrets & configuration policy

- All secrets (`DATABASE_URL`, `JWT_SECRET`, `CORS_ORIGINS`) come from environment variables; `backend/.env.example` is the template and `.gitignore` excludes `.env`.
- **Rule for all contributors:** no credential ever appears in source, in a commit, or in an issue. If a secret leaks, it is rotated immediately — deleting the commit is not sufficient.
- (Contrast case that motivated this rule: the Healthcare-AI reference repository shipped live Oracle credentials and a static `SECRET_KEY` in `config.py`. Those were rotated and moved to environment variables before any integration work — see [doc 07](07-ai-integration-strategy.md).)

## Encryption posture

| Layer | Today | Notes |
|---|---|---|
| In transit | TLS everywhere (managed platforms terminate HTTPS) | Non-negotiable |
| At rest | Inherited from managed Postgres (Supabase/Render) | Adequate for pilot |
| Application-level field encryption | Planned (Phase 2) | `known_allergies`, `chronic_conditions` and emergency-contact fields are candidates for application-layer envelope encryption, so a database dump alone never reveals clinical PII |

## Breach response SOP (72-hour rule)

1. **Detect** — audit-trail anomalies or platform alerts; the investigator is on the notification chain for the managed-DB provider.
2. **Contain** — rotate `JWT_SECRET` and DB credentials; revoke active sessions; if needed, take the backend offline (the patient app continues offline by design).
3. **Assess scope** — query the audit trail for affected records.
4. **Notify** — Data Protection Board of India and every affected data principal within 72 hours of identification, per DPDP Rules.
5. **Record** — full post-incident note appended to the audit trail and the study's regulatory file.

## Threat model (abbreviated, pilot scope)

| Threat | Vector | Mitigation |
|---|---|---|
| Credential stuffing | Login endpoint | Rate limiting (planned), bcrypt-style hashing, long minimum password |
| Cross-patient data access | IDOR on patient endpoints | Ownership checks in every handler; tests planned for the 403 path |
| Research re-identification | Exports | Study-ID-only keys, minimum cell sizes for aggregate reporting (Phase 2: k-anonymity check before export) |
| Device loss | Phone with offline data | No clinical PII beyond what the patient entered themselves; local data clearable in-app |
| Supply chain | Dependencies | Minimal dependency set; pinned versions in `requirements.txt` |

## What reviewers should verify

For an ethics committee or hospital IT review, the checklist is:

1. Can a patient see and change each consent purpose separately? — Yes (consent screen + `consent_checks`).
2. Can research data be produced without any identifier? — Yes (export contract, [doc 03](03-data-model.md)).
3. Is every privileged read logged? — Yes (`security_audit_trail`).
4. What happens to data on consent withdrawal? — Vault A cascade + local clear.
5. Where do secrets live? — Environment variables only.

*This document is engineering documentation, not legal advice. Formal DPDP certification and counsel review are planned before any production deployment beyond the ethics-approved study.*
