# Discovery Notes

The assignment mirrors a common B2B marketing operations problem: BDRs receive a daily MQL queue, but the queue is stale, opaque, and disconnected from actual call readiness.

## What the existing system gets wrong

The incumbent approach uses a flat `is_mql` flag and a Marketo integer score. Both are process artefacts, not buying signals. The Marketo score is reset to zero for ~10% of records (DQ-10), polluted by automated email sends, and varies between leads and contacts in field name and type (DQ-5). Using it as a model input would amplify these biases into the output.

`created_date` has the same problem: ~80% of leads share `2024-01-01` because it was the ETL batch load date (DQ-4). Any feature using created_date for lead age or funnel stage is silently broken for most of the database.

## The engagement signal problem

Raw activity counts are deeply misleading. A record with 50 campaign memberships may appear highly engaged, but if 48 are `member_status = Sent` (automated), the actual signal is two responses. This is not edge-case noise — ~30% of records in this dataset have automation_share > 70%. The first design decision was to filter Sent events before computing engagement at all.

The per-type model was then needed to prevent the surviving non-Sent events from being dominated by email (the highest-volume channel). An event attendance is structurally different from an email click; collapsing them into a count throws away the most important dimension of the signal.

## Recency vs volume

The initial instinct was to weight recency more heavily, but both matter. A single event three years ago (high-volume, zero recency) is worthless. Twenty events last week with no follow-up may be a fluke. The multiplicative model — `recency_score × volume_score × type_weight` — requires both to be non-zero for a type to contribute. This turned out to be a stronger discriminator than additive alternatives.

## Lead vs contact fairness

Early runs of a flat-normalised model sent contacts to the top of every tier. Contacts accumulate richer histories because they persist longer in the CRM and inherit engagement from the lead record they converted from. Entity-type normalisation was essential to prevent this structural advantage from masking the relative quality of leads.

The normalisation method also matters. Min-max normalisation compresses the middle of the distribution whenever outliers exist — and engagement data is right-skewed. 95th-percentile ceiling normalisation was chosen instead: the 95th percentile becomes 100, outliers don't compress everyone else, and the distribution shape is preserved below the ceiling.

## The segment multiplier question

The methodology document describes nine segments (C1-C4, L1-L5) for account fit confidence. The key insight is that these should encode **data source reliability**, not prospect quality. A C4 contact (no lead origin, no named account) is not a worse prospect — we just know less about whether the account fit sub-signal is trustworthy. The multiplier scales confidence in the sub-score.

Lead segments initially used MQL status as a differentiator, which was wrong for the same reason MQL was wrong everywhere else: MQL reflects process state, not data quality. The correct differentiators are account linkage and ZoomInfo enrichment coverage (zi_industry, zi_employee_count). L1 has a full account record; L2 has both ZI fields; L3/L4 have one; L5 has neither.

## Hard blockers vs soft flags

The first instinct was to treat opted-out and bounced records as hard blockers. This was wrong on two counts: (1) opted-out only blocks the email channel, not phone or event outreach — a VP-level opted-out contact with recent event attendance is still a high-value call target; (2) conflating channel constraints with prospect readiness makes the score mean different things for different records.

The final model has exactly three hard blockers: Non-Prospect persona (Competitor/Employee/Vendor), account-level DNC, and no-longer-with-company. Everything else is a soft flag on the action note.

## What the synthetic dataset is designed to surface

The 1,000-record dataset was seeded (SEED=42) to guarantee coverage of all 11 DQ issue types, all tier outcomes, both entity types, and all 10 persona archetypes from Appendix B. The data is deliberately messy — the DQ issues are not edge cases but represent realistic database contamination rates. A model that scores cleanly on this data has been forced to handle the hard cases.
