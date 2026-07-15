# Meridian Financial — corpus canon (DO NOT INGEST)

Design bible for the fictional test corpus. Every document in `docs/` must stay
consistent with this file. **Never upload this file to the knowledge base**: it
doubles as the negative-control source — some facts below exist ONLY here, so an
agent that answers them has hallucinated or leaked prior knowledge (there is
none: everything is invented).

## The company

**Meridian Financial Group** — fictional Nairobi-based financial-services group
serving institutional, SME, and retail clients across East Africa. Operates the
region's (fictional) real-time interbank settlement rail and a family of
payment products. Currency of reference: KES. Timezone: East Africa Time (EAT).
Regulated by the (fictional) East African Payments Council (EAPC).

Offices: Nairobi (HQ), Mombasa, Kampala, Dar es Salaam. ~1,200 employees.

## Product family (bird-themed, matching existing docs)

| Name | What it is | Audience |
|---|---|---|
| **Kestrel** (KSN) | Instant Settlement Network — real-time interbank settlement rail | Member institutions (Tier-K1/K2/K3) |
| **Vireo Clearing Hub** | The clearing infrastructure Kestrel runs on; hosts participant funding accounts | Internal + members |
| **Halcyon** | Ledger & reconciliation platform: audit trail, end-of-quarter recon, clawbacks | Internal (Payments Ops, Audit) |
| **Aviary** | Web portal for member institutions: KPI management, statements, sandbox access | Member institutions |
| **Tern FX** | Corporate currency desk: spot & forward FX in EAC currencies | Corporate/SME clients |
| **Sunbird** | SME & retail payments wallet (mobile-first) | SMEs, retail |

## Established facts — the ledger (do not contradict)

From `kestrel-settlement-policy.md` (policy KSN-2027-A, effective 2027-03-01,
supersedes KSN-2026-D):

- Participant tiers: **Tier-K1** (Anchor, no cap), **Tier-K2** (Direct, 8,000,000
  KES-eq single-instruction ceiling), **Tier-K3** (Indirect, 750,000 KES-eq per
  instruction, 40,000,000 per rolling 24h).
- Fees: K1 flat 4,200/month; K2 0.9/instruction (waived above 1M monthly
  instructions); K3 2.5/instruction, no waiver. Rejected instructions not billed.
- Windows: prime 05:00–22:00 EAT (4 s finality target); off-peak 22:00–05:00
  (30 s); batch recon 02:30 EAT. Freeze: last business day of quarter,
  23:00–23:45 EAT (non-K1 queued) for Halcyon end-of-quarter reconciliation.
- Error codes: KSN-ERR-4xx participant-correctable, 5xx hub-side.
  402 = ceiling exceeded; 417 = KPI suspended; 503 = hub degraded (never
  resubmit — duplicate risk, manual Halcyon clawback per §5).
- Halcyon clawback: raise within 2 business days of finality.
- Retention: KSN instructions 7 years in Halcyon ledger; raw-ledger access needs
  dual authorization (Payments Ops + Internal Audit). Monthly stats = KSN-STAT.
- KPI = Kestrel Participant Identifier. PAY-2025-C governs card/cheque/legacy flows.

From `meridian-aml-policy.md` (policy AML-2024-B — **client** tiers, a different
axis than Kestrel participant tiers; the collision is deliberate):

- Client tiers: tier-1 institutional, tier-2 SME, tier-3 retail.
- Tier-2 client transfer cap: 10,000 EUR-equivalent/day; exceptions need written
  compliance-desk approval within 2 business days.
- SAR reporting within 24 hours.

From `meridian-hr-handbook.md`:

- Vacation: 2 days/month accrual, 30-day cap.
- Onboarding: security training in week 1; badge by IT day one; payroll
  enrollment closes on the 15th.

New canon available to all documents (introduced by the generated docs; keep
consistent if reused):

- Severity scale: SEV-1 (hub-wide stall, auto-page) … SEV-4 (cosmetic).
- Sanctions screening: "Osprey list" = Meridian's consolidated watchlist,
  refreshed daily 04:00 EAT; screening threshold 1,000,000 KES-eq for
  manual review (code SCR-11).
- Onboarding milestones: sandbox KPI (KPI-S) before production KPI; cutover
  requires 3 consecutive green settlement drills.
- Aviary support: response SLA 4 business hours for K2, next business day for K3.

## Canon-only facts (NEGATIVE CONTROLS — never put in any ingested doc)

An agent asked about these must answer "not in the knowledge base":

- CEO: **Wanjiru Okonkwo** (since 2024).
- Founded **1987** in Mombasa as "Coast Clearing House Ltd"; renamed Meridian 2003.
- Kestrel's internal codename during development was **"Project Windhover"**.
- The Vireo hub runs from twin data centers in **Naivasha and Thika**.

## Style rules for corpus docs

- Every doc carries a fictional policy/reference code (KSN-…, AML-…, HR-…, ONB-…, BCP-…, SCR-…, FAQ-…, GLS-…).
- Dates 2024–2027. Author = a Meridian department, never a person.
- Cross-reference sibling docs by their codes ("see KSN-2027-A §4") — feeds
  `expand_chunk` / multi-doc test scenarios.
- Distinctive invented identifiers in every substantive section (BM25 bait +
  verifiable ground truth).
