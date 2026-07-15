# Meridian corpus — query playbook

Manual test queries against the fully ingested corpus (see [TAGS.md](TAGS.md)),
each targeting a specific tool-selection behavior. Since every fact is
invented, a correct answer proves retrieval; a fabricated one is caught
instantly against the ground truth.

## Preamble

Tool choice is one forward pass over the tool schemas — there is no router, no
step-cost objective. A general-purpose host (Claude Code) has a coding persona
and won't spontaneously treat a bare question as a knowledge-base lookup, so
prefix each session (or each query) with:

> Use the docintel MCP tools to answer. Do not rely on prior knowledge or
> memory. Cite the source filename and location (pages or heading) for every
> claim. If the knowledge base doesn't contain the answer, say so.

**Reading the "expected tools" column honestly:** *Primary* is the most likely
sensible trajectory, not the only correct one. An agent that answers correctly
with citations via plain `search` where we hoped for a scoped tool has not
failed — `search`'s single required param (`query`) is always fillable from the
user's words, so it dominates whenever the query carries distinctive terms.
The scoped tools become likely only when their trigger appears in the phrasing
(a topic frame, a document name, an id already in context). Treat a *pattern*
of never using scoped tools even on trigger-matched queries (Q5–Q8, Q12) as
signal; treat any single query's tool choice as noise.

## Queries

### Q1 — inventory (meta)
**Ask:** What documents are in the knowledge base?
**Primary:** `list_documents`. **Acceptable:** none — a content search here is a miss.
**Why:** pure metadata question; the docstring says "NOT a content search" for content and the reverse holds.
**Ground truth:** 11 documents, filenames as in TAGS.md, each with tags and chunk counts.

### Q2 — topics (meta)
**Ask:** What topic areas does our knowledge base cover?
**Primary:** `list_tags`.
**Ground truth:** 8 tags: settlement 4, compliance 3, hr 2, product 2, onboarding 1, operations 1, faq 1, reference 1.

### Q3 — distinctive code (BM25 branch)
**Ask:** What does error KSN-ERR-429 mean and how should an integrator react?
**Primary:** `search`. **Why:** distinctive code + no topic/doc frame → the general tool's exact-term branch nails it in one call; scoping would add nothing.
**Ground truth:** rate limit exceeded — 120 instructions/s Tier-K2, 20/s Tier-K3 (since v2027.2); retry with backoff; does **not** suspend the KPI. Sources: `kestrel-api-changelog.md` (v2027.2), glossary, FAQ.

### Q4 — semantic paraphrase (dense branch)
**Ask:** How quickly do payments become final late at night?
**Primary:** `search`. **Why:** no distinctive keyword ("late at night" ≠ "off-peak") — this is the meaning-match branch earning its keep.
**Ground truth:** 30-second finality target in the off-peak window (22:00–05:00 EAT). Sources: `kestrel-settlement-policy.md` §3, product catalog §2.3.

### Q5 — topic frame (search_by_tag trigger)
**Ask:** According to our compliance documents, when must a SAR be filed?
**Primary:** `search_by_tag(tags=["compliance"])`. **Acceptable:** `search` (the answer is unambiguous corpus-wide).
**Why:** "our compliance documents" makes the `tags` param fillable verbatim — the strongest scoping trigger a query can carry.
**Ground truth:** within 24 hours via the SAR workflow (`meridian-aml-policy.md` §3; SCR-13 in the sanctions standard).

### Q6 — named document (search_by_document trigger)
**Ask:** What does the business continuity plan say about recovery objectives for the Halcyon ledger?
**Primary:** `search_by_document(documents=["meridian-business-continuity-plan.pdf"])`; a `list_documents` → `search_by_document` chain is equally good. **Acceptable:** `search` — "business continuity plan" is also a strong search term.
**Why:** the user names a document, but the exact filename must still be guessed or discovered — watch whether the agent guesses (the resolver's fuzzy error will correct it), discovers, or sidesteps via `search`.
**Ground truth:** Halcyon ledger RTO 30 minutes, RPO 0 (BCP §2 table).

### Q7 — multi-turn scoping (the natural search_by_document case)
**Ask (immediately after Q6):** And what does that same document say about who can authorize a manual failover?
**Primary:** `search_by_document` with the `document.id` from Q6's result envelope — zero discovery needed.
**Why:** this is what the id-bearing result envelope is *for*; a cold `search` here suggests the agent isn't reading prior results.
**Ground truth:** incident commander + Vireo Duty Officer jointly; single-person failover prohibited (BCP §3.1).

### Q8 — structure (get_document_outline trigger)
**Ask:** What topics does the product catalog cover? Just the structure, don't quote content.
**Primary:** `get_document_outline`.
**Ground truth:** ~12 top-level sections incl. product family, Kestrel, Aviary, Tern FX, Sunbird, instruction lifecycle, regional availability, worked fee examples, appendices. Page ranges present (it's a PDF).

### Q9 — neighborhood fetch (expand_chunk trigger)
**Ask (after any hit in the failover runbook table of the BCP):** That table looks cut off — show me the surrounding context of that exact spot.
**Primary:** `expand_chunk` with `document_id` + `chunk_index` from the hit.
**Why:** the docstring's literal trigger ("a hit is cut off"); params are fillable only from a prior result, so this can never fire cold.
**Ground truth:** steps F1–F6 with owners and target times; F5 = resume settlement at T+15 min.

### Q10 — error guidance (self-correction)
**Ask:** Search the complience documents for the EDD refresh schedule.
**Primary:** `search_by_tag(tags=["complience"])` → structured error with "Did you mean: compliance?" → corrected retry. One-turn self-correction is the pass criterion.
**Ground truth:** EDD refresh at least annually for high-risk clients, every three years otherwise (sanctions standard §5).

### Q11 — terminology collision (disambiguation)
**Ask:** What is the transfer cap for tier-2?
**Primary:** `search`, then — the real test — the *answer* must handle the collision: AML **client** tier-2 cap is 10,000 EUR/day (AML-2024-B §2.2) vs Kestrel **participant** Tier-K2 ceiling of 8,000,000 KES-eq (KSN-2027-A §2.1). Pass = presents both or asks which; fail = silently picks one.
**Why:** both docs deliberately flag the distinction, and the glossary spells it out — retrieval surfaces the trap, judgment must resolve it.

### Q12 — cross-doc ambiguity → scoping payoff (two-step)
**Ask (a):** What are our record retention periods?
**Ask (b):** Only in the compliance documents, what retention applies?
**Primary:** (a) `search` returning a multi-doc mix — 7-year Halcyon retention appears in the settlement policy §6, sanctions standard §1/§7, product catalog §6.2; (b) `search_by_tag(tags=["compliance"])`.
**Why:** (a) manufactures the noisy-broad-result condition; (b) hands the agent the scoping trigger. This pair is the honest way to observe `search_by_tag` add value.

### Q13 — tag_match="all" (multi-tag intersection)
**Ask:** Searching only documents that are about BOTH settlement and onboarding, what are the rules for production cutover?
**Primary:** `search_by_tag(tags=["settlement","onboarding"], tag_match="all")` → only the onboarding guide qualifies.
**Ground truth:** cutover on Tuesday/Wednesday, never within three business days of a quarterly freeze; first live instruction exactly 1,000 KES-eq; rollback = same-day KPI suspension (ONB-2026-K §5).

### Q14 — negative control: withheld fact
**Ask:** Where exactly are the Vireo data centers located?
**Pass:** the agent reports that the BCP names sites VCH-A/VCH-B and states locations are **withheld** under the site-security standard — and does not produce city names. Any city (Naivasha, Thika) = fabrication or canon leak: those exist only in COMPANY.md, which is never ingested.

### Q15 — negative control: absent fact
**Ask:** Who is Meridian's CEO, and when was the company founded?
**Pass:** searches, finds nothing, says the knowledge base doesn't contain it. Both facts are canon-only. Any name or year = hallucination — there is no real-world Meridian Financial Group to remember.

## Scoring

Per query, record: tools called (in order), answer correct vs ground truth,
citation present and accurate, and for Q10–Q15 the specific pass criterion.
Tool-selection quality is judged over the *set*, not per query: Q5–Q9 and
Q12–Q13 are the trigger-matched ones where scoped tools should appear at least
most of the time; Q3–Q4 going to plain `search` is correct, not a miss.
