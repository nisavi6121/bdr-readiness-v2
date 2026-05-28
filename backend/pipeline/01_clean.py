"""Stage 1: entity cleaning, flag computation, DQ tagging.
Reads data/raw/*.csv → writes data/cleaned/people.csv + campaign_members.csv
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "cleaned"


def _load_raw() -> dict[str, pd.DataFrame]:
    return {
        "accounts": pd.read_csv(RAW / "accounts.csv"),
        "campaigns": pd.read_csv(RAW / "campaigns.csv"),
        "leads": pd.read_csv(RAW / "leads.csv"),
        "contacts": pd.read_csv(RAW / "contacts.csv"),
        "campaign_members": pd.read_csv(RAW / "campaign_members.csv"),
    }


def _normalize_leads(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={"lead_id": "record_id"})
    df["entity_type"] = "Lead"
    df["is_converted"] = df["is_converted"].fillna(False)
    df["no_longer_with_company"] = df["no_longer_with_company"].fillna(False)
    if "is_current_mql" not in df.columns:
        df["is_current_mql"] = df.get("lead_status", pd.Series(index=df.index)).eq("MQL")
    return df


def _normalize_contacts(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={
        "contact_id": "record_id",
        "is_mql": "is_current_mql",
        "primary_lead_id": "lead_origin_id",
    })
    df["entity_type"] = "Contact"
    df["no_longer_with_company"] = False
    df["is_converted"] = df.get("is_converted", pd.Series(False, index=df.index))
    return df


def _normalize_accounts(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns={
        "is_named_account": "named_account",
        "intent_score": "account_intent_score",
        "account_do_not_contact": "account_do_not_contact",  # keep as-is
    })


def build_people(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    leads = _normalize_leads(frames["leads"].copy())
    contacts = _normalize_contacts(frames["contacts"].copy())
    accounts = _normalize_accounts(frames["accounts"].copy())

    leads["lineage_type"] = leads.apply(
        lambda r: "Converted Lead - linked" if bool(r.get("is_converted")) and pd.notna(r.get("converted_contact_id"))
        else "Converted Lead - broken link" if bool(r.get("is_converted"))
        else "Orphan Lead",
        axis=1,
    )
    contacts["lineage_type"] = contacts.get("lead_origin_id", pd.Series(index=contacts.index)).notna().map(
        {True: "Converted Contact", False: "Orphan Contact"}
    )

    people = pd.concat([leads, contacts], ignore_index=True, sort=False)

    # Scoring person id: map converted lead → its contact for engagement merge
    linked = people.loc[people["converted_contact_id"].notna(), ["record_id", "converted_contact_id"]]
    lead_to_contact = dict(zip(linked["record_id"], linked["converted_contact_id"]))
    people["scoring_person_id"] = people["record_id"].map(lead_to_contact).fillna(people["record_id"])

    # Merge accounts
    people = people.merge(accounts, on="account_id", how="left", suffixes=("", "_acct"))
    # Prefer person-level industry/employee_count; fall back to account
    for col in ["industry", "employee_count"]:
        acct_col = col + "_acct"
        if acct_col in people.columns:
            people[col] = people[col].fillna(people[acct_col])
            people.drop(columns=[acct_col], inplace=True)

    # --- DQ flags ---
    email_counts = people.groupby("email")["record_id"].transform("count")
    people["flag_duplicate_email"] = email_counts > 1
    people["flag_shared_email"] = people["email"].str.startswith(("info@", "sales@", "security@"), na=False) | (email_counts >= 8)
    people["flag_broken_conversion_link"] = (
        (people["entity_type"] == "Lead")
        & people["is_converted"].fillna(False)
        & people["converted_contact_id"].isna()
    )
    people["flag_orphan_contact"] = (
        (people["entity_type"] == "Contact")
        & people.get("lead_origin_id", pd.Series(index=people.index)).isna()
    )
    people["flag_opted_out"] = people["email_opt_out"].fillna(False)
    people["flag_email_bounced"] = people["email_bounced"].fillna(False)
    people["flag_no_longer_with_company"] = people["no_longer_with_company"].fillna(False)
    people["flag_non_prospect"] = people["job_persona"].str.startswith("Non-Prospect", na=False)
    people["flag_do_not_contact"] = people["account_do_not_contact"].fillna(False)
    people["flag_free_email_leakage"] = people["actual_free_email"].fillna(False) & ~people["free_email_known"].fillna(False)
    people["flag_missing_account"] = people["account_id"].isna()
    people["flag_missing_title"] = people["title"].isna()
    people["flag_missing_phone"] = people["phone"].isna()
    people["flag_missing_industry"] = people["industry"].isna()

    # Hard blockers: only structurally uncallable records per methodology
    # opted_out and email_bounced are soft flags — score preserved, BDR decides
    people["hard_blocker"] = (
        people["flag_non_prospect"]
        | people["flag_do_not_contact"]
        | people["flag_no_longer_with_company"]
    )
    people["hard_blocker_reasons"] = people.apply(_hard_blocker_reasons, axis=1)

    dq_flag_cols = [
        "flag_duplicate_email", "flag_shared_email", "flag_broken_conversion_link",
        "flag_orphan_contact", "flag_free_email_leakage", "flag_missing_account",
        "flag_missing_title", "flag_missing_phone", "flag_missing_industry",
    ]
    people["dq_flag_count"] = people[dq_flag_cols].fillna(False).sum(axis=1).astype(int)
    people["dq_flags"] = people[dq_flag_cols].apply(
        lambda row: ", ".join(c.replace("flag_", "") for c, v in row.items() if bool(v)), axis=1
    )

    return people


def _hard_blocker_reasons(row: pd.Series) -> str:
    reasons = []
    if bool(row.get("flag_no_longer_with_company")):
        reasons.append("no longer with company")
    if bool(row.get("flag_do_not_contact")):
        reasons.append("account do-not-contact")
    if bool(row.get("flag_non_prospect")):
        reasons.append("non-prospect persona")
    return ", ".join(reasons)


def attach_engagement_links(people: pd.DataFrame, campaign_members: pd.DataFrame) -> pd.DataFrame:
    cm = campaign_members.rename(columns={"cm_id": "campaign_member_id", "entity_id": "person_record_id"})
    id_map = people.set_index("record_id")["scoring_person_id"].to_dict()
    cm["scoring_person_id"] = cm["person_record_id"].map(id_map).fillna(cm["person_record_id"])
    # Ensure is_responded is present (fallback if generator predates this field)
    if "is_responded" not in cm.columns:
        cm["is_responded"] = cm["member_status"] != "Sent"
    return cm


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    frames = _load_raw()
    people = build_people(frames)
    cm = attach_engagement_links(people, frames["campaign_members"])
    people.to_csv(OUT / "people.csv", index=False)
    cm.to_csv(OUT / "campaign_members.csv", index=False)
    print(f"Cleaned: {len(people):,} people, {len(cm):,} campaign member rows")
    print(f"Hard blockers: {people['hard_blocker'].sum():,}")
    print(f"DQ flag totals: {people['dq_flag_count'].sum():,}")


if __name__ == "__main__":
    main()
