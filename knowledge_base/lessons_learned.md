# Lessons Learned

The hardest part of this problem is not the arithmetic. It is deciding which imperfections should change readiness, which should change confidence, and which should block action entirely.

## Score vs Confidence vs Blocker

Three distinct signals need to stay separate:

- **Score**: how ready is this person to take a call, based on observable behaviour and fit?
- **Confidence**: how much should we trust the score, given data quality issues?
- **Blocker**: is outreach currently possible or legal?

Mixing these into a single number produces a score that means different things for different records and cannot be acted on without back-calculation. Keeping them separate lets BDRs prioritise by score while seeing the confidence caveat and the blocker reason independently.

## The ETL Date Problem

DQ-4 (80% of leads share a single created_date) is not a simulation artefact — it mirrors a real pattern seen in CRM data where batch ETL loads overwrite the original creation timestamp. Any feature that uses created_date as a proxy for lead age, funnel stage, or engagement window start is silently broken for 80% of leads. This motivated the decision to use engagement recency exclusively, rather than created_date, as the freshness signal.

## Automation vs Intent

DQ-8 is subtle because a BDR looking at a record with 50 campaign membership rows might initially infer high engagement. The per-type engagement model with the Sent-status exclusion filter makes this transparent: a record with 50 automated email sends scores the same as a record with zero sends. The automation_inflated_flag surfaces the pattern without double-penalising it.

## Lead/Contact Normalisation is Non-Negotiable

Without entity-type normalisation, contacts would dominate the Call Now tier not because they are better prospects, but because they accumulate more campaign history. Normalising within entity type before weighting means the top-ranked Lead is ranked against other Leads, not against Contacts with 3x the engagement history.

95th-percentile ceiling normalisation was chosen over min-max because engagement data is right-skewed. Min-max would compress the entire middle of the distribution whenever a handful of highly-active outliers exist. The 95th-percentile ceiling treats the top 5% as the reference point (score = 100) and scales everything else proportionally — outliers still score 100, but they no longer collapse the rest of the distribution.

## Missing Data is Not Disqualification

The instinct to penalise missing data inside the score is wrong for two reasons: (1) the record holder did not choose to have incomplete data — the CRM process failed; (2) penalising it inside the score makes the score uninterpretable. A missing phone number tells you nothing about whether this person wants to buy. The DQ flag and confidence degradation are the right signals. The score should reflect what we know, not punish what we don't.

## Segment Multipliers Encode Trust, Not Value

The 9-segment multipliers do not mean a C4 contact is a worse prospect than a C1 contact. They mean the account fit signal for a C4 contact is less trustworthy — we have less data to verify the account relationship. The multiplier scales confidence in the account fit sub-score, not the intrinsic worth of the person.
