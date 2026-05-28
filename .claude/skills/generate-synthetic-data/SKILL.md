---
name: generate-synthetic-data
description: >-
  Used to (re)generate or change the synthetic SFDC dataset for the BDR readiness
  project (accounts, campaigns, leads, contacts, campaign_members) with the
  embedded data-quality issues and the guaranteed stress-test personas. Reach for
  this when regenerating the raw data, changing record counts or DQ rates, adding
  a new field or DQ issue, or figuring out why a persona stopped showing up. The
  generator is generation/generate.py and it writes CSVs into data/raw/.
---

# Generating the synthetic data

Notes for working with `generation/generate.py`. It builds the whole fake SFDC
dataset (accounts, campaigns, leads, contacts, campaign members) and dumps the
CSVs into `data/raw/`. Worth reading before you touch the generator, because the
reproducibility breaks quietly if you get the seeding wrong.

## Things not to break

**Seeding.** Everything runs off `SEED = 42` and
`RNG = np.random.default_rng(SEED)`. There's a second generator,
`NEW_FIELDS_RNG = default_rng(SEED + 1000)`, and the only reason it exists is so
I could add new columns later without shifting the original random stream. So if
you need a new field, draw it from `NEW_FIELDS_RNG`. Don't add draws into the
main `RNG`, or every record after that point changes and the dataset is no longer
reproducible.

**Re-verify every time.** After any change: regenerate, run the four pipeline
stages, then `verify_personas.py`. I don't treat a change as done until all 10
personas land in the tiers they're meant to.

**Keep the distributions correlated.** Engagement volume is tied to account
quality and persona on purpose (more on that below). It's tempting to simplify
the weighting into plain uniform draws, but that kills the realism the model is
supposed to be handling in the first place.

## Expected record counts of the generated dataset

- 200 accounts
- 60 campaigns (40 old, 15 from 2025, 5 in the last ~60 days)
- 600 leads, 400 contacts
- 200 of the leads are converted into contacts (the connected pairs)
- ~5,000 campaign member rows

The brief asks for at least 1,000 people, 3–5k campaign members, 150–250
accounts and 8+ DQ issues, so this clears it with room to spare.

## The DQ issues I baked in

The rates below are tuned, not arbitrary. Each one is meant to give the scoring
model something real to deal with, so keep them roughly where they are.

- **DQ-1, broken conversion links.** 20% of the 200 converted leads have
  `is_converted=True` but a null `converted_contact_id`.
- **DQ-2, duplicate emails.** ~5% plain person-to-person dupes, plus shared
  mailboxes (`info@`, `sales@`, …) with 4–8 records each, plus a couple of
  high-cardinality spam clusters (10–14 records on one address, separate ones for
  leads and contacts). Shared-mailbox campaign members get cloned across everyone
  on that inbox, so one fake open inflates all of them.
- **DQ-3, mql_date overwrites.** Converted leads that were MQL get `mql_date`
  rewritten to conversion time instead of the first MQL.
- **DQ-4, ETL created_date.** 80% of leads and 35% of contacts get the flat
  `2024-01-01` load date instead of a real entry date.
- **DQ-5, score asymmetry.** Leads carry `mkto_lead_score` (int), contacts carry
  `mkto_contact_score_c` (float). Different fields on purpose, so you can't just
  concatenate the two.
- **DQ-6, non-prospect contamination.** `job_persona` is ~40% null, and about
  half of the rest are Non-Prospect types (competitor/partner/employee/vendor/
  other).
- **DQ-7, missing data.** ~15% no account, ~15% null job level, ~12% null title,
  ~18% null phone.
- **DQ-8, automation inflation.** 30% of the people who engage are inflated,
  ~82% of their campaign members are just `Sent`, and ~5% get a 40–45 event burst
  (that's persona 8).
- **DQ-9, opted-out / bounced / gone.** 22% / 10% / 8%, which lands around 35% of
  the database combined.
- **DQ-10, re-MQL resets.** 10% of the marketo scores reset to 0,
  `mql_cycle_count` tracks how many times someone re-MQL'd (1–4), and
  `dq_reason`/`dq_date` get cleared on re-MQL so the history is lost.
- **DQ-11, free-email leakage.** 8% are actually on free email, but
  `free_email_known` misses about a third of them because the reference list is
  incomplete.

I left DQ-12 (stale curated views) out on purpose. It didn't give the model
anything to act on, so it wasn't worth the effort.

## Why engagement isn't uniform

In `generate_campaign_members`, who engages and how much is weighted:

- Account quality: ICP industry ×2, named account ×2.5, and intent score scales
  it from 0.5× to 1.5×. No account linkage at all drops you to 0.5×.
- Persona: real prospects get weighted up (2.5× for leads, 3.5× for contacts),
  nulls and non-prospects down to 0.8×.
- Better accounts also get more events per person, not just more people engaging.
- Senior real prospects and active ICs get pushed toward the 5 recent 2026
  campaigns. That's what actually makes personas 1 and 3 read as recently active.

## Forcing the hard personas to exist

`_inject_persona_guarantees` makes sure the two trickiest archetypes always show
up. It injects recent genuine events, and if there's no natural candidate it
promotes the closest match:

- P1: VP or C-level, real prospect persona, named ICP account, MQL.
- P10: orphan contact (no lead origin) on a high-intent named ICP account.

If you change the counts or weights and a persona disappears from
`verify_personas.py`, this is the first place I'd look.

## Running it

```powershell
python generation\generate.py
python backend\pipeline\01_clean.py
python backend\pipeline\02_features.py
python backend\pipeline\03_score.py
python backend\pipeline\04_rank.py
python verify_personas.py
```

## Easy ways to break it

- Adding a field through the main `RNG` instead of `NEW_FIELDS_RNG`.
- Changing a DQ rate and forgetting to re-run `verify_personas.py`.
- Flattening the engagement weighting into uniform draws.
- Committing a fresh `data/raw/` without checking the printed counts still line up
  with the numbers above.
