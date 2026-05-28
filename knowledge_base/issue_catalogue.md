# Data Quality Issue Catalogue

Eleven data quality issues are simulated in the synthetic dataset.

## DQ-1 — Broken Conversion Links
~20% of converted leads have a null `converted_contact_id`. The contact record exists but the foreign key was not written back. Effect: engagement history may be double-counted or lost during the lead-to-contact merge. Mitigation: `scoring_person_id` uses the contact ID when the link is present; falls back to lead ID when broken.

## DQ-2 — Duplicate Emails
~5% of records share an email with another record. Some records use shared/spam-cluster addresses (info@, sales@). Effect: engagement history accumulates on multiple records; any outreach lands in a shared inbox. Mitigation: `flag_duplicate_email` and `flag_shared_email` flags; confidence degraded.

## DQ-3 — MQL Date Overwrites
`mql_date` reflects the most recent qualification event, not the original. For converted leads, the mql_date may post-date the conversion. Effect: time-based analyses using mql_date are unreliable. Mitigation: mql_date is not used as a scoring input.

## DQ-4 — ETL-Dominated Timestamps
~80% of lead records and ~34% of contact records have `created_date = 2024-01-01` (the ETL load date). Effect: created_date cannot be used as a proxy for lead age or engagement window start. Mitigation: created_date is not used as a scoring input.

## DQ-5 — Score Field Asymmetry
Leads have `mkto_lead_score` (integer 0-100). Contacts have `mkto_contact_score_c` (float 0-100). Neither field name nor type is consistent. ~10% of records in both types have their score reset to zero (DQ-10). Effect: direct comparison across entity types is unreliable. Mitigation: neither Marketo score field is used as a scoring input.

## DQ-6 — Non-Prospect Contamination
~38% of records have a true_persona of Partner, Competitor, Employee, or Vendor. ~40% of records have a null job_persona. Effect: the queue includes non-buyers and unknowns. Mitigation: Competitor, Employee, and Vendor records receive a hard_blocker flag and the Flagged tier. Null job_persona is imputed at the within-entity-type median.

## DQ-7 — Completeness Gaps
~15% of records have no account linkage. ~12% have no title. ~18% have no phone. Some records have no industry. Effect: account fit and profile fit signals are partial for these records. Mitigation: missing signals default to conservative values; flags are set; confidence degrades.

## DQ-8 — Automation-Inflated Engagement
~30% of records have an automation_share > 70% — their campaign history is dominated by automated email sends. Effect: raw engagement counts overstate intent for these records. Mitigation: `member_status = Sent` events are excluded from the per-type engagement signal before scoring. Records with automation_share > 70% are additionally capped at the Follow Up tier.

## DQ-9 — Opted-Out / Bounced / No-Longer-With-Company
~22% opted out, ~10% bounced, ~8% no longer with company. Effect: outreach to opted-out records is a compliance risk; bounced emails are undeliverable; departed contacts cannot be reached at the known address. Mitigation: **these are soft flags, not hard blockers.** Opted-out and bounced records keep their scored tier; the BDR action note directs channel-specific handling (no email for opted-out, phone/LinkedIn for bounced). No-longer-with-company is treated as a hard blocker because the prospect relationship has ended entirely.

## DQ-10 — DQ Field Resets
~10% of both lead and contact Marketo score fields are zero. These zeros are indistinguishable from genuine low-score records. Effect: the Marketo score field cannot be trusted as a continuous signal. Mitigation: Marketo score fields are not used as scoring inputs.

## DQ-11 — Free-Email Leakage
~8% of records use free consumer email domains (Gmail, Yahoo, etc.). Of those, ~35% are not flagged in `free_email_known` — the domain reference table was incomplete at ETL time. Effect: corporate domain filtering misses some free-email users. Mitigation: `flag_free_email_leakage` is set where `actual_free_email = True` but `free_email_known = False`.
