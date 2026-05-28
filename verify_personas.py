import pandas as pd

today = pd.Timestamp("2026-05-20")
df = pd.read_csv("data/scored/ranked_records.csv")
cm = pd.read_csv("data/cleaned/campaign_members.csv")
leads = pd.read_csv("data/raw/leads.csv")
cm["response_date"] = pd.to_datetime(cm["response_date"])
recent_cm = cm[cm["response_date"] >= today - pd.Timedelta(days=90)]
recent_genuine = recent_cm[recent_cm["member_status"] != "Sent"]


def show(num, label, subset, sort_col="final_score"):
    if len(subset) == 0:
        print(f"P{num} {label}: NO MATCH\n")
        return
    r = subset.sort_values(sort_col, ascending=False).iloc[0]
    jl = str(r.get("job_level", "?"))
    jp = str(r.get("job_persona", "?"))
    print(f"P{num} {label}")
    print(f"  {r['record_id']} | {r['entity_type']} | {jl} | {jp}")
    print(f"  Tier:{r['tier']}  Score:{r['final_score']}  eng:{r['engagement_score']:.1f}  acc:{r['account_fit_score']:.1f}  prof:{r['profile_fit_score']:.1f}")
    print(f"  Action: {str(r['bdr_action'])[:110]}")
    print()


rg_ids = set(recent_genuine["scoring_person_id"].unique())

p1 = df[
    df["job_level"].isin(["VP", "C-Level"])
    & df["named_account_flag"].fillna(False)
    & df["icp_flag"].fillna(False)
    & df["is_current_mql"].fillna(False)
    & ~df["hard_blocker"].fillna(False)
    & df["scoring_person_id"].isin(rg_ids)
]
show(1, "VP/CL named ICP recent MQL (expect: Call Now)", p1)

p2 = df[
    df["job_level"].isin(["VP", "C-Level"])
    & df["icp_flag"].fillna(False)
    & (df["engagement_score"] < 5)
    & ~df["hard_blocker"].fillna(False)
]
show(2, "VP/CL ICP stale (expect: Nurture)", p2, "account_fit_score")

p3_ids = set(recent_genuine.groupby("scoring_person_id").size()[lambda x: x >= 3].index)
p3 = df[
    (df["job_level"] == "Individual Contributor")
    & ~df["hard_blocker"].fillna(False)
    & df["scoring_person_id"].isin(p3_ids)
]
show(3, "IC 3+ recent genuine events (expect: Follow Up/Call Now)", p3, "engagement_score")

p4 = df[
    (df["job_persona"] == "CISO")
    & (df["meaningful_count"].fillna(0) == 0)  # no genuine responses (Sent-only or no CMs)
    & ~df["hard_blocker"].fillna(False)
]
show(4, "CISO zero genuine engagement (expect: Nurture)", p4, "account_fit_score")

p5 = df[(df["job_persona"] == "Non-Prospect: Competitor") & (df["engagement_count"].fillna(0) > 3)]
show(5, "Competitor high engagement (expect: Flagged)", p5)

p6 = df[
    df["flag_email_bounced"].fillna(False)
    & df["flag_opted_out"].fillna(False)
    & ~df["flag_non_prospect"].fillna(False)
    & df["scoring_person_id"].isin(set(recent_cm["scoring_person_id"].unique()))
]
show(6, "Bounced+opted out + recent events (expect: scored + soft flags)", p6, "engagement_score")

p7 = df[
    df["flag_broken_conversion_link"].fillna(False)
    & ~df["hard_blocker"].fillna(False)
    & ~df["flag_opted_out"].fillna(False)  # isolate broken-link case from opted-out noise
]
show(7, "Broken conversion link (expect: scored + DQ note)", p7)

ps = cm.groupby("scoring_person_id").agg(
    total=("campaign_member_id", "count"),
    sent=("member_status", lambda x: (x == "Sent").sum()),
)
p8_ids = set(ps[(ps["total"] >= 40) & (ps["sent"] >= 38)].index)
p8 = df[df["scoring_person_id"].isin(p8_ids) & ~df["hard_blocker"].fillna(False)]
show(8, "40+ events 38 automated (expect: Mid/Low)", p8)

p9_ids = set(leads[leads["mql_cycle_count"] == 4]["lead_id"])
p9 = df[df["record_id"].isin(p9_ids)]
show(9, "Re-MQL 4 cycles (expect: Depends)", p9)

p10 = df[
    (df["entity_type"] == "Contact")
    & df["flag_orphan_contact"].fillna(False)
    & (df["account_intent_score"].fillna(0) >= 70)
    & ~df["hard_blocker"].fillna(False)
]
show(10, "Orphan contact high intent (expect: Call Now)", p10)
