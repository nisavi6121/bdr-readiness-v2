"""Synthetic SFDC-style data generator. SEED=42. Writes to data/raw/."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
ROOT = Path(__file__).parent.parent
RAW_DIR = ROOT / "data" / "raw"

RNG = np.random.default_rng(SEED)
# Separate sub-RNG for new Appendix A fields — keeps existing RNG stream unchanged
NEW_FIELDS_RNG = np.random.default_rng(SEED + 1000)

CAMPAIGN_TYPES = ["Event", "Webinar", "Content Syndication", "Telemarketing", "Advertisement", "Email"]
INDUSTRIES = [
    "Software", "Financial Services", "Healthcare", "Telecommunications", "Energy",
    "Manufacturing", "Retail", "Education", "Professional Services", "Government",
]
ICP_INDUSTRIES = {"Software", "Financial Services", "Healthcare", "Telecommunications", "Energy"}

JOB_LEVELS = ["C-Level", "VP", "Director", "Manager", "Individual Contributor"]
JOB_PERSONAS = [
    "Technical Buyer", "CISO", "Financial Buyer", "Influencer",   # genuine prospects
    "Non-Prospect: Competitor", "Non-Prospect: Partner",           # contamination sub-types
    "Non-Prospect: Employee", "Non-Prospect: Vendor",
    "Non-Prospect: Other",                                         # unclassified contamination
]
MEMBER_STATUSES = ["Attended", "Responded", "Clicked", "Registered", "No Show", "Sent"]

FREE_EMAIL_DOMAINS = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "protonmail.com"}

COUNTRIES = ["United States", "United Kingdom", "Canada", "Germany", "Australia", "France", "Netherlands", "Sweden"]
COUNTRY_WEIGHTS = [0.70, 0.08, 0.06, 0.05, 0.04, 0.03, 0.02, 0.02]

LEAD_SOURCES = ["Web", "Event", "Partner Referral", "Cold Call", "Content Syndication",
                "Employee Referral", "Advertisement", "Webinar", "Trade Show", "Paid Search"]
LEAD_SOURCE_WEIGHTS = [0.25, 0.15, 0.10, 0.12, 0.10, 0.05, 0.08, 0.07, 0.05, 0.03]

FIRST_NAMES = [
    "James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda",
    "William", "Barbara", "David", "Susan", "Richard", "Jessica", "Joseph", "Sarah",
    "Thomas", "Karen", "Charles", "Lisa", "Christopher", "Nancy", "Daniel", "Betty",
    "Matthew", "Margaret", "Anthony", "Sandra", "Mark", "Ashley", "Donald", "Emily",
    "Steven", "Donna", "Paul", "Michelle", "Andrew", "Dorothy", "Joshua", "Carol",
    "Kenneth", "Amanda", "Kevin", "Melissa", "Brian", "Deborah", "George", "Stephanie",
    "Timothy", "Rebecca", "Ronald", "Sharon", "Edward", "Laura", "Jason", "Cynthia",
    "Jeffrey", "Kathleen", "Ryan", "Amy", "Jacob", "Angela", "Gary", "Shirley",
]
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
    "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
    "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell",
    "Carter", "Roberts",
]

COMPANY_WORDS = [
    "Apex", "Nexus", "Prism", "Vertex", "Quantum", "Orbit", "Cipher", "Forge",
    "Atlas", "Beacon", "Cobalt", "Dynex", "Eclipse", "Fusion", "Glacier", "Helios",
    "Ionic", "Jasper", "Krypton", "Lattice", "Meridian", "Nova", "Obsidian", "Paragon",
    "Quartz", "Radiant", "Solaris", "Tectonic", "Umbra", "Vortex", "Warden", "Xenon",
    "Zenith", "Aether", "Bastion", "Cascade", "Delphi", "Emblem", "Finesse", "Gravitas",
    "Harbor", "Impulse", "Junction", "Kinetic", "Luminary", "Mantle", "Nimbus",
]
COMPANY_SUFFIXES = ["Systems", "Technologies", "Solutions", "Group", "Dynamics", "Corp", "Labs", "Networks", "Ventures", "Partners"]


def _pick(arr, size, replace=True):
    return RNG.choice(arr, size=size, replace=replace)


def _rnd():
    return RNG.random()


def generate_accounts(n: int = 200) -> pd.DataFrame:
    names = [f"{RNG.choice(COMPANY_WORDS)} {RNG.choice(COMPANY_SUFFIXES)}" for _ in range(n)]
    industries = _pick(INDUSTRIES, n)
    emp_choices = [25, 50, 75, 100, 150, 200, 300, 500, 750, 1000, 1500, 2000, 3500, 5000, 7500, 10000, 15000, 25000, 50000]
    employees = _pick(emp_choices, n)
    named = RNG.random(n) < 0.20
    dnc = RNG.random(n) < 0.04
    intent = (RNG.random(n) * 100).round(1)
    domains = [name.lower().replace(" ", "") + ".com" for name in names]

    countries = NEW_FIELDS_RNG.choice(COUNTRIES, n, p=COUNTRY_WEIGHTS)
    # Annual revenue (USD millions) — size-banded with multiplicative noise
    rev_per_emp = np.select(
        [employees < 100, employees < 500, employees < 5000, employees < 25000],
        [
            NEW_FIELDS_RNG.uniform(30_000, 100_000, n),
            NEW_FIELDS_RNG.uniform(100_000, 200_000, n),
            NEW_FIELDS_RNG.uniform(150_000, 350_000, n),
            NEW_FIELDS_RNG.uniform(200_000, 500_000, n),
        ],
        default=NEW_FIELDS_RNG.uniform(300_000, 800_000, n),
    )
    annual_revenue = (employees.astype(float) * rev_per_emp / 1_000_000).round(1)

    is_icp_qualified = pd.Series(industries).isin(ICP_INDUSTRIES).values

    return pd.DataFrame({
        "account_id": [f"ACC{i:04d}" for i in range(1, n + 1)],
        "account_name": names,
        "domain": domains,
        "industry": industries,
        "employee_count": employees,
        "is_named_account": named,
        "is_icp_qualified": is_icp_qualified,
        "account_do_not_contact": dnc,
        "intent_score": intent,
        "country": countries,
        "annual_revenue": annual_revenue,
    })


def generate_campaigns(n: int = 60) -> pd.DataFrame:
    # 40 historical (2023-2024), 15 moderately recent (2025), 5 very recent (last 60 days)
    n_very_recent = 5
    n_recent = 15
    n_historical = n - n_recent - n_very_recent
    base_hist = pd.Timestamp("2023-01-01")
    base_recent = pd.Timestamp("2025-01-01")
    base_very_recent = pd.Timestamp("2026-03-21")  # ~60 days before today (2026-05-20)
    offsets_hist = RNG.integers(0, 730, n_historical)
    offsets_recent = RNG.integers(0, 365, n_recent)
    offsets_vrecent = RNG.integers(0, 60, n_very_recent)
    start_dates = (
        [base_hist + pd.Timedelta(days=int(d)) for d in offsets_hist]
        + [base_recent + pd.Timedelta(days=int(d)) for d in offsets_recent]
        + [base_very_recent + pd.Timedelta(days=int(d)) for d in offsets_vrecent]
    )
    # Very recent campaigns: guarantee Event/Webinar types for persona 1 and 3 coverage
    types_hist_recent = list(_pick(CAMPAIGN_TYPES, n_historical + n_recent))
    types_vrecent = ["Webinar", "Event", "Webinar", "Content Syndication", "Event"][:n_very_recent]
    types = types_hist_recent + types_vrecent
    names = [f"{ct} Campaign {i:03d}" for i, ct in enumerate(types, 1)]
    return pd.DataFrame({
        "campaign_id": [f"CAM{i:04d}" for i in range(1, n + 1)],
        "campaign_name": names,
        "campaign_type": types,
        "start_date": [d.date().isoformat() for d in start_dates],
    })


def _make_email(first: str, last: str, domain: str, use_free: bool) -> str:
    if use_free:
        fd = RNG.choice(list(FREE_EMAIL_DOMAINS))
        return f"{first.lower()}.{last.lower()}@{fd}"
    return f"{first[0].lower()}{last.lower()}@{domain}"


def generate_people(accounts: pd.DataFrame, n_leads: int = 600, n_contacts: int = 400, n_converted: int = 200) -> tuple[pd.DataFrame, pd.DataFrame]:
    n_total = n_leads + n_contacts
    first_names = _pick(FIRST_NAMES, n_total)
    last_names = _pick(LAST_NAMES, n_total)

    acc_ids = accounts["account_id"].tolist()
    acc_names = dict(zip(accounts["account_id"], accounts["account_name"]))
    acc_industries = dict(zip(accounts["account_id"], accounts["industry"]))
    acc_employees = dict(zip(accounts["account_id"], accounts["employee_count"]))

    # DQ-7: ~15% missing account linkage
    person_account_ids = np.where(RNG.random(n_total) < 0.15, None, _pick(acc_ids, n_total))
    # Realistic seniority pyramid + ~15% null (not everyone fills in job level on a form)
    _jl_weights = [0.05, 0.12, 0.18, 0.25, 0.40]  # C-Level, VP, Director, Manager, Individual Contributor
    job_levels_raw = RNG.choice(JOB_LEVELS, size=n_total, p=_jl_weights)
    job_levels = np.where(RNG.random(n_total) < 0.15, None, job_levels_raw)

    # DQ-6: ~40% null; of non-null: ~50% genuine prospects, ~50% contamination (5 NP sub-types)
    # TB, CISO, FB, Influencer, NP:Competitor, NP:Partner, NP:Employee, NP:Vendor, NP:Other
    _jp_weights = [0.20, 0.08, 0.12, 0.10, 0.12, 0.07, 0.14, 0.09, 0.08]
    job_personas_raw = np.where(
        RNG.random(n_total) < 0.40,
        None,
        RNG.choice(JOB_PERSONAS, size=n_total, p=_jp_weights),
    )
    # DQ-7: missing title/phone
    titles_raw = np.where(RNG.random(n_total) < 0.12, None, [f"{jl} of Something" if jl else "Unknown Title" for jl in job_levels])
    phones_raw = np.where(RNG.random(n_total) < 0.18, None, [f"+1-555-{RNG.integers(1000,9999)}" for _ in range(n_total)])
    # DQ-11: free email leakage — actual_free_email correct, free_email_known misses some
    actual_free = RNG.random(n_total) < 0.08
    free_known = actual_free.copy()
    leak_mask = actual_free & (RNG.random(n_total) < 0.35)
    free_known[leak_mask] = False

    domains = [
        (acc_names.get(aid, "unknown").lower().replace(" ", "") + ".com") if aid else "unknown.com"
        for aid in person_account_ids
    ]
    emails = [_make_email(fn, ln, dom, bool(af)) for fn, ln, dom, af in zip(first_names, last_names, domains, actual_free)]

    # DQ-2: person-to-person duplicate emails (~5%)
    n_dupes = int(n_total * 0.05)
    dupe_indices = RNG.choice(n_total, size=n_dupes * 2, replace=False)
    for i in range(n_dupes):
        emails[dupe_indices[n_dupes + i]] = emails[dupe_indices[i]]

    already_modified = set(dupe_indices.tolist())

    # DQ-2: shared mailbox addresses — info@, sales@, marketing@ etc. (~4 records each)
    shared_mailboxes = [
        "info@techconf.com",          "info@securitysummit.org",    "info@b2bleads.net",
        "sales@megacorp.com",         "sales@cloudvendor.io",       "sales@enterprisetech.com",
        "marketing@globalpartners.com", "contact@vendorlist.net",
        "admin@tradeshow.events",     "hello@sdrlists.com",
    ]
    mailbox_pool = [i for i in range(n_total) if i not in already_modified]
    RNG.shuffle(mailbox_pool)
    pos = 0
    for addr in shared_mailboxes:
        for _ in range(int(RNG.integers(4, 8))):
            if pos < len(mailbox_pool):
                emails[mailbox_pool[pos]] = addr
                already_modified.add(mailbox_pool[pos])
                pos += 1

    # DQ-2: high-cardinality spam clusters — leads-only addresses
    lead_spam_clusters = [
        ("newsletter@marketingblast.com", 13),
        ("leads@databroker.io",           11),
    ]
    lead_spam_pool = [i for i in range(n_leads) if i not in already_modified]
    RNG.shuffle(lead_spam_pool)
    pos = 0
    for spam_email, count in lead_spam_clusters:
        for _ in range(count):
            if pos < len(lead_spam_pool):
                emails[lead_spam_pool[pos]] = spam_email
                pos += 1

    # DQ-2: high-cardinality spam clusters — contacts-only addresses
    contact_spam_clusters = [
        ("noreply@formspam.net",          14),
        ("subscribe@vendorblast.com",     10),
    ]
    contact_spam_pool = [i for i in range(n_leads, n_total) if i not in already_modified]
    RNG.shuffle(contact_spam_pool)
    pos = 0
    for spam_email, count in contact_spam_clusters:
        for _ in range(count):
            if pos < len(contact_spam_pool):
                emails[contact_spam_pool[pos]] = spam_email
                pos += 1

    # DQ-4: ETL-dominated created_date — 80% leads, 34% contacts will be ETL date
    etl_date = "2024-01-01"
    base_date = pd.Timestamp("2022-01-01")
    real_offsets = RNG.integers(0, 730, n_total)
    real_dates = [(base_date + pd.Timedelta(days=int(d))).date().isoformat() for d in real_offsets]
    etl_flags_lead = RNG.random(n_leads) < 0.80
    etl_flags_contact = np.zeros(n_contacts, dtype=bool)
    etl_flags_contact[RNG.choice(n_contacts, size=int(n_contacts * 0.35), replace=False)] = True
    etl_flags = np.concatenate([etl_flags_lead, etl_flags_contact])
    created_dates = [etl_date if etl_flags[i] else real_dates[i] for i in range(n_total)]

    # DQ-9: opted out, bounced, no-longer-with-company — combined ~35% of database
    email_opt_out = RNG.random(n_total) < 0.22
    email_bounced = RNG.random(n_total) < 0.10
    no_longer = RNG.random(n_total) < 0.08

    # Split into leads and contacts
    l_idx = slice(0, n_leads)
    c_idx = slice(n_leads, n_total)

    # --- LEADS ---
    lead_ids = [f"L{i:05d}" for i in range(1, n_leads + 1)]
    # DQ-3: mql_date overwrites — generate once, some converted leads get mql_date from conversion time
    is_mql_lead = RNG.random(n_leads) < 0.28
    mql_dates_lead = [
        (base_date + pd.Timedelta(days=int(RNG.integers(0, 730)))).date().isoformat() if is_mql_lead[i] else None
        for i in range(n_leads)
    ]
    lead_statuses = np.where(is_mql_lead, "MQL", RNG.choice(["Open", "Working", "Nurturing", "Disqualified"], size=n_leads))
    # DQ-5: lead has mkto_lead_score (int 0-100)
    mkto_lead_scores = (RNG.random(n_leads) * 100).astype(int)
    # DQ-10: 10% of scores reset to 0 on re-MQL
    mkto_lead_scores[RNG.random(n_leads) < 0.10] = 0

    # DQ-10: re-MQL cycles — mql_cycle_count tracks how many times a record hit MQL
    # dq_reason and dq_date are cleared on re-MQL (that's the DQ-10 issue: history is lost)
    mql_cycle_count = np.zeros(n_leads, dtype=int)
    mql_idx = np.where(is_mql_lead)[0]
    mql_cycle_count[mql_idx] = RNG.choice([1, 1, 1, 2, 2, 3, 4, 4], size=len(mql_idx))
    # Non-MQL leads: some are currently disqualified (haven't re-MQL'd yet)
    is_disqualified = (RNG.random(n_leads) < 0.12) & ~is_mql_lead
    _dq_reason_opts = ["Competitor", "Duplicate", "No Longer With Company", "Bad Data"]
    dq_reasons = [
        RNG.choice(_dq_reason_opts) if is_disqualified[i] else None
        for i in range(n_leads)
    ]
    dq_dates = [
        (base_date + pd.Timedelta(days=int(RNG.integers(0, 730)))).date().isoformat()
        if is_disqualified[i] else None
        for i in range(n_leads)
    ]

    # ZoomInfo enrichment fields for leads that have no native account linkage (L2/L3/L4 segmentation)
    # Simulates third-party enrichment stamps applied independently of CRM account matching
    lead_acc_ids = person_account_ids[l_idx]
    no_account_mask_l = pd.Series(lead_acc_ids).isna().values
    emp_choices = [25, 50, 75, 100, 150, 200, 300, 500, 750, 1000, 1500, 2000, 3500, 5000, 7500, 10000, 15000, 25000, 50000]
    zi_industry_vals = np.where(
        no_account_mask_l & (RNG.random(n_leads) < 0.55),
        RNG.choice(INDUSTRIES, n_leads),
        None,
    )
    zi_employee_vals = np.where(
        no_account_mask_l & (RNG.random(n_leads) < 0.45),
        RNG.choice(emp_choices, n_leads).astype(str),
        None,
    )

    lead_sources = NEW_FIELDS_RNG.choice(LEAD_SOURCES, size=n_leads, p=LEAD_SOURCE_WEIGHTS)

    # company: self-reported messy field — ~70% matches account_name with noise, ~30% blank or free-text
    # Uses NEW_FIELDS_RNG to preserve main RNG stream reproducibility
    _acc_name_for_lead = [acc_names.get(aid, "") for aid in lead_acc_ids]
    _noise_opts = ["Inc.", "LLC", "Corp", "Ltd", "& Co", "Group", ""]
    company_vals = [
        (name + " " + NEW_FIELDS_RNG.choice(_noise_opts)).strip() if name and NEW_FIELDS_RNG.random() < 0.70
        else (NEW_FIELDS_RNG.choice(["", name, name.split()[0] if name else ""]))
        for name in _acc_name_for_lead
    ]
    company_vals = [v if v else None for v in company_vals]

    leads = pd.DataFrame({
        "lead_id": lead_ids,
        "first_name": first_names[l_idx],
        "last_name": last_names[l_idx],
        "email": emails[l_idx],
        "title": titles_raw[l_idx],
        "company": company_vals,
        "job_level": job_levels[l_idx],
        "job_persona": job_personas_raw[l_idx],
        "phone": phones_raw[l_idx],
        "account_id": lead_acc_ids,
        "industry": [acc_industries.get(aid) for aid in lead_acc_ids],
        "employee_count": [acc_employees.get(aid) for aid in lead_acc_ids],
        "zi_industry": zi_industry_vals,
        "zi_employee_count": zi_employee_vals,
        "created_date": created_dates[l_idx],
        "lead_source": lead_sources,
        "lead_status": lead_statuses,
        "is_current_mql": is_mql_lead,
        "mql_date": mql_dates_lead,
        "email_opt_out": email_opt_out[l_idx],
        "email_bounced": email_bounced[l_idx],
        "no_longer_with_company": no_longer[l_idx],
        "is_converted": False,
        "converted_contact_id": None,
        "free_email_known": free_known[l_idx],
        "actual_free_email": actual_free[l_idx],
        "mkto_lead_score": mkto_lead_scores,
        "mql_cycle_count": mql_cycle_count,
        "is_disqualified": is_disqualified,
        "dq_reason": dq_reasons,
        "dq_date": dq_dates,
    })

    # --- CONTACTS ---
    contact_ids = [f"C{i:05d}" for i in range(1, n_contacts + 1)]
    is_mql_contact = RNG.random(n_contacts) < 0.35
    mql_dates_contact = [
        (base_date + pd.Timedelta(days=int(RNG.integers(0, 730)))).date().isoformat() if is_mql_contact[i] else None
        for i in range(n_contacts)
    ]
    # DQ-5: contact has mkto_contact_score_c (float 0-100)
    mkto_contact_scores = (RNG.random(n_contacts) * 100).round(1)
    mkto_contact_scores[RNG.random(n_contacts) < 0.10] = 0.0

    contacts = pd.DataFrame({
        "contact_id": contact_ids,
        "first_name": first_names[c_idx],
        "last_name": last_names[c_idx],
        "email": emails[c_idx],
        "title": titles_raw[c_idx],
        "job_level": job_levels[c_idx],
        "job_persona": job_personas_raw[c_idx],
        "phone": phones_raw[c_idx],
        "account_id": person_account_ids[c_idx],
        "industry": [acc_industries.get(aid) for aid in person_account_ids[c_idx]],
        "employee_count": [acc_employees.get(aid) for aid in person_account_ids[c_idx]],
        "created_date": created_dates[c_idx],
        "is_mql": is_mql_contact,
        "mql_date": mql_dates_contact,
        "email_opt_out": email_opt_out[c_idx],
        "email_bounced": email_bounced[c_idx],
        "is_converted": False,
        "primary_lead_id": None,
        "free_email_known": free_known[c_idx],
        "actual_free_email": actual_free[c_idx],
        "mkto_contact_score_c": mkto_contact_scores,
    })

    # DQ-1: converted lead pairs — 80% linked, 20% broken
    converted_lead_idx = RNG.choice(n_leads, size=n_converted, replace=False)
    converted_contact_idx = RNG.choice(n_contacts, size=n_converted, replace=False)
    broken_mask = RNG.random(n_converted) < 0.20

    for i, (li, ci) in enumerate(zip(converted_lead_idx, converted_contact_idx)):
        leads.iloc[li, leads.columns.get_loc("is_converted")] = True
        # A converted Contact is created FROM the Lead — they are the SAME person.
        # Sync the full person identity so a connected pair is one human, not two.
        # Account is intentionally NOT synced: a lead often has no account and gets one
        # on conversion, so divergence there is realistic.
        # NOTE: copies existing values only — no RNG draws — so the data stream is unchanged.
        for _f in ("first_name", "last_name", "email", "title", "job_level", "job_persona", "phone"):
            contacts.iloc[ci, contacts.columns.get_loc(_f)] = leads.iloc[li][_f]
        # Same person -> same company. In SFDC, conversion resolves the lead's Company to an
        # Account and attaches the contact to it, so the contact lands on the lead's account.
        # Only sync when the lead actually has an account; if it doesn't, the contact keeps
        # its own (conversion assigns one) so "contacts always have an account" still holds.
        if pd.notna(leads.iloc[li]["account_id"]):
            for _af in ("account_id", "industry", "employee_count"):
                contacts.iloc[ci, contacts.columns.get_loc(_af)] = leads.iloc[li][_af]
        if not broken_mask[i]:
            leads.iloc[li, leads.columns.get_loc("converted_contact_id")] = contact_ids[ci]
            contacts.iloc[ci, contacts.columns.get_loc("primary_lead_id")] = lead_ids[li]
        # DQ-3: overwrite mql_date for converted leads
        if bool(leads.iloc[li]["is_current_mql"]):
            conv_date = (base_date + pd.Timedelta(days=int(RNG.integers(365, 730)))).date().isoformat()
            leads.iloc[li, leads.columns.get_loc("mql_date")] = conv_date

    contacts["has_lead_origin"] = contacts["primary_lead_id"].notna()

    return leads, contacts


def generate_campaign_members(leads: pd.DataFrame, contacts: pd.DataFrame, campaigns: pd.DataFrame, accounts: pd.DataFrame, n_target: int = 4200) -> pd.DataFrame:
    camp_ids = campaigns["campaign_id"].tolist()
    camp_types = dict(zip(campaigns["campaign_id"], campaigns["campaign_type"]))
    camp_names = dict(zip(campaigns["campaign_id"], campaigns["campaign_name"]))
    camp_dates = dict(zip(campaigns["campaign_id"], pd.to_datetime(campaigns["start_date"])))

    records = []
    cm_id = 1

    # Weight engagements: persona × account quality — they should not be independent.
    # ICP + named accounts attract more marketing spend → more campaigns targeted at them.
    # High intent score signals active research → people there show up at events more.
    _np_personas = {p for p in JOB_PERSONAS if p.startswith("Non-Prospect")}

    # Pre-build account lookup for fast access
    _acc_index = accounts.set_index("account_id")

    def _acct_quality_multiplier(acc_id):
        if pd.isna(acc_id) or acc_id not in _acc_index.index:
            return 0.5  # no account linkage — off targeted lists entirely
        row = _acc_index.loc[acc_id]
        m = 1.0
        if row.get("industry") in ICP_INDUSTRIES:
            m *= 2.0   # ICP industry → much more campaign targeting
        if bool(row.get("is_named_account")):
            m *= 2.5   # named account → ABM, direct invite lists, high-touch sequences
        intent = float(row.get("intent_score") or 0)
        m *= (0.5 + intent / 100)  # intent 0→0.5×, intent 50→1.0×, intent 100→1.5×
        return m

    lead_persona_w = np.where(
        leads["job_persona"].isna() | leads["job_persona"].isin(_np_personas), 0.8, 2.5
    )
    lead_acct_w = np.array([_acct_quality_multiplier(aid) for aid in leads["account_id"]])
    lead_weights = lead_persona_w * lead_acct_w

    contact_persona_w = np.where(
        contacts["job_persona"].isna() | contacts["job_persona"].isin(_np_personas), 0.8, 3.5
    )
    contact_acct_w = np.array([_acct_quality_multiplier(aid) for aid in contacts["account_id"]])
    contact_weights = contact_persona_w * contact_acct_w

    # Per-person engagement intensity — ICP+named people also attend more events per campaign.
    # Stored as a lookup so it doesn't add extra RNG calls inside the main loop.
    all_acct_w = np.concatenate([lead_acct_w, contact_acct_w])
    # Normalise to [0,1] range for n_events scaling
    _aw_max = all_acct_w.max() if all_acct_w.max() > 0 else 1.0
    engagement_intensity = all_acct_w / _aw_max  # 0 = weakest account, 1 = strongest

    # Profile lookup for campaign recency bias (personas 1 and 3)
    lead_profiles = leads.set_index("lead_id")[["job_level", "job_persona"]].to_dict("index")
    contact_profiles = contacts.set_index("contact_id")[["job_level", "job_persona"]].to_dict("index")
    _senior_levels = {"VP", "C-Level"}
    _prospect_personas = {"CISO", "Technical Buyer", "Financial Buyer", "Influencer"}
    # Recent = campaigns from 2026 (very recent batch)
    _recent_cids = [cid for cid, d in camp_dates.items() if d >= pd.Timestamp("2026-01-01")]
    _hist_cids = [cid for cid in camp_ids if cid not in set(_recent_cids)]
    all_ids = leads["lead_id"].tolist() + contacts["contact_id"].tolist()
    all_types = ["Lead"] * len(leads) + ["Contact"] * len(contacts)
    all_weights = np.concatenate([lead_weights, contact_weights])
    all_weights = all_weights / all_weights.sum()

    n_people_with_engagement = min(len(all_ids), 750)
    engaged_idx = RNG.choice(len(all_ids), size=n_people_with_engagement, replace=False, p=all_weights)

    # DQ-8: ~30% of records will be automation-inflated
    automation_inflated = set(RNG.choice(len(all_ids), size=int(len(all_ids) * 0.30), replace=False))

    # DQ-2 shared mailbox inflation: build email → [entity_ids] map for shared mailbox addresses only
    # (spam clusters excluded — different people with a fake email, not a real shared inbox)
    SHARED_PREFIXES = ("info@", "sales@", "marketing@", "contact@", "admin@", "hello@")
    all_people = pd.concat([
        leads[["lead_id", "email"]].rename(columns={"lead_id": "entity_id"}),
        contacts[["contact_id", "email"]].rename(columns={"contact_id": "entity_id"}),
    ], ignore_index=True)
    entity_to_email = dict(zip(all_people["entity_id"], all_people["email"]))
    shared_email_groups = {
        email: grp["entity_id"].tolist()
        for email, grp in all_people.groupby("email")
        if email.startswith(SHARED_PREFIXES) and len(grp) > 1
    }

    for idx in engaged_idx:
        pid = all_ids[idx]
        ptype = all_types[idx]
        is_inflated = idx in automation_inflated
        # ~5% of inflated records get extreme inflation (40-45 events) — persona 8
        if is_inflated and RNG.random() < 0.05:
            n_events = int(RNG.integers(40, 46))
        elif is_inflated:
            n_events = int(RNG.integers(6, 18))
        else:
            # Account quality boosts n_events: ICP+named+high-intent people attend more
            # intensity range [0,1]; low-quality → 1-3 events, high-quality → 1-8 events
            intensity = engagement_intensity[idx]
            n_events = int(RNG.integers(1, max(4, int(4 + intensity * 5))))
        # Bias senior genuine prospects and active ICs toward recent campaigns
        profile = lead_profiles.get(pid) or contact_profiles.get(pid) or {}
        jl = str(profile.get("job_level") or "")
        jp = str(profile.get("job_persona") or "")
        is_senior_prospect = jl in _senior_levels and jp in _prospect_personas
        is_ic_active = jl == "Individual Contributor" and not is_inflated

        if _recent_cids and (is_senior_prospect or is_ic_active):
            n_r = max(1, n_events // 2) if is_senior_prospect else max(1, n_events // 3)
            n_h = n_events - n_r
            chosen_camps = (
                list(RNG.choice(_recent_cids, size=n_r, replace=True))
                + list(_pick(_hist_cids if _hist_cids else camp_ids, n_h))
            )
        else:
            chosen_camps = _pick(camp_ids, n_events)

        for cid in chosen_camps:
            ctype = camp_types[cid]
            camp_date = camp_dates[cid]
            response_date = min(
                camp_date + pd.Timedelta(days=int(RNG.integers(0, 30))),
                pd.Timestamp.today().normalize(),
            )

            if is_inflated and RNG.random() < 0.82:
                status = "Sent"
                is_auto = True
            else:
                if ctype == "Event":
                    status = RNG.choice(["Attended", "Registered", "No Show"], p=[0.45, 0.35, 0.20])
                elif ctype == "Webinar":
                    status = RNG.choice(["Attended", "Registered", "No Show"], p=[0.35, 0.40, 0.25])
                elif ctype in ("Content Syndication", "Telemarketing"):
                    status = RNG.choice(["Responded", "Clicked", "Sent"], p=[0.30, 0.45, 0.25])
                elif ctype == "Advertisement":
                    status = RNG.choice(["Clicked", "Sent"], p=[0.40, 0.60])
                else:  # Email
                    status = RNG.choice(["Clicked", "Responded", "Sent"], p=[0.25, 0.15, 0.60])
                is_auto = ctype == "Email" and status == "Sent"

            records.append({
                "cm_id": f"CM{cm_id:06d}",
                "entity_id": pid,
                "entity_type": ptype,
                "campaign_id": cid,
                "campaign_name": camp_names[cid],
                "campaign_type": ctype,
                "member_status": status,
                "is_responded": status != "Sent",
                "response_date": response_date.date().isoformat(),
                "is_automated": bool(is_auto),
            })
            cm_id += 1
            if len(records) >= n_target:
                break
        if len(records) >= n_target:
            break

    # DQ-2 shared mailbox inflation: clone every CM of a shared-mailbox record to all
    # other members of that mailbox group (simulates one email open inflating all records)
    clones = []
    for rec in records:
        email = entity_to_email.get(rec["entity_id"], "")
        if email in shared_email_groups:
            for other_id in shared_email_groups[email]:
                if other_id != rec["entity_id"]:
                    clones.append({
                        "cm_id": f"CM{cm_id:06d}",
                        "entity_id": other_id,
                        "entity_type": "Lead" if other_id.startswith("L") else "Contact",
                        "campaign_id": rec["campaign_id"],
                        "campaign_name": rec["campaign_name"],
                        "campaign_type": rec["campaign_type"],
                        "member_status": rec["member_status"],
                        "is_responded": rec["is_responded"],
                        "response_date": rec["response_date"],
                        "is_automated": rec["is_automated"],
                    })
                    cm_id += 1

    df = pd.DataFrame(records + clones)
    # is_active: ~90% True; False simulates records removed from campaign or unsubscribed
    df["is_active"] = NEW_FIELDS_RNG.random(len(df)) > 0.10
    return df


def _inject_persona_guarantees(
    accounts: pd.DataFrame,
    leads: pd.DataFrame,
    contacts: pd.DataFrame,
    campaigns: pd.DataFrame,
    campaign_members: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Inject guaranteed CM records for P1 (VP/CL named ICP MQL) and P10 (orphan contact high intent).
    Modifies leads/contacts in-place where needed; returns updated DataFrames."""
    _PROSPECT_PERSONAS_G = {"CISO", "Technical Buyer", "Financial Buyer", "Influencer"}

    camp_ts = dict(zip(campaigns["campaign_id"], pd.to_datetime(campaigns["start_date"])))
    camp_type_map = dict(zip(campaigns["campaign_id"], campaigns["campaign_type"]))
    today_ts = pd.Timestamp("2026-05-20")
    very_recent_cids = [cid for cid, d in camp_ts.items() if d >= today_ts - pd.Timedelta(days=60)]
    if not very_recent_cids:
        return leads, contacts, accounts, campaign_members

    named_acc_ids = set(accounts[accounts["is_named_account"]]["account_id"])
    icp_acc_ids = set(accounts[accounts["industry"].isin(ICP_INDUSTRIES)]["account_id"])
    named_icp_accs = named_acc_ids & icp_acc_ids

    cm_next_id = int(campaign_members["cm_id"].str.replace("CM", "").astype(int).max()) + 1
    extra = []

    def _genuine_status(ctype: str) -> str:
        if ctype in ("Event", "Webinar"):
            return "Attended"
        if ctype == "Telemarketing":
            return "Responded"
        return "Clicked"

    def _add_events(pid: str, etype: str, cids: list, nonlocal_id: list) -> None:
        for cid in cids:
            ctype = camp_type_map[cid]
            base = camp_ts[cid]
            rdate = min(
                base + pd.Timedelta(days=int(RNG.integers(1, 8))),
                pd.Timestamp.today().normalize(),
            )
            extra.append({
                "cm_id": f"CM{nonlocal_id[0]:06d}",
                "entity_id": pid,
                "entity_type": etype,
                "campaign_id": cid,
                "campaign_type": ctype,
                "member_status": _genuine_status(ctype),
                "response_date": rdate.date().isoformat(),
                "is_automated": False,
            })
            nonlocal_id[0] += 1

    id_counter = [cm_next_id]

    # --- P1: VP/CL + named ICP account + MQL + inject recent genuine events ---
    p1_leads = leads[
        leads["job_level"].isin(["VP", "C-Level"])
        & leads["job_persona"].isin(_PROSPECT_PERSONAS_G)
        & leads["is_current_mql"]
        & leads["account_id"].isin(named_icp_accs)
    ]["lead_id"].tolist()
    p1_contacts = contacts[
        contacts["job_level"].isin(["VP", "C-Level"])
        & contacts["job_persona"].isin(_PROSPECT_PERSONAS_G)
        & contacts["is_mql"]
        & contacts["account_id"].isin(named_icp_accs)
    ]["contact_id"].tolist()
    p1_candidates = p1_leads + p1_contacts

    # If no natural candidates, promote the best available lead
    if not p1_candidates:
        vp_icp = leads[
            leads["job_level"].isin(["VP", "C-Level"])
            & leads["account_id"].isin(icp_acc_ids)
            & ~leads["is_current_mql"]
        ]
        if len(vp_icp) > 0:
            idx = vp_icp.index[0]
            acc_id = leads.at[idx, "account_id"]
            accounts.loc[accounts["account_id"] == acc_id, "is_named_account"] = True
            leads.at[idx, "is_current_mql"] = True
            leads.at[idx, "lead_status"] = "MQL"
            if leads.at[idx, "job_persona"] not in _PROSPECT_PERSONAS_G:
                leads.at[idx, "job_persona"] = "Technical Buyer"
            p1_candidates = [leads.at[idx, "lead_id"]]

    for pid in p1_candidates[:2]:
        etype = "Lead" if pid.startswith("L") else "Contact"
        # Inject enough genuine events to push automation_share below 0.70
        _add_events(pid, etype, very_recent_cids[:5], id_counter)

    # --- P10: orphan contact + named ICP + account_intent_score >= 70 + recent genuine events ---
    high_intent_named_icp = set(
        accounts[
            accounts["is_named_account"]
            & accounts["industry"].isin(ICP_INDUSTRIES)
            & (accounts["intent_score"] >= 70)
        ]["account_id"]
    )
    p10_df = contacts[
        contacts["primary_lead_id"].isna()
        & contacts["job_level"].isin(["VP", "C-Level", "Director"])
        & contacts["job_persona"].isin(["CISO", "Technical Buyer"])
        & contacts["account_id"].isin(high_intent_named_icp)
    ]
    if len(p10_df) > 0:
        p10_pid = p10_df.iloc[0]["contact_id"]
    else:
        # Patch the first orphan contact to qualify
        orphans = contacts[contacts["primary_lead_id"].isna()]
        if len(orphans) > 0 and len(high_intent_named_icp) > 0:
            idx = orphans.index[0]
            hi_acc = next(iter(high_intent_named_icp))
            acc_row = accounts[accounts["account_id"] == hi_acc].iloc[0]
            contacts.at[idx, "account_id"] = hi_acc
            contacts.at[idx, "industry"] = acc_row["industry"]
            contacts.at[idx, "employee_count"] = acc_row["employee_count"]
            contacts.at[idx, "job_level"] = "VP"
            contacts.at[idx, "job_persona"] = "Technical Buyer"
            p10_pid = contacts.at[idx, "contact_id"]
        else:
            p10_pid = None

    if p10_pid:
        _add_events(p10_pid, "Contact", very_recent_cids[:4], id_counter)

    if extra:
        campaign_members = pd.concat([campaign_members, pd.DataFrame(extra)], ignore_index=True)

    return leads, contacts, accounts, campaign_members


def generate_all(output_dir: Path = RAW_DIR) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    accounts = generate_accounts(200)
    campaigns = generate_campaigns(60)
    leads, contacts = generate_people(accounts, n_leads=600, n_contacts=400, n_converted=200)
    campaign_members = generate_campaign_members(leads, contacts, campaigns, accounts, n_target=5000)

    leads, contacts, accounts, campaign_members = _inject_persona_guarantees(
        accounts, leads, contacts, campaigns, campaign_members
    )

    accounts.to_csv(output_dir / "accounts.csv", index=False)
    campaigns.to_csv(output_dir / "campaigns.csv", index=False)
    leads.to_csv(output_dir / "leads.csv", index=False)
    contacts.to_csv(output_dir / "contacts.csv", index=False)
    campaign_members.to_csv(output_dir / "campaign_members.csv", index=False)

    print(f"accounts:          {len(accounts):,}")
    print(f"campaigns:         {len(campaigns):,}")
    print(f"leads:             {len(leads):,}")
    print(f"contacts:          {len(contacts):,}")
    print(f"campaign_members:  {len(campaign_members):,}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(RAW_DIR))
    args = parser.parse_args()
    generate_all(Path(args.out))
