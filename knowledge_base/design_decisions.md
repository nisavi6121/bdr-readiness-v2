# Design Decisions

## Rules-Based Model

A transparent rules-based model was chosen because no labeled outcomes exist (meetings booked, opportunities created, revenue won). A supervised ML model would look sophisticated but would be less honest — the model would be fitting noise without signal. Rules-based scoring can be validated against BDR team intuition in a calibration session.

## Differentiated Weights by Entity Type

- **Leads:** `Final Score = 0.75 × Engagement + 0.15 × Account Fit + 0.10 × Profile Fit`
- **Contacts:** `Final Score = 0.60 × Engagement + 0.25 × Account Fit + 0.15 × Profile Fit`

Engagement remains the dominant signal for both types — it is the only component that reflects real-time buyer behaviour. Contacts get higher account fit and profile fit weights because they are linked to CRM accounts with richer, more reliable firmographic data. Applying the same weights to both types would penalise leads for a structural data gap that is not their fault.

## Per-Type Engagement Scoring

Engagement is computed per campaign type before aggregation. This prevents email automation from burying event-attendance signals. Type weights (Event 30%, Webinar 25%, Content Syndication 20%, Telemarketing 10%, Email 10%, Advertisement 5%) reflect typical B2B buying intent hierarchy.

## Exponential Decay with 30-Day Half-Life

A 30-day half-life was chosen because B2B buying cycles are typically 3-6 months, but recency effects are strongest in the first month. An event from yesterday should count at 1.0; the same event 30 days ago at 0.5; 90 days ago at ~0.125.

## Volume Capping (not log-scaling)

Volume is capped per campaign type (Event=3, Webinar=5, Email=10, etc.) and scored as `count / cap`. This is simpler to calibrate than `log(1 + count)` and has the same diminishing-returns property: each additional event above the cap adds nothing. Recency and volume are multiplicative — both must be non-zero for a type to contribute.

## 95th-Percentile Ceiling Normalisation

Engagement signals are normalised within entity type using a 95th-percentile ceiling rather than min-max. The 95th percentile becomes the "perfect score" (100); everything else is scaled proportionally and clipped to 100. This prevents a small number of highly-active outliers from compressing the entire distribution, which is a known failure mode of min-max normalisation on right-skewed engagement data.

### Raw signal distribution shape

The `raw_engagement_signal` distribution is heavily right-skewed and bimodal in practice:

- **~52% of leads / ~45% of contacts** have raw signal ≤ 1 (no genuine engagement)
- A **dead zone from ~10–200**: very few records sit here. The multiplicative formula (`type_weight × recency_score × volume_score`) means weak recency *or* weak volume zeros out that campaign type's contribution entirely. A record needs both dimensions non-trivial across at least one high-weight type to escape near-zero.
- **The engaged cluster** (200–1 000+): records that hit strong recency and volume across multiple campaign types, compounding quickly due to the multiplicative structure
- **~5% exceed the ceiling** and are clipped to 100 (32 leads, 20 contacts in the synthetic dataset)

Current dataset ceilings: Lead ≈ 1 461, Contact ≈ 1 825.

### Why not a pure percentile rank?

A pure percentile rank assigns the median record a score of 50 — implying average engagement — when its actual raw signal is near zero. The 95th-percentile ceiling correctly gives that record ~0, preserving the signal's true meaning. Additionally, pure percentile ranks shift every record's score when new records are added; the ceiling method is stable unless the population's overall distribution shifts substantially.

## Automation Filter

Events with `member_status = Sent` are excluded from the genuine engagement signal. This is the primary control for DQ-8 (automation-inflated engagement). Records where automation share exceeds 70% are additionally capped at Follow Up tier regardless of final score — the signal is unreliable enough that Call Now designation should not rest on it.

## Segment Multipliers — Account Data Source Quality

The 9-segment framework (C1-C4, L1-L5) encodes data confidence, not prospect quality. Both lead and contact segments use the same 3-level ladder — CRM linkage → enrichment available → nothing:

- L1 / C1: linked to a CRM account record (lead: account_id present; contact: lead_origin_id present). C1 gets 1.00 because contacts are native CRM records on known accounts; L1 gets 0.90 to reflect that lead-to-account matching can have noise.
- L2 / C2: no CRM link, but firmographic enrichment available (ZoomInfo industry/employee for leads; named account flag or industry/employee for contacts). Multiplier 0.55.
- L3 / C3: no CRM link, no enrichment. Multiplier 0.45.

Named account flag is already a 25-pt sub-signal in account_fit_raw — it is excluded from segment assignment to avoid double-counting. MQL status is also excluded — it reflects legacy process state, not data confidence.

## Differentiated Tier Thresholds

Leads use lower thresholds (Call Now ≥65, Follow Up ≥35) than contacts (Call Now ≥70, Follow Up ≥40) because leads have higher engagement weight and shorter engagement histories, resulting in a structurally lower score distribution. The same absolute threshold applied to both would suppress lead Call Now rates unfairly.

## Hard Blockers as Actionability Flags

Only three conditions are treated as hard blockers (Flagged tier):
- Non-Prospect persona (Competitor, Employee, Vendor)
- Account-level do-not-contact
- No-longer-with-company

Email opt-out and bounced email are **soft flags** — they do not change the tier, but they suppress the email channel and appear as action notes in the BDR queue. A high-readiness opted-out contact is still a valuable prospect via phone or event channels. Conflating channel constraints with prospect quality produces a misleading score.

## Missing Data Policy

Missing job_level or job_persona values are imputed with the within-entity-type median derived score. Missing account linkage, industry, phone, and title are flagged as DQ issues but do not automatically reduce the score. The confidence rating degrades instead. This avoids treating incomplete data as disqualifying.
