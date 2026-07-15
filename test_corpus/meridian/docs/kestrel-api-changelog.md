# Kestrel API Changelog — CHG-KSN

Owner: Meridian Financial, Platform Engineering. Audience: member-institution
integrators. Latest entries first. Semantic scheme: vYEAR.RELEASE.

## v2027.2 — 2027-06-10

- **New:** `GET /v2/instructions/{id}/finality` returns the Halcyon finality
  timestamp directly; previously required a KSN-STAT export.
- **New error code:** KSN-ERR-429 — participant rate limit exceeded (default
  120 instructions/second for Tier-K2, 20/s for Tier-K3). Retry with backoff;
  429s do not suspend the KPI.
- **Changed:** sandbox KPIs (KPI-S) now expire after 90 days of inactivity
  instead of 180. Re-issue through Aviary.
- **Deprecated:** `POST /v1/instructions` — sunset scheduled v2028.1. Migrate
  to `/v2/instructions`, which requires the `settlement_window` hint field.

## v2027.1 — 2027-02-01

- **New:** webhook `settlement.finality` fires within 1 s of Halcyon ledger
  write; replaces polling for K2 integrators.
- **Changed:** `KSN-ERR-503` responses now carry a `retry_after_hint` field.
  The rule in KSN-2027-A §4 still applies: never resubmit manually on a 503.
- **Fixed:** duplicate `KSN-ERR-402` on split resubmissions when the second
  fragment arrived inside the same reconciliation tick.

## v2026.3 — 2026-10-05

- **New:** Aviary sandbox self-service — request a KPI-S without a support
  ticket. Requires an onboarding milestone M2 sign-off (see ONB-2026-K §3).
- **Changed:** off-peak batch reconciliation moved from 02:00 to 02:30 EAT to
  align with the Halcyon maintenance window.
- **Security:** all API tokens rotated to the `mfk_` prefix format; legacy
  `kestrel_` tokens rejected after 2026-12-31.

## v2026.2 — 2026-06-14

- **New:** bulk instruction endpoint `POST /v1/instructions:batch` (max 500 per
  call, K1/K2 only).
- **Fixed:** finality timestamps off by one reconciliation tick for
  instructions settled in the last 4 s of the prime window.
