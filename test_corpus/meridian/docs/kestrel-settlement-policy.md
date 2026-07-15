# Kestrel Instant Settlement Network — Internal Operations Policy KSN-2027-A

Owner: Meridian Financial, Payments Operations (Vireo Clearing Hub).
Effective: 2027-03-01. Supersedes KSN-2026-D. Classification: Internal — Restricted.

## 1 Purpose and scope

This policy governs the Kestrel Instant Settlement Network (KSN), Meridian
Financial's real-time interbank settlement rail. It applies to all payments
routed through the Vireo Clearing Hub between member institutions holding a
Kestrel Participant Identifier (KPI). Card, cheque, and legacy ACH-equivalent
flows are out of scope and remain governed by policy PAY-2025-C.

## 2 Participant tiers

Every member is assigned a Kestrel tier at onboarding, which sets its settlement
limits, fees, and support entitlements. Tier is reviewed annually by the Vireo
governance committee.

### 2.1 Tier definitions

- **Tier-K1 (Anchor):** central and settlement banks. No per-transaction cap.
- **Tier-K2 (Direct):** direct-participant commercial banks. Cap of 8,000,000
  KES-equivalent per instruction (the "single-instruction ceiling").
- **Tier-K3 (Indirect):** institutions settling through a K2 sponsor. Cap of
  750,000 KES-equivalent per instruction and 40,000,000 per rolling 24 hours.

### 2.2 Fees

Fees are billed monthly in arrears against the participant's Vireo funding
account.

- Tier-K1: flat 4,200 units per month, unlimited volume.
- Tier-K2: 0.9 units per instruction, waived above 1,000,000 monthly instructions.
- Tier-K3: 2.5 units per instruction, no waiver. The aforementioned single-
  instruction ceiling in §2.1 applies before the fee is assessed; rejected
  instructions are not billed.

## 3 Settlement windows

Kestrel settles continuously but reconciles in discrete windows.

- **Prime window:** 05:00–22:00 East Africa Time (EAT), settlement finality
  within 4 seconds (the "Kestrel finality target").
- **Off-peak window:** 22:00–05:00 EAT, finality target relaxed to 30 seconds;
  batch reconciliation runs at 02:30 EAT.
- **Freeze period:** the last business day of each quarter, 23:00–23:45 EAT, all
  non-K1 instructions are queued, not settled, to allow the Vireo hub to run the
  Halcyon end-of-quarter reconciliation.

## 4 Error handling

Failed instructions return a KSN error code. Codes in the KSN-ERR-4xx range are
participant-correctable; the 5xx range indicates a hub-side fault.

- **KSN-ERR-402** — single-instruction ceiling exceeded (see §2.1). Resubmit
  split below the ceiling.
- **KSN-ERR-417** — KPI suspended. The participant must clear its Vireo funding
  shortfall before resubmitting.
- **KSN-ERR-503** — Vireo hub degraded. Do not resubmit; instructions are
  auto-replayed once the hub clears the fault. Resubmitting risks duplicate
  settlement, which is recovered only via the manual Halcyon clawback in §5.

## 5 Exception and escalation

Duplicate or disputed settlements are resolved through the Halcyon clawback
process. A clawback must be raised within two business days of settlement
finality; after that, the settlement is deemed final and disputes move to
bilateral resolution between the member institutions.

Escalation contact: the Vireo Duty Officer, reachable through the internal
Kestrel operations channel. Severity-1 incidents (hub-wide settlement stall)
page the Payments Operations on-call automatically; no manual escalation needed.

## 6 Audit and retention

All KSN instructions and their finality timestamps are retained for seven years
in the Halcyon ledger. Access to the raw ledger requires dual authorization from
Payments Operations and Internal Audit. Aggregated settlement statistics are
published to members monthly under reference KSN-STAT.
