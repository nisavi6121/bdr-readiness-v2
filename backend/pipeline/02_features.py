"""Stage 2: feature engineering.
Per-type engagement features with 30-day half-life decay.
Reads data/cleaned/ → writes data/features/
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent.parent
CLEANED = ROOT / "data" / "cleaned"
OUT = ROOT / "data" / "features"

TODAY = pd.Timestamp.today().normalize()
HALF_LIFE_DAYS = 30.0
DECAY_K = np.log(2) / HALF_LIFE_DAYS

# Per-type contribution weights (sum = 1.0)
TYPE_WEIGHTS = {
    "Event": 0.30,
    "Webinar": 0.25,
    "Content Syndication": 0.20,
    "Telemarketing": 0.10,
    "Email": 0.10,
    "Advertisement": 0.05,
}

# Per-type volume caps — genuine responses above cap get no additional credit
TYPE_CAPS = {
    "Event": 3,
    "Webinar": 5,
    "Content Syndication": 5,
    "Telemarketing": 5,
    "Email": 10,
    "Advertisement": 10,
}

ICP_INDUSTRIES = {"Software", "Financial Services", "Healthcare", "Telecommunications", "Energy"}

# Job level scoring
JOB_LEVEL_SCORES = {
    "C-Level": 1.00,
    "VP": 0.85,
    "Director": 0.70,
    "Manager": 0.50,
    "Individual Contributor": 0.30,
}
# Job persona scoring
JOB_PERSONA_SCORES = {
    "CISO": 1.00,
    "Technical Buyer": 0.85,
    "Financial Buyer": 0.70,
    "Influencer": 0.50,
    "Non-Prospect: Competitor": 0.00,
    "Non-Prospect: Partner": 0.00,
    "Non-Prospect: Employee": 0.00,
    "Non-Prospect: Vendor": 0.00,
    "Non-Prospect: Other": 0.00,
}


def _engagement_features(cm: pd.DataFrame) -> pd.DataFrame:
    cm = cm.copy()
    cm["response_date"] = pd.to_datetime(cm["response_date"])
    cm["age_days"] = (TODAY - cm["response_date"]).dt.days.clip(lower=0)
    cm["decay"] = np.exp(-DECAY_K * cm["age_days"])

    # Filter automation: only non-Sent counts as genuine signal
    cm["is_responded"] = cm["member_status"] != "Sent"
    genuine = cm[cm["is_responded"]].copy()

    rows = []
    for ctype, tw in TYPE_WEIGHTS.items():
        cap = TYPE_CAPS[ctype]
        sub = genuine[genuine["campaign_type"] == ctype]
        if sub.empty:
            continue
        grp = sub.groupby("scoring_person_id").agg(
            recency=("decay", "max"),
            volume=("campaign_member_id", "count"),
        )
        # recency_score 0-100, volume_score 0-100; multiplicative — both must be present
        recency_score = grp["recency"] * 100
        volume_score = (grp["volume"] / cap).clip(0, 1) * 100
        grp[f"eng_{ctype.lower().replace(' ', '_')}"] = tw * recency_score * volume_score
        rows.append(grp[[f"eng_{ctype.lower().replace(' ', '_')}"]])

    if rows:
        per_type = pd.concat(rows, axis=1).fillna(0)
    else:
        per_type = pd.DataFrame()

    # Overall aggregates (all records including automated)
    overall = cm.groupby("scoring_person_id").agg(
        engagement_count=("campaign_member_id", "count"),
        automation_events=("is_automated", "sum"),
        last_engagement_date=("response_date", "max"),
        first_engagement_date=("response_date", "min"),
    )
    overall["days_since_last_engagement"] = (TODAY - overall["last_engagement_date"]).dt.days.clip(lower=0)

    # Genuine-only aggregates for 30d/90d
    genuine_agg = genuine.groupby("scoring_person_id").agg(
        meaningful_count=("campaign_member_id", "count"),
        meaningful_30d=("age_days", lambda s: (s <= 30).sum()),
        meaningful_90d=("age_days", lambda s: (s <= 90).sum()),
    )

    # Automation share
    overall["sent_events"] = cm[cm["member_status"] == "Sent"].groupby("scoring_person_id").size()
    overall["sent_events"] = overall["sent_events"].fillna(0)
    overall["automation_share"] = np.where(
        overall["engagement_count"] > 0,
        overall["automation_events"] / overall["engagement_count"],
        0,
    )
    overall["automation_inflated_flag"] = overall["automation_share"] > 0.70

    result = overall.join(genuine_agg, how="left").fillna(0)
    if not per_type.empty:
        result = result.join(per_type, how="left").fillna(0)

    # Total engagement signal = sum of per-type contributions
    type_cols = [c for c in result.columns if c.startswith("eng_")]
    result["raw_engagement_signal"] = result[type_cols].sum(axis=1)
    return result.reset_index()


def _account_fit_features(people: pd.DataFrame) -> pd.DataFrame:
    people = people.copy()

    # For leads without account linkage, fall back to ZoomInfo enrichment fields
    zi_ind = people.get("zi_industry", pd.Series(dtype=str))
    zi_emp = people.get("zi_employee_count", pd.Series(dtype=object))
    industry_eff = people["industry"].fillna(zi_ind)
    emp_eff = pd.to_numeric(
        people["employee_count"].fillna(pd.to_numeric(zi_emp, errors="coerce")),
        errors="coerce",
    ).fillna(0)

    people["icp_flag"] = industry_eff.isin(ICP_INDUSTRIES)
    people["named_account_flag"] = people["named_account"].fillna(False)

    emp = emp_eff
    people["employee_fit"] = np.select(
        [emp.between(500, 10000), emp.between(100, 50000)],
        [1.0, 0.65],
        default=0.25,
    )

    # 6-segment framework — account data source quality only, no MQL status
    # Leads:    L1 (matched to CRM account), L2 (no match, enrichment available), L3 (no match, no enrichment)
    # Contacts: C1 (has lead origin), C2 (no lead origin, enrichment available), C3 (no lead origin, no enrichment)
    # Named account flag is already a sub-signal in account_fit_raw — excluded from segment to avoid double-counting
    def _segment(row):
        if row["entity_type"] == "Lead":
            if pd.notna(row.get("account_id")):
                return "L1"
            has_enrichment = (pd.notna(row.get("zi_industry")) or pd.notna(row.get("industry"))
                              or pd.notna(row.get("zi_employee_count")) or pd.notna(row.get("employee_count")))
            return "L2" if has_enrichment else "L3"
        else:  # Contact
            if pd.notna(row.get("lead_origin_id")):
                return "C1"
            has_enrichment = (bool(row.get("named_account_flag"))
                              or pd.notna(row.get("industry")) or pd.notna(row.get("employee_count")))
            return "C2" if has_enrichment else "C3"

    # Multipliers — reflect data source confidence, not prospect quality
    # Contacts get C1=1.00 because they are native CRM records linked to known accounts
    SEGMENT_MULTIPLIERS = {
        "L1": 0.90, "L2": 0.55, "L3": 0.45,
        "C1": 1.00, "C2": 0.55, "C3": 0.45,
    }

    people["segment"] = people.apply(_segment, axis=1)
    people["segment_multiplier"] = people["segment"].map(SEGMENT_MULTIPLIERS).fillna(0.35)

    # Raw account fit sub-signals (0-100 scale before multiplier)
    intent_raw = people.get("account_intent_score", pd.Series(0.0, index=people.index)).fillna(0).clip(0, 100)
    people["account_fit_raw"] = (
        people["icp_flag"].astype(float) * 50
        + people["named_account_flag"].astype(float) * 25
        + people["employee_fit"] * 15
        + (intent_raw / 100) * 10
    )
    people["account_fit_raw"] = people["account_fit_raw"].clip(0, 100)
    people["account_fit_signal"] = people["account_fit_raw"] * people["segment_multiplier"]
    return people[["record_id", "icp_flag", "named_account_flag", "employee_fit", "segment", "segment_multiplier", "account_fit_raw", "account_fit_signal"]]


def _profile_fit_features(people: pd.DataFrame) -> pd.DataFrame:
    """Cascading imputation within entity type on derived scores only (never on categories)."""
    people = people.copy()
    people["job_level_score_raw"] = people["job_level"].map(JOB_LEVEL_SCORES)
    people["job_persona_score_raw"] = people["job_persona"].map(JOB_PERSONA_SCORES)

    for etype in ["Lead", "Contact"]:
        mask = people["entity_type"] == etype
        subset = people.loc[mask]
        median_level = subset["job_level_score_raw"].median()
        median_persona = subset["job_persona_score_raw"].median()
        # Never use population mean; impute with within-entity-type median
        people.loc[mask, "job_level_score"] = subset["job_level_score_raw"].fillna(median_level if pd.notna(median_level) else 0.30)
        people.loc[mask, "job_persona_score"] = subset["job_persona_score_raw"].fillna(median_persona if pd.notna(median_persona) else 0.30)

    people["profile_fit_signal"] = (people["job_level_score"] + people["job_persona_score"]) / 2
    return people[["record_id", "job_level_score", "job_persona_score", "profile_fit_signal"]]


def build_features(people: pd.DataFrame, cm: pd.DataFrame) -> pd.DataFrame:
    eng = _engagement_features(cm)
    acc = _account_fit_features(people)
    prof = _profile_fit_features(people)

    features = people.merge(eng, on="scoring_person_id", how="left")
    # Fill engagement zeros for people with no campaign history
    eng_cols = [c for c in eng.columns if c not in ["scoring_person_id"]]
    for col in eng_cols:
        if col in features.columns and features[col].dtype != object:
            features[col] = features[col].fillna(0)

    features = features.merge(acc, on="record_id", how="left")
    features = features.merge(prof, on="record_id", how="left")

    return features


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    people = pd.read_csv(CLEANED / "people.csv")
    cm = pd.read_csv(CLEANED / "campaign_members.csv")
    features = build_features(people, cm)
    features.to_csv(OUT / "features.csv", index=False)
    print(f"Features: {len(features):,} rows, {len(features.columns)} columns")


if __name__ == "__main__":
    main()
