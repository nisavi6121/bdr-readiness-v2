# BDR Readiness Score

A Flask/Jinja2 BDR prioritisation tool: four-stage scoring pipeline + live web app.

**Scoring model — differentiated by entity type:**
- Leads: `Final Score = 0.75 × Engagement + 0.15 × Account Fit + 0.10 × Profile Fit`
- Contacts: `Final Score = 0.60 × Engagement + 0.25 × Account Fit + 0.15 × Profile Fit`

## Prerequisites

- Python 3.10+

## Quick Start (local dev)

```powershell
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Run the data pipeline (generates + scores 1 000 records)
python generation\generate.py
python backend\pipeline\01_clean.py
python backend\pipeline\02_features.py
python backend\pipeline\03_score.py
python backend\pipeline\04_rank.py

# 3. Start the web app
python app.py
# Open http://localhost:5000
```

## Routes (http://localhost:5000)

| Route | Description |
|---|---|
| `/` | Redirect to `/queue` |
| `/queue` | Paginated, filterable BDR priority queue |
| `/record/<id>` | Full record detail + score breakdown |
| `/methodology` | Scoring methodology explained |
| `/knowledge-base` | Analyst discovery notes and design decisions |

## Project Structure

```
bdr_readiness_score/
├── generation/
│   └── generate.py          # Synthetic SFDC-style data (SEED=42)
├── backend/
│   └── pipeline/
│       ├── 01_clean.py      # Entity resolution + DQ flags
│       ├── 02_features.py   # Per-type engagement features + fit signals
│       ├── 03_score.py      # 3-component scoring
│       └── 04_rank.py       # Tier assignment + BDR actions
├── templates/               # Jinja2 HTML (base, queue, record, methodology, kb)
├── knowledge_base/          # Markdown docs (design, issues, lessons, discovery)
├── app.py                   # Flask application entry point
├── data/
│   ├── raw/                 # Generated CSVs
│   ├── cleaned/             # After 01_clean
│   ├── features/            # After 02_features
│   └── scored/              # ranked_records.csv (final output)
├── vercel.json
└── requirements.txt
```

## Scoring Model

### Engagement (leads 75%, contacts 60%)
Per campaign type (Event 30%, Webinar 25%, Content Syndication 20%, Telemarketing 10%, Email 10%, Ad 5%).
Decay: `exp(−ln(2)/30 × age_days)` (30-day half-life).
Volume: `count / type_cap` (capped per type, not log).
Automation filter: `Sent` status events excluded from genuine signal.
Normalised within entity type using **95th-percentile ceiling** — outliers do not compress the rest.

### Account Fit (leads 15%, contacts 25%)
Sub-signals: ICP Industry (30 pts), Named Account (25 pts), Industry overlap (20 pts), Employee Count (15 pts), Intent Score (10 pts).
Multiplied by a segment confidence factor based on **account data source quality**:

| Segment | Condition | Multiplier |
|---|---|---|
| L1 | Lead matched to account | 0.90 |
| L2 | No account match; both ZI industry + ZI emp enrichment | 0.65 |
| L3 | No account match; industry enrichment only | 0.55 |
| L4 | No account match; emp enrichment only | 0.60 |
| L5 | No account match; no enrichment | 0.45 |
| C1 | Contact with lead origin + named account | 1.00 |
| C2 | Contact with lead origin | 0.85 |
| C3 | Named account, no lead origin | 0.55 |
| C4 | No lead origin, no named account | 0.30 |

### Profile Fit (leads 10%, contacts 15%)
`(job_level_score + job_persona_score) / 2`
Job level: C-Level 1.00 · VP 0.85 · Director 0.70 · Manager 0.50 · IC 0.30
Job persona: CISO 1.00 · Technical Buyer 0.85 · Financial Buyer 0.70 · Influencer 0.50 · Non-Prospect 0.00
Missing values imputed with within-entity-type median (never population mean).

### Tiers

| Tier | Lead threshold | Contact threshold | Action |
|---|---|---|---|
| Call Now | ≥ 65 | ≥ 70 | Priority outreach within 24h |
| Follow Up | ≥ 35 | ≥ 40 | Schedule within 5 business days |
| Nurture | < 35 | < 40 | Long-term sequence |
| Flagged | hard blocker | hard blocker | Review before any outreach |

Automation-inflated records (automation_share > 70%) are capped at Follow Up regardless of score.

### Hard Blockers (Flagged tier)
- Non-Prospect persona (Competitor, Employee, Vendor)
- Account-level do-not-contact
- No-longer-with-company

### Soft Flags (do not block tier, inform BDR action)
- Email opted-out → no email channel; call or event outreach only
- Bounced email → use phone or LinkedIn

## Vercel Deployment

The app deploys to Vercel via `@vercel/python`. `ranked_records.csv` and `campaign_members.csv` are pre-committed so no pipeline runs at deploy time.

```bash
vercel --prod
```
