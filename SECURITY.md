# Security Policy

## Supported version

The `main` branch is the only supported version.

## Reporting a vulnerability

Please report suspected vulnerabilities privately to
**kartik.h6822@gmail.com** — do not open a public issue for them. Include
reproduction steps if you can. You will get an acknowledgement within a
few days.

Please avoid submitting automated scanner output without verification —
a finding you have confirmed yourself is worth ten unconfirmed ones.

## Known posture

- Authentication is phone + bcrypt password with JWT (HS256) sessions;
  enrollment uses one-time activation codes, never shared passwords.
- Research data export is gated on the patient's attested consent.
- Admin access to clinical data requires a written break-glass reason,
  recorded in the audit trail with the caller's IP.
- The application refuses to start without an explicit `JWT_SECRET`
  and `CORS_ORIGINS` allow-list, and rejects the public development
  default secret outright.
