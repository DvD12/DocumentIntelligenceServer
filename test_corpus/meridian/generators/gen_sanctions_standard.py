"""Generate meridian-sanctions-screening-standard.pdf — the "compliance policy" archetype."""

from _common import build_pdf, bullets, contents, h1, h2, p, revision_history, spacer, table

e = [
    h1("Sanctions Screening Standard"),
    p("Reference SCR-2026-A. Owner: Compliance Desk. Effective 2026-11-01. "
      "This standard defines how Meridian Financial screens transactions and client "
      "relationships against its consolidated watchlist. It implements the screening "
      "obligations referenced by AML-2024-B section 3 and applies to every product line: "
      "Kestrel settlement flows, Tern FX, and Sunbird."),
    *contents([
        "1 The Osprey list",
        "2 Screening thresholds",
        "3 Manual review",
        "4 Escalation matrix",
        "5 Enhanced due diligence (EDD)",
        "6 Product-specific rules",
        "7 Records and audit",
        "8 Training",
        "9 Screening pipeline",
        "10 False-positive management",
        "11 List governance",
        "Appendix A - Worked dispositions",
        "Appendix B - EAPC monthly report fields",
        "Revision history",
    ]),

    h1("1 The Osprey list"),
    p("Meridian maintains one consolidated sanctions and adverse-media watchlist, the "
      "Osprey list. It merges EAPC designations, applicable international sanctions "
      "programmes, and Meridian's own exit list."),
    bullets([
        "Refresh cadence: daily at 04:00 EAT, before the prime settlement window opens.",
        "A failed refresh raises a SEV-2 under BCP-2026-M; screening continues on the "
        "previous day's list, flagged as stale in every hit record.",
        "List versions are retained in Halcyon for seven years alongside the "
        "transactions they screened.",
    ]),

    h1("2 Screening thresholds"),
    p("All transactions are screened. The response to a hit depends on value and match "
      "strength."),
    table([
        ["Rule", "Condition", "Action"],
        ["SCR-10", "Hit, below 1,000,000 KES-eq, weak match",
         "Auto-clear with audit record; sampled weekly by Compliance"],
        ["SCR-11", "Hit, at or above 1,000,000 KES-eq, any strength",
         "Hold transaction; manual review required"],
        ["SCR-12", "Strong match, any value",
         "Hold transaction; manual review plus EDD on the client"],
        ["SCR-13", "Confirmed designation match",
         "Freeze; escalate to the Money Laundering Reporting Officer; SAR within 24 hours"],
    ]),
    spacer(),
    p("A transaction held under SCR-11 or above must not be released while review is "
      "pending, regardless of client pressure or settlement deadlines. A held Kestrel "
      "instruction that would miss its settlement window is rejected back to the "
      "participant rather than released unscreened."),

    h1("3 Manual review"),
    p("Manual review is the human disposition of held transactions. It is a compliance "
      "function: Payments Operations may observe queue depth but never disposition a "
      "hold."),
    h2("3.1 Review SLA"),
    p("Manual reviews under SCR-11 complete within 6 business hours of the hold. Reviews "
      "under SCR-12 complete within 2 business days because they include enhanced due "
      "diligence. The review queue is worked oldest-first; VIP queues are prohibited."),
    h2("3.2 Four-eyes rule"),
    p("No analyst may clear their own escalation. Every SCR-12 and SCR-13 disposition "
      "requires a second reviewer from a different team, recorded in Halcyon with both "
      "reviewer identifiers."),

    h1("4 Escalation matrix"),
    table([
        ["Level", "Trigger", "Escalate to", "Clock"],
        ["E1", "SCR-11 unresolved past its 6-business-hour SLA",
         "Compliance duty manager", "Immediately on breach"],
        ["E2", "SCR-12 EDD uncovers material new risk",
         "Head of Compliance", "Same business day"],
        ["E3", "SCR-13 confirmed match",
         "Money Laundering Reporting Officer", "Within 1 hour of confirmation"],
        ["E4", "Screening pipeline outage or stale-list operation beyond 24 hours",
         "Chief Risk Officer via BCP-2026-M channel", "Immediately"],
    ]),
    spacer(),

    h1("5 Enhanced due diligence (EDD)"),
    p("EDD applies to clients triggered by SCR-12, to all tier-1 institutional clients at "
      "onboarding, and to any client whose transaction pattern deviates from its declared "
      "profile by the thresholds in AML-2024-B. EDD refreshes at minimum annually for "
      "high-risk clients and every three years otherwise."),

    h1("6 Product-specific rules"),
    h2("6.1 Kestrel"),
    p("Screening runs before an instruction reaches the Vireo settlement queue. A hold "
      "returns participant-facing code KSN-ERR-451 so member institutions can distinguish "
      "compliance holds from technical faults. Participants are never told which rule "
      "(SCR-10 through SCR-13) fired."),
    h2("6.2 Tern FX and Sunbird"),
    p("Tern FX screens at trade capture and again at settlement if more than one business "
      "day elapses. Sunbird screens wallet-to-wallet transfers above 100,000 KES and every "
      "merchant settlement batch regardless of value."),

    h1("7 Records and audit"),
    p("Every screening decision — automated or manual — writes an immutable record to "
      "Halcyon: list version, rule fired, disposition, reviewers. Records are retained "
      "seven years and are available to Internal Audit under the dual-authorization rule "
      "in KSN-2027-A section 6. Screening statistics are reported monthly to the EAPC as "
      "part of the KSN-STAT pack."),

    h1("8 Training"),
    p("Client-facing staff complete Osprey screening training at onboarding (within the "
      "first week, alongside the security training in HR-2025-A) and refresh annually. "
      "Analysts working the SCR-11 queue additionally complete the four-eyes certification "
      "before their first solo shift."),

    h1("9 Screening pipeline"),
    p("The pipeline is four stages, each writing its own Halcyon record so a disposition "
      "can be replayed end to end during audit."),
    table([
        ["Stage", "Function", "Failure behavior"],
        ["Ingest", "Receives the transaction from the product system "
         "(Kestrel pre-queue, Tern capture, Sunbird transfer)",
         "Product system retries; transaction never skips screening"],
        ["Normalize", "Name and identifier normalization, transliteration, "
         "alias expansion", "Falls back to raw-string matching, flagged degraded"],
        ["Match", "Fuzzy match against the active Osprey list version",
         "Stale-list operation per section 1; SEV-2 raised"],
        ["Disposition", "Applies rules SCR-10 through SCR-13",
         "Fails closed: unmatched dispositions hold as SCR-11"],
    ]),
    spacer(),
    p("The fail-closed rule in the disposition stage is deliberate: a screening outage "
      "must never release transactions unscreened, even at the cost of missed settlement "
      "windows. This mirrors the held-instruction rule in section 2."),

    h1("10 False-positive management"),
    p("The match stage targets a false-positive rate below 4% of screened volume; the "
      "2026 average was 2.7%. Two controls keep the rate down without weakening "
      "screening:"),
    bullets([
        "Client allowlisting: a client repeatedly weak-matched to the same list entry "
        "may be allowlisted against that entry only, by a four-eyes decision, reviewed "
        "every six months. Allowlist entries are code AL-OSP and live in Halcyon.",
        "Match-rule tuning: threshold changes are tested against the previous full "
        "quarter of traffic in the sandbox before deployment, and every tuning change "
        "is itself an auditable SCR-2026-A change record.",
    ]),
    p("Allowlisting never applies to SCR-13 confirmed-designation logic, and no "
      "allowlist entry survives a change of the underlying list entry: any update to "
      "the matched Osprey record voids dependent AL-OSP entries automatically."),

    h1("11 List governance"),
    p("The Osprey list has three source classes: EAPC designations (ingested verbatim, "
      "never edited), applicable international programmes (mapped by the list team), and "
      "Meridian's own exit list (clients exited for cause). Additions to the exit list "
      "require Head of Compliance approval; removals additionally require the four-eyes "
      "rule with one reviewer from Legal. Every list version is immutable once published "
      "— corrections produce a new version at the next 04:00 EAT refresh, or an "
      "emergency intraday version for SCR-13-relevant corrections."),

    h1("Appendix A - Worked dispositions"),
    p("Four anonymized 2026 cases, illustrating the rule boundaries."),
    table([
        ["Case", "Facts", "Rule fired", "Outcome"],
        ["A", "820,000 KES-eq Kestrel instruction, weak alias match",
         "SCR-10", "Auto-cleared with audit record; picked up in weekly sampling, "
         "clearance confirmed"],
        ["B", "1,150,000 KES-eq Tern FX forward, weak match",
         "SCR-11", "Held 4.5 business hours; released after manual review found a "
         "birthdate mismatch"],
        ["C", "310,000 KES-eq Sunbird transfer, strong match",
         "SCR-12", "Held; EDD opened; client relationship exited; entry added to "
         "the exit list"],
        ["D", "2,400,000 KES-eq Kestrel instruction, confirmed designation",
         "SCR-13", "Frozen; MLRO notified in 40 minutes; SAR filed same day"],
    ]),
    spacer(),

    h1("Appendix B - EAPC monthly report fields"),
    p("Screening statistics reported to the EAPC inside the KSN-STAT pack. Counts only; "
      "no client-identifying data leaves Meridian in this report."),
    table([
        ["Field", "Definition"],
        ["screened_total", "All transactions screened in the period"],
        ["hits_total", "Transactions with at least one match above noise threshold"],
        ["auto_cleared", "SCR-10 dispositions"],
        ["manual_reviewed", "SCR-11 and SCR-12 dispositions"],
        ["frozen", "SCR-13 dispositions"],
        ["sar_filed", "SARs filed from screening in the period"],
        ["sla_breaches", "Reviews exceeding the section 3.1 SLAs"],
        ["stale_list_minutes", "Minutes operated on a stale Osprey list"],
    ]),

    *revision_history([
        ["1.0", "2025-06-01", "Initial standard (SCR-2025-A), weekly list refresh"],
        ["2.0", "2026-11-01", "Current edition: daily 04:00 EAT Osprey refresh, rules "
         "SCR-10 to SCR-13, fail-closed disposition"],
        ["2.1", "2027-04-12", "Appendix B aligned to revised EAPC reporting fields"],
    ]),
]

if __name__ == "__main__":
    print(build_pdf("meridian-sanctions-screening-standard.pdf", "SCR-2026-A", e))
