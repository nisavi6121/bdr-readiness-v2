"""Stage 4: ranking and tier assignment.
Tiers: Tier 1 (≥70, Call Now), Tier 2 (40-69, Follow Up), Tier 3 (<40, Nurture), Flagged (hard blocker).
Reads data/scored/ → writes data/scored/ranked_records.csv
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent.parent
SCORED = ROOT / "data" / "scored"
OUT = ROOT / "data" / "scored"

TIER_ORDER = {"Call Now": 0, "Follow Up": 1, "Nurture": 2, "Flagged": 3}


def assign_tiers(scored: pd.DataFrame) -> pd.DataFrame:
    df = scored.copy()

    # Differentiated thresholds per entity type — leads score structurally lower
    lead_mask = df["entity_type"] == "Lead"
    call_now = (lead_mask & (df["final_score"] >= 65)) | (~lead_mask & (df["final_score"] >= 70))
    follow_up = (lead_mask & (df["final_score"] >= 35)) | (~lead_mask & (df["final_score"] >= 40))

    df["tier"] = np.select(
        [df["hard_blocker"].fillna(False), call_now, follow_up],
        ["Flagged", "Call Now", "Follow Up"],
        default="Nurture",
    )

    # Automation-inflated records capped at Follow Up — engagement signal unreliable for Call Now
    auto_cap = df["automation_inflated_flag"].fillna(False) & (df["tier"] == "Call Now")
    df.loc[auto_cap, "tier"] = "Follow Up"

    df["tier_sort"] = df["tier"].map(TIER_ORDER)
    df = df.sort_values(["tier_sort", "final_score"], ascending=[True, False])

    # Soft flags — opted_out and email_bounced do not block tier but inform BDR action
    non_email_eng_cols = [c for c in df.columns if c.startswith("eng_") and "email" not in c]
    has_non_email_signal = df[non_email_eng_cols].sum(axis=1) > 0 if non_email_eng_cols else pd.Series(False, index=df.index)
    opted_out_engaged = df["flag_opted_out"].fillna(False) & has_non_email_signal
    bounced_only = df["flag_email_bounced"].fillna(False) & ~df["flag_opted_out"].fillna(False)

    # BDR action column
    df["bdr_action"] = np.select(
        [
            df["tier"] == "Flagged",
            opted_out_engaged & (df["tier"] == "Call Now"),
            opted_out_engaged & (df["tier"] == "Follow Up"),
            bounced_only,
            df["tier"] == "Call Now",
            df["tier"] == "Follow Up",
        ],
        [
            "Review blocker: " + df["hard_blocker_reasons"].fillna(""),
            "Do not email — call or engage at event only (opted out, non-email signal present)",
            "Do not email — schedule call or event outreach (opted out, non-email signal present)",
            "Email undeliverable — use phone or LinkedIn only",
            "Priority outreach — call or email within 24h",
            "Schedule follow-up within 5 business days",
        ],
        default="Add to long-term nurture sequence",
    )

    # Append soft flag notes to bdr_action for all non-blocked records
    df["bdr_action"] = df.apply(_append_soft_notes, axis=1)

    # Converted leads with a linked contact — suppress from active outreach.
    # The contact is the canonical record; actioning the lead would duplicate effort.
    converted_linked = (
        (df["entity_type"] == "Lead")
        & df["is_converted"].fillna(False)
        & df["converted_contact_id"].notna()
    )
    df["is_suppressed"] = converted_linked
    df.loc[converted_linked, "bdr_action"] = (
        "Do not action — record converted to contact "
        + df.loc[converted_linked, "converted_contact_id"].astype(str)
        + " (work the contact record instead)"
    )

    # Contact tier promotion — higher tier between lead and contact prevails.
    # Hard blocker on the contact always supersedes.
    df = _promote_contacts(df)

    # Re-sort after potential tier changes
    df["tier_sort"] = df["tier"].map(TIER_ORDER)
    df = df.sort_values(["tier_sort", "final_score"], ascending=[True, False])

    # Action tag — short label for queue badge and filter
    df["action_tag"] = df["bdr_action"].apply(_action_tag)

    return df


def _promote_contacts(df: pd.DataFrame) -> pd.DataFrame:
    TIER_PRIORITY = {"Call Now": 0, "Follow Up": 1, "Nurture": 2, "Flagged": 3}
    sup_leads = df[df["is_suppressed"]][["record_id", "converted_contact_id", "tier"]].copy()
    snap = df.set_index("record_id", drop=False)  # snapshot before mutations

    for _, lead_row in sup_leads.iterrows():
        cid = lead_row["converted_contact_id"]
        if pd.isna(cid) or cid not in snap.index:
            continue
        contact = snap.loc[cid]
        if bool(contact["hard_blocker"]):
            continue  # blocker always supersedes
        lead_tier = lead_row["tier"]
        contact_tier = str(contact["tier"])
        if TIER_PRIORITY.get(lead_tier, 3) >= TIER_PRIORITY.get(contact_tier, 3):
            continue  # contact already equal or higher priority

        mask = df["record_id"] == cid
        df.loc[mask, "tier"] = lead_tier

        # Rebuild base action for new tier, respecting soft flags
        is_opted_out = bool(df.loc[mask, "flag_opted_out"].iloc[0])
        if lead_tier == "Call Now":
            base = ("Do not email — call or engage at event only (opted out, non-email signal present)"
                    if is_opted_out else "Priority outreach — call or email within 24h")
        else:
            base = ("Do not email — schedule call or event outreach (opted out, non-email signal present)"
                    if is_opted_out else "Schedule follow-up within 5 business days")

        existing = str(df.loc[mask, "bdr_action"].iloc[0])
        notes = (" | Note:" + existing.split(" | Note:", 1)[1]) if " | Note:" in existing else ""
        df.loc[mask, "bdr_action"] = (
            base
            + f" | Promoted from {contact_tier} — linked lead {lead_row['record_id']} scored {lead_tier}"
            + notes
        )

    return df


def _action_tag(action: str) -> str:
    a = str(action)
    if a.startswith("Do not action"):
        return "Converted"
    if a.startswith("Review blocker"):
        return "Blocked"
    if a.startswith("Priority outreach"):
        return "Call / Email"
    if a.startswith("Do not email — call"):
        return "Call only"
    if a.startswith("Do not email — schedule"):
        return "Follow Up"
    if a.startswith("Email undeliverable"):
        return "Phone / LinkedIn"
    if a.startswith("Schedule follow-up"):
        return "Follow Up"
    if a.startswith("Add to long-term"):
        return "Nurture"
    return "—"


def _append_soft_notes(row: pd.Series) -> str:
    notes = []
    if bool(row.get("flag_opted_out")) and not bool(row.get("hard_blocker")):
        notes.append("opted out — no email")
    if bool(row.get("flag_email_bounced")) and not bool(row.get("hard_blocker")):
        notes.append("email bounced — use phone/LinkedIn")
    if bool(row.get("flag_broken_conversion_link")):
        notes.append("broken conversion link (DQ-1)")
    if bool(row.get("automation_inflated_flag")) and not bool(row.get("hard_blocker")):
        notes.append("engagement may be automation-inflated")
    if notes:
        return str(row["bdr_action"]) + " | Note: " + "; ".join(notes)
    return str(row["bdr_action"])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    scored = pd.read_csv(SCORED / "scored.csv")
    ranked = assign_tiers(scored)
    ranked.to_csv(OUT / "ranked_records.csv", index=False)
    print(f"Ranked {len(ranked):,} records")
    print(ranked["tier"].value_counts().to_string())
    print(f"\nTop 10:")
    top_cols = ["record_id", "entity_type", "tier", "final_score", "confidence", "first_name", "last_name", "account_name"]
    available = [c for c in top_cols if c in ranked.columns]
    print(ranked[available].head(10).to_string(index=False))


if __name__ == "__main__":
    main()
