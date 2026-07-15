"""Generate meridian-product-catalog.pdf — the "product manual" archetype."""

from _common import build_pdf, bullets, contents, h1, h2, p, revision_history, spacer, table

e = [
    h1("Meridian Financial Product Catalog"),
    p("Reference PRD-2027-A. Owner: Product Management. Effective 2027-01-15. "
      "This catalog describes Meridian Financial Group's client-facing and member-facing "
      "products, their commercial terms, and their operational boundaries. Internal platform "
      "components (Vireo Clearing Hub, Halcyon) are included for completeness but are not "
      "sold separately."),
    *contents([
        "1 Product family overview",
        "2 Kestrel Instant Settlement Network",
        "3 Aviary member portal",
        "4 Tern FX currency desk",
        "5 Sunbird payments wallet",
        "6 Internal platforms",
        "7 Instruction lifecycle",
        "8 Regional availability",
        "9 Worked fee examples",
        "10 Product change control",
        "Appendix A - Document map",
        "Revision history",
    ]),

    h1("1 Product family overview"),
    p("Meridian operates six named products. Client-facing products are sold by Commercial; "
      "member-facing products are contracted through Network Participation under the "
      "onboarding process ONB-2026-K."),
    table([
        ["Product", "Code", "Audience", "Commercial owner"],
        ["Kestrel Instant Settlement Network (KSN)", "PRD-KSN", "Member institutions", "Network Participation"],
        ["Aviary member portal", "PRD-AVY", "Member institutions", "Network Participation"],
        ["Tern FX currency desk", "PRD-TFX", "Corporate and SME clients", "Commercial"],
        ["Sunbird payments wallet", "PRD-SNB", "SME and retail clients", "Commercial"],
        ["Vireo Clearing Hub", "PRD-VCH", "Internal platform", "Payments Operations"],
        ["Halcyon ledger and reconciliation", "PRD-HAL", "Internal platform", "Payments Operations"],
    ]),
    spacer(),

    h1("2 Kestrel Instant Settlement Network"),
    p("Kestrel is the group's real-time interbank settlement rail, governed by policy "
      "KSN-2027-A. Member institutions settle under a Kestrel Participant Identifier (KPI) "
      "in one of three participation tiers. Card, cheque, and legacy ACH-equivalent flows "
      "are out of Kestrel scope and remain under PAY-2025-C."),
    h2("2.1 Participation tiers and limits"),
    table([
        ["Tier", "Name", "Single-instruction ceiling", "Rolling 24h limit"],
        ["Tier-K1", "Anchor", "No cap", "No cap"],
        ["Tier-K2", "Direct", "8,000,000 KES-eq", "Not applied"],
        ["Tier-K3", "Indirect (via K2 sponsor)", "750,000 KES-eq", "40,000,000 KES-eq"],
    ]),
    spacer(),
    h2("2.2 Settlement fees"),
    p("Fees are billed monthly in arrears against the participant's Vireo funding account. "
      "Rejected instructions are not billed."),
    table([
        ["Tier", "Fee model", "Waiver"],
        ["Tier-K1", "Flat 4,200 units per month, unlimited volume", "Not applicable"],
        ["Tier-K2", "0.9 units per instruction", "Waived above 1,000,000 monthly instructions"],
        ["Tier-K3", "2.5 units per instruction", "No waiver"],
    ]),
    spacer(),
    h2("2.3 Service levels"),
    p("Settlement finality targets: 4 seconds in the prime window (05:00-22:00 EAT) and "
      "30 seconds off-peak. The quarterly freeze (last business day of quarter, 23:00-23:45 "
      "EAT) queues all non-K1 instructions during the Halcyon end-of-quarter reconciliation. "
      "Detailed error-handling rules, including the KSN-ERR code ranges, are in KSN-2027-A "
      "section 4 and the Kestrel API changelog CHG-KSN."),

    h1("3 Aviary member portal"),
    p("Aviary is the web portal through which member institutions manage their Kestrel "
      "participation: KPI lifecycle management, settlement statements, sandbox (KPI-S) "
      "self-service, and support tickets."),
    h2("3.1 Support entitlements"),
    table([
        ["Participant tier", "Support response SLA", "Channel"],
        ["Tier-K1", "Dedicated channel, no ticket queue", "Named contact"],
        ["Tier-K2", "4 business hours", "Aviary ticket"],
        ["Tier-K3", "Next business day", "Aviary ticket"],
    ]),
    spacer(),
    h2("3.2 Sandbox access"),
    p("Since release v2026.3 of the Kestrel API, integrators self-request a sandbox KPI "
      "(KPI-S) through Aviary once onboarding milestone M2 is signed off. A KPI-S expires "
      "after 90 days of inactivity (changed from 180 days in v2027.2) and is re-issued "
      "through Aviary without a support ticket."),

    h1("4 Tern FX currency desk"),
    p("Tern FX provides spot and forward foreign exchange in East African Community "
      "currencies to corporate and SME clients."),
    h2("4.1 Dealing terms"),
    bullets([
        "Same-day value cutoff: 15:30 EAT for EAC currency pairs; later trades book for "
        "next business day.",
        "Forward tenors: up to 12 months, subject to credit approval by the Tern desk.",
        "Minimum ticket: 250,000 KES-eq spot; 1,000,000 KES-eq forwards.",
        "Standard spread schedule: reference TFX-SPREAD-2027, published monthly on Aviary.",
    ]),
    h2("4.2 Compliance boundaries"),
    p("Tern FX client relationships follow the AML client-tier framework in AML-2024-B. "
      "Note that AML client tiers (tier-1 institutional, tier-2 SME, tier-3 retail) are a "
      "different axis from Kestrel participation tiers: a tier-2 SME client of Tern FX has "
      "no Kestrel tier at all unless their bank is separately a Kestrel member."),

    h1("5 Sunbird payments wallet"),
    p("Sunbird is Meridian's mobile-first payments wallet for SMEs and retail users."),
    h2("5.1 Wallet limits"),
    table([
        ["Account state", "Daily transaction cap", "Single transaction cap"],
        ["Verified", "500,000 KES", "150,000 KES"],
        ["Unverified", "50,000 KES", "10,000 KES"],
    ]),
    spacer(),
    h2("5.2 Merchant terms"),
    p("Merchant acceptance fee: 0.65% per transaction, settled to the merchant's Sunbird "
      "float account on T+1. Merchants above 2,000,000 KES monthly volume qualify for the "
      "negotiated schedule SNB-M2 and next-day dedicated support."),

    h1("6 Internal platforms"),
    p("Two platform components appear throughout member and client documentation but are "
      "not commercial products: they cannot be bought, and their service levels are "
      "expressed only through the products that run on them."),
    h2("6.1 Vireo Clearing Hub"),
    p("Vireo hosts participant funding accounts and executes Kestrel settlement windows. "
      "Participant-visible behavior (window times, error semantics) is documented in "
      "KSN-2027-A; continuity arrangements are in BCP-2026-M."),
    h2("6.2 Halcyon"),
    p("Halcyon is the ledger of record: audit trail, end-of-quarter reconciliation, and "
      "clawback processing. Instructions and finality timestamps are retained for seven "
      "years. Raw ledger access requires dual authorization from Payments Operations and "
      "Internal Audit; aggregated statistics publish monthly as KSN-STAT."),

    h1("7 Instruction lifecycle"),
    p("Every Kestrel instruction passes through five stages, in order: submission "
      "(schema validation, rate-limit check against the v2027.2 limits), sanctions "
      "screening (SCR-2026-A rules, before the settlement queue), queueing in the Vireo "
      "hub, settlement inside the active window, and finality (durable Halcyon write, "
      "then the participant-visible finality timestamp). The stage a failure occurs in "
      "determines the error family: schema and limit failures return 4xx codes at "
      "submission; compliance holds return KSN-ERR-451 at screening; hub faults return "
      "5xx codes from queueing onward."),
    p("Integrators frequently misattribute screening holds to hub faults. The "
      "distinguishing signal is the code family: a KSN-ERR-451 hold never auto-replays, "
      "while a KSN-ERR-503 always does. Support staff triage against this table before "
      "opening an incident."),

    h1("8 Regional availability"),
    p("Availability is governed by licensing per EAC member state. \"Full\" means the "
      "product is sold and supported; \"partner\" means delivery through a licensed local "
      "partner institution; a dash means not available."),
    table([
        ["Product", "Kenya", "Uganda", "Tanzania", "Rwanda"],
        ["Kestrel participation", "Full", "Full", "Full", "Partner"],
        ["Aviary", "Full", "Full", "Full", "Partner"],
        ["Tern FX", "Full", "Full", "Partner", "Partner"],
        ["Sunbird", "Full", "Partner", "-", "-"],
    ]),
    spacer(),
    p("Sunbird's Tanzania and Rwanda launches are gated on wallet-interoperability "
      "rulings by the EAPC; the product council reviews the gating decision quarterly."),

    h1("9 Worked fee examples"),
    h2("9.1 Tier-K2 monthly invoice"),
    p("A Tier-K2 member submitting 1,400,000 instructions in a month pays for the first "
      "1,000,000 at 0.9 units each (900,000 units) and nothing for the remaining 400,000 "
      "— the waiver in section 2.2 applies above the millionth instruction. Rejected "
      "instructions, including KSN-ERR-402 splits that were re-submitted successfully, "
      "are excluded from the count."),
    h2("9.2 Tier-K3 monthly invoice"),
    p("A Tier-K3 member submitting 30,000 instructions pays 75,000 units (30,000 x 2.5); "
      "no waiver tier exists for K3. Instructions rejected at the 750,000 KES-eq ceiling "
      "are not billed, but their split re-submissions are, as separate instructions."),
    h2("9.3 Sunbird merchant settlement"),
    p("A merchant processing 3,000,000 KES in a month pays 19,500 KES in acceptance fees "
      "(0.65%) and, having crossed the 2,000,000 KES threshold, qualifies for the "
      "negotiated SNB-M2 schedule the following quarter."),

    h1("10 Product change control"),
    p("Commercial terms in this catalog change only through the quarterly product council. "
      "Between councils, corrections are published as PRD-2027-A errata on Aviary. API-level "
      "changes follow the Kestrel API changelog CHG-KSN and its deprecation windows: "
      "deprecated endpoints receive at least one full release cycle of notice, as with the "
      "v1 instruction endpoint scheduled for sunset in v2028.1."),

    h1("Appendix A - Document map"),
    p("Where to look next, by topic. This catalog is the commercial entry point; the "
      "documents below are authoritative for their domains."),
    table([
        ["Topic", "Authoritative document"],
        ["Settlement rules, tiers, windows, error semantics", "KSN-2027-A"],
        ["Member onboarding, sandbox, drills, cutover", "ONB-2026-K"],
        ["API releases and deprecations", "CHG-KSN"],
        ["Sanctions screening rules and holds", "SCR-2026-A"],
        ["AML client tiers and transfer caps", "AML-2024-B"],
        ["Continuity, severities, recovery objectives", "BCP-2026-M"],
        ["Card, cheque, legacy ACH-equivalent flows", "PAY-2025-C"],
    ]),

    *revision_history([
        ["1.0", "2026-01-20", "First consolidated catalog (superseded PRD-2026 sheets)"],
        ["1.1", "2026-07-02", "Sunbird merchant schedule SNB-M2 added"],
        ["2.0", "2027-01-15", "Current edition: Tern FX forwards, regional availability, "
         "v2027-era Kestrel limits"],
    ]),
]

if __name__ == "__main__":
    print(build_pdf("meridian-product-catalog.pdf", "PRD-2027-A", e))
