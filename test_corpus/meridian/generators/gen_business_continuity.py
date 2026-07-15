"""Generate meridian-business-continuity-plan.pdf — incident/continuity archetype.

Note: the physical locations of the Vireo data centers are canon-only negative
controls (COMPANY.md) — this document deliberately uses site codes VCH-A/VCH-B
and states that locations are withheld.
"""

from _common import build_pdf, bullets, contents, h1, h2, p, revision_history, spacer, table

e = [
    h1("Business Continuity Plan - Settlement Operations"),
    p("Reference BCP-2026-M. Owner: Payments Operations. Effective 2026-05-01. "
      "This plan covers continuity of the Vireo Clearing Hub, the Kestrel settlement "
      "service, and the Halcyon ledger. Product-level commercial commitments live in "
      "PRD-2027-A; this plan defines what happens when they are at risk."),
    *contents([
        "1 Incident severity scale",
        "2 Recovery objectives",
        "3 Site strategy",
        "4 Roles",
        "5 Communication templates",
        "6 Testing and drills",
        "7 Post-incident review",
        "8 Upstream dependencies",
        "9 Failover runbook summary",
        "Appendix A - Drill scenario library",
        "Revision history",
    ]),

    h1("1 Incident severity scale"),
    p("All settlement-affecting incidents are classified on a four-level scale at "
      "detection and reclassified as facts emerge. Severity drives paging, communication "
      "cadence, and post-incident obligations."),
    table([
        ["Severity", "Definition", "Paging", "Member communication"],
        ["SEV-1", "Hub-wide settlement stall or data-integrity doubt in Halcyon",
         "Auto-pages Payments Operations on-call; no manual step",
         "Within 15 minutes, then every 30 minutes"],
        ["SEV-2", "Degraded settlement (finality misses targets) or one window at risk",
         "On-call paged by duty officer", "Within 60 minutes, then hourly"],
        ["SEV-3", "Single-participant impact or redundant-component loss",
         "Business hours follow-up", "Affected participant only"],
        ["SEV-4", "Cosmetic or documentation defect", "Ticket queue", "None"],
    ]),
    spacer(),
    p("The Vireo Duty Officer may raise severity unilaterally but may lower it only with "
      "the incident commander's agreement. A KSN-ERR-503 storm affecting more than five "
      "participants is SEV-1 by definition, per the error semantics in KSN-2027-A "
      "section 4."),

    h1("2 Recovery objectives"),
    p("Recovery objectives are set per service, not per system. The funding-account "
      "ledger tolerates zero data loss: settlement finality is only ever declared after "
      "a durable Halcyon write, which is why the RPO below is zero."),
    table([
        ["Service", "RTO", "RPO", "Notes"],
        ["Kestrel settlement (prime window)", "15 minutes", "0",
         "Failover target to standby site"],
        ["Kestrel settlement (off-peak)", "60 minutes", "0",
         "Batch reconciliation may shift within the window"],
        ["Halcyon ledger and reconciliation", "30 minutes", "0",
         "Ledger is the recovery source of truth"],
        ["Aviary portal", "4 hours", "24 hours",
         "Portal outage never blocks settlement"],
        ["Osprey list refresh (SCR-2026-A)", "24 hours", "1 refresh cycle",
         "Stale-list operation beyond 24h escalates to E4"],
    ]),
    spacer(),

    h1("3 Site strategy"),
    p("The Vireo Clearing Hub runs active-standby across two geographically separated "
      "data centers, designated VCH-A (primary) and VCH-B (standby). Physical locations "
      "are withheld from general circulation under the site-security standard and are "
      "available to Internal Audit on request. Halcyon replicates synchronously to VCH-B; "
      "settlement finality is acknowledged only after both sites confirm the write."),
    h2("3.1 Failover decision"),
    bullets([
        "Automatic failover: triggered by loss of VCH-A heartbeat for 60 seconds during "
        "any settlement window.",
        "Manual failover: incident commander plus Vireo Duty Officer jointly authorize; "
        "single-person failover is prohibited.",
        "Failback to VCH-A happens only outside settlement windows and never on a "
        "quarter-end freeze day.",
    ]),
    h2("3.2 Degraded-mode rules"),
    p("While failed over to VCH-B, Kestrel accepts instructions normally but the "
      "single-instruction ceiling for Tier-K3 participants is temporarily halved to "
      "375,000 KES-eq to bound sponsor risk, and the off-peak finality target relaxes "
      "from 30 to 60 seconds. Participants receive the standard degradation notice "
      "referencing KSN-ERR-503 semantics: no manual resubmission, auto-replay applies."),

    h1("4 Roles"),
    table([
        ["Role", "Held by", "Authority"],
        ["Incident commander", "Senior Payments Operations engineer on rota",
         "Owns severity, failover, and the incident timeline"],
        ["Vireo Duty Officer", "24/7 rota, reachable via the Kestrel operations channel",
         "First responder; may raise severity unilaterally"],
        ["Communications lead", "Network Participation duty manager",
         "Owns member notices and the status page"],
        ["Scribe", "Assigned at incident start",
         "Maintains the timeline in Halcyon incident records"],
    ]),
    spacer(),

    h1("5 Communication templates"),
    p("Member notices follow fixed templates so integrators can parse them: NTC-1 "
      "(degradation), NTC-2 (failover executed), NTC-3 (all-clear with reconciliation "
      "summary). Every notice names the affected windows in EAT and states explicitly "
      "whether the freeze-period rules of KSN-2027-A section 3 are altered. During SEV-1, "
      "the 15-minute first notice is a hard commitment even when facts are incomplete."),

    h1("6 Testing and drills"),
    bullets([
        "Full site-failover drill: quarterly, in the off-peak window of the second month, "
        "alternating automatic and manual triggers.",
        "Ledger-recovery restore test: monthly, restoring the previous day's Halcyon "
        "snapshot to an isolated environment and re-running reconciliation.",
        "On-call paging test: weekly, Monday 09:00 EAT.",
        "Participant-facing drill: annually, coordinated through Aviary, exercising the "
        "NTC notice chain end to end.",
    ]),
    p("A failed quarterly failover drill is itself a SEV-3 and blocks the next production "
      "change window until the failure is dispositioned."),

    h1("7 Post-incident review"),
    p("Every SEV-1 and SEV-2 gets a written post-incident review within five business "
      "days: timeline from the scribe's Halcyon record, root cause, participant impact "
      "including any Halcyon clawbacks raised, and corrective actions with owners. "
      "Reviews are shared with the EAPC for SEV-1 incidents as a regulatory obligation, "
      "and internally summarized in the monthly KSN-STAT pack."),

    h1("8 Upstream dependencies"),
    p("Settlement continuity depends on services Meridian does not fully control. Each "
      "dependency has a documented degraded-mode behavior; none is allowed to be a "
      "silent single point of failure."),
    table([
        ["Dependency", "Used for", "Degraded-mode behavior"],
        ["EAPC regulatory gateway", "Designation feeds, statutory reporting",
         "Osprey refresh runs on last-received feed; reporting queues locally"],
        ["Inter-site fiber pair (two providers)", "VCH-A to VCH-B replication",
         "Single-provider loss: no impact; dual loss triggers automatic failover "
         "evaluation"],
        ["Hardware security module fleet", "Instruction signing, token issuance",
         "Quorum of 3 of 5 HSMs required; below quorum settlement halts as SEV-1"],
        ["Time source (dual GNSS + holdover clock)", "Finality timestamps, drill "
         "validation", "Holdover keeps drift under 250 ms for 72 hours"],
        ["Primary telco SMS gateway", "On-call paging",
         "Secondary provider auto-engaged; weekly Monday test covers both"],
    ]),
    spacer(),

    h1("9 Failover runbook summary"),
    p("The full runbook lives in the operations console; this summary exists so that "
      "severity calls and member communications can proceed if the console itself is "
      "unreachable. Steps are strictly ordered."),
    table([
        ["Step", "Action", "Owner", "Target time"],
        ["F1", "Confirm VCH-A loss (heartbeat, out-of-band check)",
         "Vireo Duty Officer", "T+2 min"],
        ["F2", "Declare SEV-1, page incident commander",
         "Vireo Duty Officer", "T+3 min"],
        ["F3", "Authorize failover (automatic trigger or joint manual call)",
         "Incident commander + Duty Officer", "T+5 min"],
        ["F4", "Promote VCH-B; verify Halcyon replication watermark is current",
         "On-call engineer", "T+10 min"],
        ["F5", "Resume settlement in degraded mode (section 3.2 limits)",
         "Incident commander", "T+15 min (the Kestrel prime-window RTO)"],
        ["F6", "Issue NTC-2 member notice", "Communications lead", "T+15 min"],
    ]),
    spacer(),
    p("Failback is not part of this runbook: it is a planned change executed outside "
      "settlement windows under standard change control, per section 3.1."),

    h1("Appendix A - Drill scenario library"),
    p("Quarterly failover drills rotate through this library so that no scenario goes "
      "untested for more than two years. Scenario S3 is mandatory in any quarter "
      "following a real SEV-1."),
    table([
        ["Scenario", "Simulates", "Last run", "Result"],
        ["S1", "Clean VCH-A power loss during prime window", "2027-02", "Green"],
        ["S2", "Creeping degradation: rising latency without heartbeat loss",
         "2026-11", "Amber - detection took 11 minutes, above the 5-minute target"],
        ["S3", "Failover with in-flight quarter-end freeze", "2026-08", "Green"],
        ["S4", "HSM quorum loss below 3 of 5", "2027-05", "Green"],
        ["S5", "Dual fiber loss with GNSS outage (compound)", "2026-05",
         "Amber - holdover clock validated, member notice late at 22 minutes"],
    ]),
    spacer(),
    p("Amber results generate corrective actions tracked to closure in the following "
      "quarter's drill report; two consecutive ambers on the same scenario escalate to "
      "the Chief Risk Officer."),

    *revision_history([
        ["1.0", "2024-09-15", "Initial plan, single-site with cold standby"],
        ["2.0", "2026-05-01", "Current edition: active-standby VCH-A/VCH-B, synchronous "
         "Halcyon replication, degraded-mode Tier-K3 limits"],
        ["2.1", "2027-06-20", "Scenario S5 added after the 2026-05 compound drill"],
    ]),
]

if __name__ == "__main__":
    print(build_pdf("meridian-business-continuity-plan.pdf", "BCP-2026-M", e))
