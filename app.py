"""Flask app — single entry point. Run: python app.py"""
from __future__ import annotations

import math
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd
from flask import Flask, redirect, render_template, request, url_for

ROOT = Path(__file__).parent
SCORED = ROOT / "data" / "scored" / "ranked_records.csv"
CLEANED_CM = ROOT / "data" / "cleaned" / "campaign_members.csv"
KB_DIR = ROOT / "knowledge_base"

app = Flask(__name__)

_ranked: pd.DataFrame | None = None
_cm: pd.DataFrame | None = None


# ── Pipeline bootstrap ────────────────────────────────────────────────────────

def _run_pipeline() -> None:
    steps = [
        ROOT / "generation" / "generate.py",
        ROOT / "backend" / "pipeline" / "01_clean.py",
        ROOT / "backend" / "pipeline" / "02_features.py",
        ROOT / "backend" / "pipeline" / "03_score.py",
        ROOT / "backend" / "pipeline" / "04_rank.py",
    ]
    for s in steps:
        print(f"  running {s.name}…")
        r = subprocess.run([sys.executable, str(s)], cwd=str(ROOT))
        if r.returncode != 0:
            raise SystemExit(f"Pipeline stage {s.name} failed.")


def _load() -> None:
    global _ranked, _cm
    if not SCORED.exists():
        print("Data not found — running pipeline…")
        _run_pipeline()
    _ranked = pd.read_csv(SCORED)
    _cm = pd.read_csv(CLEANED_CM) if CLEANED_CM.exists() else pd.DataFrame()
    print(f"Loaded {len(_ranked):,} records.")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _v(val):
    """Return None for NaN, else the value."""
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    return val


def _row(series: pd.Series) -> dict:
    d = series.to_dict()
    return {k: _v(v) for k, v in d.items()}


def _tier_badge_cls(tier: str) -> str:
    return {"Call Now": "b-call", "Follow Up": "b-follow", "Flagged": "b-flagged"}.get(tier, "b-nurture")


def _markdown_to_html(md: str) -> str:
    """Minimal markdown → HTML (headings, bold, lists, paragraphs)."""
    lines = md.splitlines()
    html, in_ul = [], False
    for line in lines:
        if line.startswith("### "):
            if in_ul: html.append("</ul>"); in_ul = False
            html.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("## "):
            if in_ul: html.append("</ul>"); in_ul = False
            html.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("# "):
            if in_ul: html.append("</ul>"); in_ul = False
            html.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("- "):
            if not in_ul: html.append("<ul>"); in_ul = True
            content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line[2:])
            content = re.sub(r"`(.+?)`", r"<code>\1</code>", content)
            html.append(f"<li>{content}</li>")
        elif line.strip() == "":
            if in_ul: html.append("</ul>"); in_ul = False
            html.append("")
        else:
            if in_ul: html.append("</ul>"); in_ul = False
            content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
            content = re.sub(r"`(.+?)`", r"<code>\1</code>", content)
            html.append(f"<p>{content}</p>")
    if in_ul:
        html.append("</ul>")
    return "\n".join(html)


def _sunburst_html(row: dict) -> str:
    import math

    def _slice(cx, cy, ro, ri, a0, a1, gap=0.8):
        a0g = a0 + gap / 2
        a1g = a1 - gap / 2
        if a1g <= a0g:
            return None
        s0 = math.radians(a0g - 90)
        s1 = math.radians(a1g - 90)
        large = 1 if (a1g - a0g) > 180 else 0
        ox0, oy0 = cx + ro * math.cos(s0), cy + ro * math.sin(s0)
        ox1, oy1 = cx + ro * math.cos(s1), cy + ro * math.sin(s1)
        ix0, iy0 = cx + ri * math.cos(s1), cy + ri * math.sin(s1)
        ix1, iy1 = cx + ri * math.cos(s0), cy + ri * math.sin(s0)
        return (f"M{ox0:.2f},{oy0:.2f} "
                f"A{ro},{ro} 0 {large},1 {ox1:.2f},{oy1:.2f} "
                f"L{ix0:.2f},{iy0:.2f} "
                f"A{ri},{ri} 0 {large},0 {ix1:.2f},{iy1:.2f} Z")

    def _blend(hex_col, intensity):
        intensity = min(max(intensity, 0.12), 1.0)
        bg = (19, 22, 30)
        r = int(int(hex_col[1:3], 16) * intensity + bg[0] * (1 - intensity))
        g = int(int(hex_col[3:5], 16) * intensity + bg[1] * (1 - intensity))
        b = int(int(hex_col[5:7], 16) * intensity + bg[2] * (1 - intensity))
        return f"#{r:02x}{g:02x}{b:02x}"

    eng_score  = float(row.get("engagement_score")  or 0)
    acc_score  = float(row.get("account_fit_score")  or 0)
    prof_score = float(row.get("profile_fit_score")  or 0)
    final      = float(row.get("final_score")        or 0)

    # Use per-record weights stored at score time (differentiated by entity type)
    eng_w  = float(row.get("engagement_weight")  or 0.60)
    acc_w  = float(row.get("account_fit_weight") or 0.22)
    prof_w = float(row.get("profile_fit_weight") or 0.18)
    eng_c  = eng_score  * eng_w
    acc_c  = acc_score  * acc_w
    prof_c = prof_score * prof_w
    total  = max(eng_c + acc_c + prof_c, 0.01)

    type_keys = ["event","webinar","content_syndication","telemarketing","email","advertisement"]
    type_lbls = ["Event","Webinar","Content Syn.","Telemarketing","Email","Ad"]
    type_base = [0.30, 0.25, 0.20, 0.10, 0.10, 0.05]
    raw_e = [max(float(row.get(f"eng_{k}") or 0), 0.0) for k in type_keys]
    raw_s = sum(raw_e)
    ep = [v / raw_s for v in raw_e] if raw_s > 1e-9 else type_base

    icp_p   = 30.0 if row.get("icp_flag")          else 0.0
    named_p = 25.0 if row.get("named_account_flag") else 0.0
    emp_p   = float(row.get("employee_fit") or 0.25) * 15
    int_p   = float(row.get("account_intent_score") or 0) / 100 * 10
    acc_raw = [icp_p, named_p, emp_p, int_p]
    acc_s   = max(sum(acc_raw), 1)
    ap      = [v / acc_s for v in acc_raw]

    jl = float(row.get("job_level_score") or 0)
    jp = float(row.get("job_persona_score") or 0)
    jl_jp = max(jl + jp, 1e-4)
    pp = [jl / jl_jp, jp / jl_jp]

    CX, CY   = 200, 200
    RO, RM, RI, RH = 188, 128, 76, 40

    # Each segment tuple: (label, frac, color, intensity, tooltip_text, center_val, center_sub)
    inner = [
        ("Engagement", eng_c/total, "#4f7cff", eng_score/100,
         f"Engagement  {eng_score:.1f}/100  ×{eng_w:.2f}  →  {eng_c:.1f} pts",
         f"{eng_score:.1f}", "Engagement"),
        ("Account Fit", acc_c/total, "#22c55e", acc_score/100,
         f"Account Fit  {acc_score:.1f}/100  ×{acc_w:.2f}  →  {acc_c:.1f} pts",
         f"{acc_score:.1f}", "Acct Fit"),
        ("Profile Fit", prof_c/total, "#a78bfa", prof_score/100,
         f"Profile Fit  {prof_score:.1f}/100  ×{prof_w:.2f}  →  {prof_c:.1f} pts",
         f"{prof_score:.1f}", "Profile Fit"),
    ]

    acc_max = [30, 25, 15, 10]
    outer = (
        [(type_lbls[i], ep[i]*(eng_c/total), "#4f7cff", ep[i],
          f"{type_lbls[i]}  {ep[i]*100:.0f}% of engagement signal",
          f"{ep[i]*100:.0f}%", type_lbls[i]) for i in range(6)]
        + [(lbl, ap[i]*(acc_c/total), "#22c55e", min(acc_raw[i]/30, 1),
            f"{lbl}  {acc_raw[i]:.1f} / {acc_max[i]} pts",
            f"{acc_raw[i]:.1f}", lbl)
           for i, lbl in enumerate(["ICP","Named","Emp.","Intent"])]
        + [("Job Level", pp[0]*(prof_c/total), "#a78bfa", jl,
            f"Job Level  score {jl:.2f}", f"{jl:.2f}", "Job Level"),
           ("Persona",   pp[1]*(prof_c/total), "#a78bfa", jp,
            f"Job Persona  score {jp:.2f}", f"{jp:.2f}", "Persona")]
    )

    uid = f"sb{abs(hash(str(row.get('record_id', 'x')))) % 100000:05d}"

    parts = [
        f'<div id="{uid}" style="position:relative;user-select:none">',
        f'<svg id="{uid}_svg" viewBox="0 0 400 400" width="100%" '
        f'style="max-width:400px;display:block;margin:0 auto" xmlns="http://www.w3.org/2000/svg">',
    ]

    def _render_ring(segs, ro, ri, min_span_label):
        angle = 0.0
        for label, frac, color, intensity, tip, cv, cs in segs:
            span = frac * 360
            if span < 0.3:
                angle += span
                continue
            d = _slice(CX, CY, ro, ri, angle, angle + span)
            if d:
                fill = _blend(color, intensity)
                tip_s = tip.replace('"', '&quot;')
                fs = "10" if ri == RI else "9"
                parts.append(
                    f'<path d="{d}" fill="{fill}" stroke="#0d0f14" stroke-width="1.2" '
                    f'data-tip="{tip_s}" data-cv="{cv}" data-cs="{cs}" '
                    f'style="cursor:pointer;transition:opacity .12s">'
                    f'<title>{label}</title></path>'
                )
                if span >= min_span_label:
                    mid = math.radians((angle + angle + span) / 2 - 90)
                    lx = CX + (ro + ri) / 2 * math.cos(mid)
                    ly = CY + (ro + ri) / 2 * math.sin(mid)
                    parts.append(
                        f'<text x="{lx:.1f}" y="{ly:.1f}" style="font:600 {fs}px DM Sans,sans-serif;'
                        f'fill:#e8eaf0;text-anchor:middle;dominant-baseline:middle;pointer-events:none">'
                        f'{label}</text>'
                    )
            angle += span

    _render_ring(outer, RO, RM + 2, min_span_label=20)
    _render_ring(inner, RM, RI, min_span_label=15)

    parts += [
        f'<circle cx="{CX}" cy="{CY}" r="{RH}" fill="#13161e" stroke="#252a38" stroke-width="1"/>',
        f'<text id="{uid}_ct" x="{CX}" y="{CY-9}" style="font:700 22px DM Mono,monospace;'
        f'fill:#e8eaf0;text-anchor:middle;dominant-baseline:middle">{final:.0f}</text>',
        f'<text id="{uid}_cs" x="{CX}" y="{CY+13}" style="font:400 10px DM Sans,sans-serif;'
        f'fill:#5c6278;text-anchor:middle">/ 100</text>',
        '</svg>',
        f'<div id="{uid}_tip" style="position:absolute;display:none;background:#1b1f2a;'
        f'border:1px solid #2e3447;border-radius:6px;padding:5px 11px;font-size:.78rem;'
        f'color:#e8eaf0;pointer-events:none;white-space:nowrap;z-index:100;'
        f'box-shadow:0 4px 14px rgba(0,0,0,.5)"></div>',
    ]

    legend = ''.join(
        f'<span style="display:inline-flex;align-items:center;gap:5px;margin-right:12px;'
        f'font-size:.76rem;color:#9aa0b4">'
        f'<span style="width:10px;height:10px;border-radius:2px;background:{c};display:inline-block"></span>'
        f'{lbl}</span>'
        for lbl, c in [("Engagement","#4f7cff"),("Account Fit","#22c55e"),("Profile Fit","#a78bfa")]
    )
    parts.append(f'<div style="text-align:center;margin-top:10px">{legend}</div>')

    js = (
        '<script>(function(){'
        f'var w=document.getElementById("{uid}");'
        f'var tip=document.getElementById("{uid}_tip");'
        f'var ct=document.getElementById("{uid}_ct");'
        f'var cs=document.getElementById("{uid}_cs");'
        f'var orig="{final:.0f}";'
        f'var svg=document.getElementById("{uid}_svg");'
        'svg.querySelectorAll("path[data-tip]").forEach(function(p){'
        'p.addEventListener("mouseenter",function(){'
        'p.setAttribute("stroke","#ffffff");p.setAttribute("stroke-width","2.2");'
        'p.style.opacity="0.82";'
        'tip.textContent=p.dataset.tip;tip.style.display="block";'
        'ct.textContent=p.dataset.cv;cs.textContent=p.dataset.cs;'
        '});'
        'p.addEventListener("mouseleave",function(){'
        'p.setAttribute("stroke","#0d0f14");p.setAttribute("stroke-width","1.2");'
        'p.style.opacity="";'
        'tip.style.display="none";'
        'ct.textContent=orig;cs.textContent="/ 100";'
        '});'
        'p.addEventListener("mousemove",function(e){'
        'var r=w.getBoundingClientRect();'
        'var x=e.clientX-r.left+14,y=e.clientY-r.top-38;'
        'if(x+220>r.width)x=e.clientX-r.left-200;'
        'if(y<0)y=4;'
        'tip.style.left=x+"px";tip.style.top=y+"px";'
        '});'
        '});'
        '})();</script>'
        '</div>'
    )
    parts.append(js)

    return ''.join(parts)


# ── Portfolio stats ───────────────────────────────────────────────────────────

def _stats() -> dict:
    df = _ranked
    tc = df["tier"].value_counts()
    return {
        "total": len(df),
        "call_now": int(tc.get("Call Now", 0)),
        "follow_up": int(tc.get("Follow Up", 0)),
        "nurture": int(tc.get("Nurture", 0)),
        "flagged": int(tc.get("Flagged", 0)),
        "median": round(float(df["final_score"].median()), 1),
        "dq_total": int(df["dq_flag_count"].sum()),
    }


# ── Routes ────────────────────────────────────────────────────────────────────

PAGE_SIZE = 50


SORT_COLS = {
    "record_id": ("record_id", True),
    "name": ("last_name", True),
    "entity_type": ("entity_type", True),
    "tier": ("tier_sort", True),
    "final_score": ("final_score", False),
    "confidence": ("confidence", True),
    "account_name": ("account_name", True),
    "industry": ("industry", True),
    "segment": ("segment", True),
    "meaningful_30d": ("meaningful_30d", False),
    "days_since": ("days_since_last_engagement", True),
    "dq_flag_count": ("dq_flag_count", False),
}


@app.route("/")
def queue():
    f_tier = request.args.get("tier", "")
    f_entity = request.args.get("entity_type", "")
    f_industry = request.args.get("industry", "")
    f_min_score = float(request.args.get("min_score", 0) or 0)
    f_named_only = bool(request.args.get("named_only"))
    f_action = request.args.get("action", "")
    sort_by = request.args.get("sort_by", "tier")
    sort_dir = request.args.get("sort_dir", "asc")
    page = max(1, int(request.args.get("page", 1) or 1))

    df = _ranked.copy()
    if f_tier:
        df = df[df["tier"] == f_tier]
    if f_entity:
        df = df[df["entity_type"] == f_entity]
    if f_industry:
        df = df[df["industry"] == f_industry]
    if f_named_only:
        df = df[df["named_account"].fillna(False)]
    if f_min_score > 0:
        df = df[df["final_score"] >= f_min_score]
    if f_action:
        df = df[df["action_tag"] == f_action]

    # Sort
    col, _ = SORT_COLS.get(sort_by, ("tier_sort", True))
    ascending = (sort_dir == "asc")
    if col in df.columns:
        # Secondary sort: always final_score desc to break ties
        df = df.sort_values([col, "final_score"], ascending=[ascending, False], na_position="last")

    total = len(df)
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = min(page, total_pages)
    start = (page - 1) * PAGE_SIZE
    page_df = df.iloc[start: start + PAGE_SIZE]

    def _rec(row):
        days = _v(row.get("days_since_last_engagement"))
        return {
            "record_id": row["record_id"],
            "first_name": _v(row.get("first_name")) or "",
            "last_name": _v(row.get("last_name")) or "",
            "entity_type": row["entity_type"],
            "tier": row["tier"],
            "final_score": float(row["final_score"]),
            "confidence": row["confidence"],
            "account_name": _v(row.get("account_name")),
            "industry": _v(row.get("industry")),
            "segment": _v(row.get("segment")),
            "meaningful_30d": int(row.get("meaningful_30d") or 0),
            "days_since": int(days) if days is not None else None,
            "dq_flag_count": int(row.get("dq_flag_count") or 0),
            "is_suppressed": bool(row.get("is_suppressed", False)),
            "action_tag": _v(row.get("action_tag")) or "—",
        }

    records = [_rec(r) for _, r in page_df.iterrows()]

    # Build pagination URLs preserving filters + sort
    base_params = {k: v for k, v in {
        "tier": f_tier, "entity_type": f_entity, "industry": f_industry,
        "min_score": f_min_score if f_min_score else "",
        "named_only": "1" if f_named_only else "",
        "action": f_action,
        "sort_by": sort_by, "sort_dir": sort_dir,
    }.items() if v}

    def _purl(p):
        return "/?" + urlencode({**base_params, "page": p})

    def _surl(col_key):
        """URL to sort by col_key, toggling direction if already active."""
        if sort_by == col_key:
            new_dir = "desc" if sort_dir == "asc" else "asc"
        else:
            new_dir = "asc" if SORT_COLS.get(col_key, (None, True))[1] else "desc"
        p = {k: v for k, v in base_params.items() if k not in ("sort_by", "sort_dir", "page")}
        return "/?" + urlencode({**p, "sort_by": col_key, "sort_dir": new_dir})

    industries = sorted(_ranked["industry"].dropna().unique().tolist())
    action_tags = sorted(_ranked["action_tag"].dropna().unique().tolist())
    return render_template("queue.html",
        records=records, total=total, page=page, total_pages=total_pages,
        prev_url=_purl(page - 1), next_url=_purl(page + 1),
        stats=_stats(), industries=industries, action_tags=action_tags,
        sort_by=sort_by, sort_dir=sort_dir, surl=_surl,
        f_tier=f_tier, f_entity=f_entity, f_industry=f_industry,
        f_min_score=int(f_min_score), f_named_only=f_named_only, f_action=f_action,
    )


@app.route("/record/<record_id>")
def record_detail(record_id: str):
    rows = _ranked[_ranked["record_id"] == record_id]
    if rows.empty:
        return redirect(url_for("queue"))
    r = _row(rows.iloc[0])

    # Engagement history
    engagement = []
    if _cm is not None and not _cm.empty:
        sid = r.get("scoring_person_id") or record_id
        hist = _cm[_cm["scoring_person_id"] == sid].sort_values("response_date", ascending=False).head(30)
        engagement = [
            {
                "response_date": _v(row.get("response_date")),
                "campaign_type": _v(row.get("campaign_type")),
                "member_status": _v(row.get("member_status")),
                "is_automated": bool(row.get("is_automated")),
                "is_active": bool(row.get("is_active", True)),
                "campaign_id": _v(row.get("campaign_id")),
            }
            for _, row in hist.iterrows()
        ]

    sunburst = _sunburst_html(r)

    # Preserve filter context for back link
    back_url = request.referrer or url_for("queue")

    return render_template("record.html", r=r, engagement=engagement, sunburst_html=sunburst, back_url=back_url)


@app.route("/methodology")
def methodology():
    return render_template("methodology.html")


@app.route("/guide")
def guide():
    return render_template("guide.html")


@app.route("/knowledge-base")
def kb_index():
    docs = [p.stem for p in sorted(KB_DIR.glob("*.md"))]
    if not docs:
        return render_template("kb.html", docs=[], current=None, content="<p>No documents found.</p>")
    return redirect(url_for("kb_doc", doc_name=docs[0]))


@app.route("/knowledge-base/<doc_name>")
def kb_doc(doc_name: str):
    safe = re.sub(r"[^\w\-]", "", doc_name)
    path = KB_DIR / f"{safe}.md"
    docs = [p.stem for p in sorted(KB_DIR.glob("*.md"))]
    content = _markdown_to_html(path.read_text(encoding="utf-8")) if path.exists() else "<p>Document not found.</p>"
    return render_template("kb.html", docs=docs, current=safe, content=content)


# ── Startup ───────────────────────────────────────────────────────────────────
# Called at import time so gunicorn workers pick up the data without __main__.
_load()

if __name__ == "__main__":
    import webbrowser, threading
    threading.Timer(1.2, lambda: webbrowser.open("http://127.0.0.1:5000")).start()
    print("\n  BDR Readiness Score  http://127.0.0.1:5000\n")
    port = int(__import__("os").environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
