"""Generate kestrel-participant-onboarding-guide.pdf — the "onboarding guide" archetype."""

from _common import build_pdf, bullets, contents, h1, h2, p, revision_history, spacer, table

e = [
    h1("Kestrel Participant Onboarding Guide"),
    p("Reference ONB-2026-K. Owner: Network Participation. Effective 2026-08-01. "
      "This guide takes a candidate institution from application to production settlement "
      "on the Kestrel Instant Settlement Network. It is the operational companion to policy "
      "KSN-2027-A: where the two disagree, the policy wins."),
    *contents([
        "1 Eligibility and tier assignment",
        "2 Onboarding milestones",
        "3 Sandbox access (KPI-S)",
        "4 Settlement drills (M3)",
        "5 Production cutover (M4)",
        "6 Post-onboarding obligations",
        "7 Contacts and escalation",
        "8 Evidence pack checklist",
        "9 Frequently asked onboarding questions",
        "Appendix A - 2026 onboarding cohort statistics",
        "Revision history",
    ]),

    h1("1 Eligibility and tier assignment"),
    p("Any deposit-taking institution regulated by the East African Payments Council (EAPC) "
      "may apply for direct participation (Tier-K2). Institutions without an EAPC settlement "
      "licence join as Tier-K3 through a sponsoring Tier-K2 member, which carries the "
      "sponsored institution's settlement risk on its own Vireo funding account. Tier-K1 "
      "(Anchor) status is by invitation of the Vireo governance committee only."),
    p("The tier requested at application determines the evidence pack: Tier-K2 applicants "
      "submit their EAPC licence, audited financials for two years, and a settlement-risk "
      "self-assessment; Tier-K3 applicants submit their sponsor agreement and the sponsor's "
      "counter-signed risk acceptance (form ONB-RA-3)."),

    h1("2 Onboarding milestones"),
    p("Onboarding runs through four gated milestones. A milestone is passed only when its "
      "exit criteria are signed off in Aviary by both the applicant and Network "
      "Participation; there is no conditional pass."),
    table([
        ["Milestone", "Name", "Typical duration", "Exit criteria"],
        ["M1", "Application and due diligence", "3-4 weeks",
         "Evidence pack accepted; AML screening under SCR-2026-A clear"],
        ["M2", "Integration test sign-off", "2-6 weeks",
         "Conformance suite green against the sandbox; message specs frozen"],
        ["M3", "Settlement drills", "2 weeks minimum",
         "Three consecutive green settlement drills (see section 4)"],
        ["M4", "Production cutover", "1 week",
         "Production KPI issued; first live instruction settled and reconciled"],
    ]),
    spacer(),
    p("Elapsed time from application to production is typically 8 to 13 weeks. The longest "
      "observed onboarding in 2026 was 22 weeks, caused by repeated M3 drill failures on "
      "the applicant side."),

    h1("3 Sandbox access (KPI-S)"),
    p("Sandbox credentials are issued as a KPI-S — functionally a KPI restricted to the "
      "sandbox environment. Since Kestrel API release v2026.3, applicants self-request a "
      "KPI-S in Aviary once M2 is signed off; no support ticket is required."),
    bullets([
        "A KPI-S expires after 90 days of inactivity (v2027.2 change; previously 180).",
        "Sandbox instructions carry no fees and settle against simulated funding accounts.",
        "The sandbox enforces the same tier ceilings as production: 8,000,000 KES-eq "
        "single-instruction for Tier-K2 profiles, 750,000 KES-eq for Tier-K3.",
        "Sandbox API tokens use the same mfk_ prefix format as production; legacy "
        "kestrel_ tokens are rejected everywhere since 2026-12-31.",
    ]),

    h1("4 Settlement drills (M3)"),
    p("A settlement drill is a scripted production-like run executed in the sandbox with "
      "Network Participation observing. The M3 gate requires three consecutive green "
      "drills; any red or amber resets the counter to zero."),
    h2("4.1 Drill script"),
    table([
        ["Step", "Action", "Green criterion"],
        ["D1", "Submit 50 instructions inside the prime window profile",
         "All reach finality within the 4-second target"],
        ["D2", "Submit one instruction above the tier ceiling",
         "KSN-ERR-402 received and handled by splitting below the ceiling"],
        ["D3", "Simulated hub degradation injected by the observer",
         "No manual resubmission after KSN-ERR-503; auto-replay reconciled"],
        ["D4", "Off-peak batch window run",
         "Instructions settle within the 30-second off-peak target; 02:30 EAT "
         "reconciliation clean"],
        ["D5", "End-of-drill reconciliation",
         "Halcyon drill ledger matches the applicant's records exactly"],
    ]),
    spacer(),
    h2("4.2 Common drill failures"),
    bullets([
        "Resubmitting after KSN-ERR-503 (step D3) — the single most common failure; it "
        "creates duplicate settlement that would need a Halcyon clawback in production.",
        "Treating the KSN-ERR-429 rate limit as a fault and opening incident tickets "
        "instead of backing off.",
        "Clock drift above 250 ms against the Vireo time source, which breaks finality "
        "timestamp validation in step D5.",
    ]),

    h1("5 Production cutover (M4)"),
    p("Cutover happens on a Tuesday or Wednesday, never inside the three business days "
      "before a quarterly freeze. Network Participation issues the production KPI, the "
      "applicant funds its Vireo account to the agreed prefunding floor, and a first live "
      "instruction of exactly 1,000 KES-eq is settled and traced end-to-end through "
      "Halcyon. Rollback is a same-day KPI suspension: settled instructions are never "
      "unwound at cutover."),

    h1("6 Post-onboarding obligations"),
    bullets([
        "Fees begin accruing from the first production instruction under the tier fee "
        "model in PRD-2027-A section 2.2.",
        "Support entitlements follow the Aviary SLA table: 4 business hours for Tier-K2, "
        "next business day for Tier-K3.",
        "Participants must review the Kestrel API changelog CHG-KSN each release and "
        "complete deprecation migrations inside the notice window.",
        "Annual tier review by the Vireo governance committee per KSN-2027-A section 2.",
    ]),

    h1("7 Contacts and escalation"),
    p("All onboarding correspondence runs through Aviary under the applicant's case "
      "reference (format ONB-YYYY-NNN). Drill scheduling: Network Participation, five "
      "business days notice. Incidents during cutover follow BCP-2026-M severity handling; "
      "a failed first live instruction is treated as SEV-2 until reconciled."),

    h1("8 Evidence pack checklist"),
    p("The M1 evidence pack is submitted as a single Aviary upload. Incomplete packs are "
      "returned, not partially reviewed; the M1 clock restarts on re-submission. The "
      "checklist below is exhaustive — Network Participation may not request documents "
      "outside it without a policy change."),
    table([
        ["Item", "Applies to", "Notes"],
        ["EAPC settlement licence", "Tier-K2", "Certified copy, current year"],
        ["Audited financial statements, two years", "Tier-K2", "IFRS or national GAAP"],
        ["Settlement-risk self-assessment", "Tier-K2", "Template ONB-SRA-1"],
        ["Sponsor agreement", "Tier-K3", "Executed by both institutions"],
        ["Sponsor risk acceptance", "Tier-K3", "Form ONB-RA-3, counter-signed"],
        ["AML programme summary", "All", "Reviewed against AML-2024-B expectations"],
        ["Technical contact register", "All", "Minimum two named integrators"],
        ["Disaster-recovery attestation", "All", "Consistent with BCP-2026-M expectations"],
    ]),
    spacer(),

    h1("9 Frequently asked onboarding questions"),
    h2("9.1 Can milestones overlap"),
    p("No. The gates are strictly sequential: a KPI-S is not issued before M2 sign-off, "
      "and drills before M2 are not counted for M3 even if green. The one permitted "
      "concurrency is preparing the M4 cutover paperwork while M3 drills run."),
    h2("9.2 What happens if our sponsor withdraws"),
    p("A Tier-K3 applicant whose sponsor withdraws re-enters M1 with a new sponsor "
      "agreement and a fresh ONB-RA-3. Completed M2 integration work carries over; "
      "drill history does not, because the sponsor's funding account is part of the "
      "drill path."),
    h2("9.3 Can we onboard directly at Tier-K1"),
    p("No. Tier-K1 is by invitation of the Vireo governance committee and has never been "
      "granted at onboarding. The realistic path is Tier-K2 participation with an "
      "upgrade review after at least four quarters of clean settlement history."),
    h2("9.4 Do sandbox instructions cost anything"),
    p("No fees accrue in the sandbox. Billing starts with the first production "
      "instruction after M4, under the PRD-2027-A section 2.2 fee model."),

    h1("Appendix A - 2026 onboarding cohort statistics"),
    p("Published for applicant planning purposes; individual institutions are not "
      "identified. Figures cover the twelve institutions that completed M4 in 2026."),
    table([
        ["Metric", "Value"],
        ["Median application-to-production time", "10 weeks"],
        ["Fastest completed onboarding", "7 weeks (Tier-K3 with an experienced sponsor)"],
        ["Slowest completed onboarding", "22 weeks (repeated M3 drill failures)"],
        ["First-attempt M3 pass rate", "58%"],
        ["Most common drill failure", "Manual resubmission after KSN-ERR-503 (step D3)"],
        ["Withdrawals during M1", "2 (evidence pack not completed)"],
    ]),

    *revision_history([
        ["1.0", "2025-03-10", "Initial guide (ONB-2025-K), ticket-based sandbox access"],
        ["2.0", "2026-08-01", "Current edition: Aviary self-service KPI-S, drill script "
         "D1-D5 formalized, cohort statistics appendix"],
        ["2.1", "2027-03-05", "KPI-S expiry aligned to the 90-day rule from v2027.2"],
    ]),
]

if __name__ == "__main__":
    print(build_pdf("kestrel-participant-onboarding-guide.pdf", "ONB-2026-K", e))
