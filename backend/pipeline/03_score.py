"""Stage 3: 3-component scoring.
Final Score = 0.60 × engagement_score + 0.22 × account_fit_score + 0.18 × profile_fit_score
All component scores normalized to 0-100 within entity type before weighting.
Reads data/features/ → writes data/scored/
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent.parent
FEATURES = ROOT / "data" / "features"
OUT = ROOT / "data" / "scored"

# Differentiated weights per entity type per methodology doc
LEAD_WEIGHTS = {"engagement": 0.75, "account_fit": 0.15, "profile_fit": 0.10}
CONTACT_WEIGHTS = {"engagement": 0.60, "account_fit": 0.25, "profile_fit": 0.15}


def _normalize_engagement_95p(df: pd.DataFrame) -> pd.DataFrame:
    """95th-percentile ceiling normalization within entity type.
    Prevents outliers from compressing everyone else. Floor stays at 0."""
    df = df.copy()
    df["engagement_score"] = 0.0
    for etype in df["entity_type"].unique():
        mask = df["entity_type"] == etype
        vals = df.loc[mask, "raw_engagement_signal"]
        ceiling = vals.quantile(0.95)
        if ceiling > 0:
            df.loc[mask, "engagement_score"] = (vals / ceiling).clip(0, 1) * 100
        else:
            df.loc[mask, "engagement_score"] = 0.0
    return df


def score(features: pd.DataFrame) -> pd.DataFrame:
    scored = features.copy()

    # --- Engagement score (0-100) ---
    # 95th-percentile normalization within entity type
    raw_eng = scored.get("raw_engagement_signal", pd.Series(0.0, index=scored.index)).fillna(0)
    scored["raw_engagement_signal"] = raw_eng
    scored = _normalize_engagement_95p(scored)

    # --- Account fit score (0-100) ---
    # account_fit_signal already 0-100 scale (raw × multiplier)
    raw_acc = scored.get("account_fit_signal", pd.Series(0.0, index=scored.index)).fillna(0)
    scored["account_fit_score"] = raw_acc.clip(0, 100).round(1)

    # --- Profile fit score (0-100) ---
    # profile_fit_signal is 0-1; scale to 0-100
    raw_prof = scored.get("profile_fit_signal", pd.Series(0.0, index=scored.index)).fillna(0)
    scored["profile_fit_score"] = (raw_prof * 100).clip(0, 100).round(1)

    # --- Non-prospect override: zero account fit and profile fit ---
    # These records are hard-blocked anyway; zeroing scores makes the model internally consistent.
    np_mask = scored.get("job_persona", pd.Series("", index=scored.index)).str.startswith("Non-Prospect", na=False)
    scored.loc[np_mask, "account_fit_score"] = 0.0
    scored.loc[np_mask, "profile_fit_score"] = 0.0

    # --- Final weighted score — differentiated by entity type ---
    lead_mask = scored["entity_type"] == "Lead"
    scored["final_score"] = np.where(
        lead_mask,
        scored["engagement_score"] * LEAD_WEIGHTS["engagement"]
        + scored["account_fit_score"] * LEAD_WEIGHTS["account_fit"]
        + scored["profile_fit_score"] * LEAD_WEIGHTS["profile_fit"],
        scored["engagement_score"] * CONTACT_WEIGHTS["engagement"]
        + scored["account_fit_score"] * CONTACT_WEIGHTS["account_fit"]
        + scored["profile_fit_score"] * CONTACT_WEIGHTS["profile_fit"],
    )
    scored["final_score"] = scored["final_score"].clip(0, 100).round(1)

    # Store weights used per record for transparency
    scored["engagement_weight"] = np.where(lead_mask, LEAD_WEIGHTS["engagement"], CONTACT_WEIGHTS["engagement"])
    scored["account_fit_weight"] = np.where(lead_mask, LEAD_WEIGHTS["account_fit"], CONTACT_WEIGHTS["account_fit"])
    scored["profile_fit_weight"] = np.where(lead_mask, LEAD_WEIGHTS["profile_fit"], CONTACT_WEIGHTS["profile_fit"])

    # --- Data confidence ---
    scored["confidence"] = np.select(
        [scored["dq_flag_count"] <= 1, scored["dq_flag_count"] <= 3],
        ["High", "Medium"],
        default="Low",
    )

    # --- Score explanation ---
    scored["score_explanation"] = scored.apply(_explain, axis=1)

    return scored


def _explain(row: pd.Series) -> str:
    parts = []
    if row.get("meaningful_30d", 0) >= 2:
        parts.append(f"{int(row['meaningful_30d'])} meaningful engagements in last 30d")
    elif pd.notna(row.get("days_since_last_engagement")) and row["days_since_last_engagement"] > 0:
        parts.append(f"last engaged {int(row['days_since_last_engagement'])}d ago")
    else:
        parts.append("no engagement history")
    if row.get("icp_flag"):
        parts.append(f"ICP industry ({row.get('industry', '')})")
    if row.get("named_account_flag"):
        parts.append("named account")
    if row.get("automation_inflated_flag"):
        parts.append("engagement discounted (automation-heavy)")
    seg = row.get("segment", "")
    if seg:
        parts.append(f"segment {seg}")
    return "; ".join(parts)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    features = pd.read_csv(FEATURES / "features.csv")
    scored = score(features)
    scored.to_csv(OUT / "scored.csv", index=False)
    print(f"Scored {len(scored):,} records")
    score_cols = ["engagement_score", "account_fit_score", "profile_fit_score", "final_score"]
    print(scored[score_cols].describe().round(1).to_string())


if __name__ == "__main__":
    main()
