"""
SectorWindow Transition Signal Score — Full Backtest
Steps 1–6: event definition, no-lookahead scoring, eligible sample,
           metrics, baselines, and results.md

Reads production DB (read-only). Writes all outputs to backtest/outputs/.
Never modifies production tables or scoring code.

Primary cutoff:   12/31/2021
  Scoring: officer + filing data with period_end ≤ 12/31/2020 (tax_year ≤ 2020)
  12-month outcome: transitions detected in 2021  (N ≈ 29,000)
  24-month outcome: transitions in 2021 or 2022   (N ≈ 29,200; 2022 sparse — caveat noted)

Secondary cutoff: 12/31/2020  (cross-check only; genuine 24-mo window)
  Scoring: period_end ≤ 12/31/2019 (tax_year ≤ 2019)
  12-month outcome: 2020  (N ≈ 9,540)
  24-month outcome: 2021  (N ≈ 8,795)
"""

from __future__ import annotations

import json
import math
import os
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional
import re

import duckdb
import pandas as pd
import numpy as np
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = str(ROOT / "data" / "dej_intelligence.duckdb")
OUT_DIR = Path(__file__).resolve().parent / "outputs"
OUT_DIR.mkdir(exist_ok=True)

# ── Cutoff config ────────────────────────────────────────────────────────────
# Primary: 12/31/2021
PRIMARY_CUTOFF_DATE = "2021-12-31"
PRIMARY_PRE_YEAR    = 2020   # last tax_year of public officer data
PRIMARY_12MO_YEAR   = 2021   # 12-month outcome
PRIMARY_24MO_YEAR   = 2022   # 24-month outcome (sparse)

# Secondary: 12/31/2020
SECONDARY_PRE_YEAR  = 2019
SECONDARY_12MO_YEAR = 2020
SECONDARY_24MO_YEAR = 2021

# ── Title normalization ──────────────────────────────────────────────────────
# Titles that mean "current top executive" — used to identify the CEO/ED/President
TOP_EXEC_PATTERNS = re.compile(
    r"(EXECUTIVE DIRECTOR|EXEC\.?\s*DIR|CHIEF EXECUTIVE|CEO|C\.E\.O\.|"
    r"PRESIDENT(?!\s*(ELECT|BOARD|PAST|IMMEDIATE|PRESIDENTELECT))|"
    r"HEAD OF SCHOOL|HEADMASTER|SUPERINTENDENT|MANAGING DIRECTOR)",
    re.IGNORECASE,
)

# Titles that indicate a PAST or INCOMING role — exclude from "current CEO"
EXCLUDE_TITLE_PATTERNS = re.compile(
    r"(PAST\s|IMMEDIATE\s+PAST|FORMER|ELECT\b|PRESIDENTELECT|"
    r"INCOMING|EMERITUS|BOARD\s+PRESIDENT)",
    re.IGNORECASE,
)

INTERIM_PATTERNS = re.compile(
    r"(INTERIM|ACTING|TEMPORARY|TEMP\.?\s|PROVISIONAL)",
    re.IGNORECASE,
)

REVENUE_BANDS = [
    ("< $1M",     0,         1_000_000),
    ("$1M–$5M",   1_000_000, 5_000_000),
    ("$5M–$25M",  5_000_000, 25_000_000),
    ("> $25M",    25_000_000, 1e18),
]

DCMDVA = {"DC", "MD", "VA"}


# ════════════════════════════════════════════════════════════════════════════
# Shared scoring functions  (mirror of production, no DB side-effects)
# ════════════════════════════════════════════════════════════════════════════

TIER_THRESHOLDS_CORRECTED = [("imminent", 80), ("elevated", 60), ("watch", 40), ("stable", 0)]
# Phase-1-only tier thresholds (from compute_signals.py) — used as a secondary lens
# for orgs that are mostly scoring on financial signals only (LOW confidence)
TIER_THRESHOLDS_P1 = [("imminent", 55), ("high", 40), ("elevated", 20), ("low", 0)]

TENURE_SCORE_TABLE = [
    (0,   1,  20),
    (2,   2,  15),
    (3,   4,  10),
    (5,   6,   8),
    (7,  10,  12),
    (11, 14,  16),
    (15, 999, 20),
]

CONFIDENCE_MULTIPLIER = {"HIGH": 1.0, "MEDIUM": 0.5, "LOW": 0.0}


def assign_tier(score: int) -> str:
    for tier, threshold in TIER_THRESHOLDS_CORRECTED:
        if score >= threshold:
            return tier
    return "stable"


def score_revenue_trend(cagr) -> tuple[int, str]:
    if cagr is None or (isinstance(cagr, float) and math.isnan(cagr)):
        return 0, "unknown"
    cagr = float(cagr)
    if cagr <= -0.30: return 25, "steep_decline"
    if cagr <= -0.15: return 20, "decline"
    if cagr <= -0.05: return 12, "soft_decline"
    if cagr <= 0.05:  return  5, "flat"
    if cagr <= 0.15:  return  2, "growth"
    return 0, "strong_growth"


def score_comp_trajectory(pct) -> tuple[int, str]:
    if pct is None or (isinstance(pct, float) and math.isnan(pct)):
        return 0, "unknown"
    pct = float(pct)
    if pct <= -0.20: return 15, "declining"
    if pct <= -0.05: return 10, "softening"
    if pct <= 0.05:  return  8, "flat"
    if pct <= 0.20:  return  3, "growing"
    return 0, "strong_growth"


def score_deficit_years(consecutive: int) -> int:
    if consecutive >= 3: return 30
    if consecutive == 2: return 20
    if consecutive == 1: return 10
    return 0


def tenure_to_points(years) -> int:
    if years is None:
        return 5
    try:
        years = float(years)
    except (TypeError, ValueError):
        return 5
    for min_y, max_y, pts in TENURE_SCORE_TABLE:
        if min_y <= years <= max_y:
            return pts
    return 5


def comp_pct_to_points(pct) -> int:
    if pct is None:
        return 3
    try:
        pct = float(pct)
    except (TypeError, ValueError):
        return 3
    if pct >= 90: return 8
    if pct >= 75: return 5
    if pct >= 25: return 3
    if pct >= 10: return 6
    return 9


def compute_deficit_streaks(deficit_rows: list[tuple]) -> dict[str, int]:
    """Mirror of production compute_deficit_streaks, restricted to allowed years."""
    streaks: dict[str, int] = {}
    current_ein = None
    streak = 0
    streak_broken = False
    for ein, _yr, is_deficit in sorted(deficit_rows, key=lambda r: (r[0], -r[1])):
        if ein != current_ein:
            if current_ein is not None:
                streaks[current_ein] = streak
            current_ein, streak, streak_broken = ein, 0, False
        if not streak_broken:
            if is_deficit:
                streak += 1
            else:
                streak_broken = True
    if current_ein is not None:
        streaks[current_ein] = streak
    return streaks


# ════════════════════════════════════════════════════════════════════════════
# Step 1 — Transition event detection
# ════════════════════════════════════════════════════════════════════════════

def name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def is_interim(title: str) -> bool:
    return bool(INTERIM_TITLES_RE.search(title)) if title else False

INTERIM_TITLES_RE = INTERIM_PATTERNS


def pick_primary_exec(rows: list[dict]) -> Optional[dict]:
    """
    From a list of is_top_officer rows for one (ein, year), select the
    'current primary executive':
      1. Exclude PAST/ELECT/FORMER/BOARD roles if any non-excluded row exists.
      2. Among remaining, pick highest comp_reportable_org (then comp_total).
    Returns None if no rows.
    """
    if not rows:
        return None

    # Try to filter out past/elect titles
    current = [r for r in rows if not EXCLUDE_TITLE_PATTERNS.search(r["title_normalized"] or "")]
    pool = current if current else rows  # fall back to all if everything filtered

    # Pick by compensation
    pool_sorted = sorted(
        pool,
        key=lambda r: (
            r["comp_reportable_org"] or 0,
            r["comp_total"] or 0,
        ),
        reverse=True,
    )
    return pool_sorted[0]


def build_exec_map(con: duckdb.DuckDBPyConnection, max_year: int) -> dict[tuple, list[dict]]:
    """
    Returns {(ein, tax_year): [officer_rows]} for all years <= max_year,
    restricted to is_top_officer = true.
    """
    rows = con.execute(f"""
        select ein, tax_year, person_name_normalized, title_normalized,
               coalesce(comp_reportable_org, 0) as comp_reportable_org,
               coalesce(comp_total, 0) as comp_total
        from officers
        where is_top_officer = true
          and tax_year <= {max_year}
          and person_name_normalized is not null
          and trim(person_name_normalized) != ''
        order by ein, tax_year
    """).fetchall()

    result: dict[tuple, list[dict]] = defaultdict(list)
    for ein, yr, name, title, comp_org, comp_tot in rows:
        result[(ein, yr)].append({
            "ein": ein, "tax_year": yr,
            "person_name_normalized": name,
            "title_normalized": title or "",
            "comp_reportable_org": comp_org,
            "comp_total": comp_tot,
        })
    return result


def step1_detect_transitions(
    con: duckdb.DuckDBPyConnection,
    all_years_max: int = 2022,
    fuzzy_threshold: float = 0.90,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Detect top-exec transitions between consecutive filing years.
    Returns (transitions_df, title_only_df).

    transitions_df: each row is a year-over-year change where the person changed.
    title_only_df:  year-over-year changes where same person, different title.
    """
    print("Step 1: Loading officer data for transition detection...")
    exec_map = build_exec_map(con, max_year=all_years_max)

    # Get all EINs and years from the map
    all_keys = sorted(exec_map.keys())  # (ein, year)

    transitions = []
    title_only  = []

    seen_pairs: set[tuple] = set()
    for (ein, yr_new) in all_keys:
        yr_old = yr_new - 1
        if (ein, yr_old) not in exec_map:
            continue  # no consecutive prior year → skip
        pair_key = (ein, yr_old, yr_new)
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)

        old_exec = pick_primary_exec(exec_map[(ein, yr_old)])
        new_exec = pick_primary_exec(exec_map[(ein, yr_new)])
        if old_exec is None or new_exec is None:
            continue

        name_old = old_exec["person_name_normalized"]
        name_new = new_exec["person_name_normalized"]
        title_old = old_exec["title_normalized"]
        title_new = new_exec["title_normalized"]

        sim = name_similarity(name_old, name_new)
        same_person = (sim >= fuzzy_threshold)
        is_int_old = bool(INTERIM_PATTERNS.search(title_old))
        is_int_new = bool(INTERIM_PATTERNS.search(title_new))

        base = {
            "ein": ein,
            "year_before": yr_old,
            "year_after": yr_new,
            "exec_name_before": name_old,
            "exec_name_after": name_new,
            "title_before": title_old,
            "title_after": title_new,
            "name_similarity": round(sim, 4),
            "is_interim_before": is_int_old,
            "is_interim_after": is_int_new,
        }

        if same_person:
            if title_old != title_new:
                title_only.append({**base, "change_type": "title_only"})
        else:
            transitions.append({
                **base,
                "change_type": "transition",
                "is_interim": is_int_new,
            })

    trans_df = pd.DataFrame(transitions)
    title_df  = pd.DataFrame(title_only)

    print(f"  Transitions detected: {len(trans_df):,}")
    print(f"  Title-only changes:   {len(title_df):,}")
    return trans_df, title_df


# ════════════════════════════════════════════════════════════════════════════
# Step 2 — No-lookahead scoring
# ════════════════════════════════════════════════════════════════════════════

def step2_score_at_cutoff(
    con: duckdb.DuckDBPyConnection,
    pre_year: int,
) -> pd.DataFrame:
    """
    Re-score each org using ONLY filings and officer data public at the cutoff.
    Replicates production logic exactly (financial Phase 1 + leadership Phase 2
    + coverage-confidence discount).

    'Public at cutoff' = period_end + 12 months <= cutoff_date
                       = period_end <= (cutoff - 1 year)
                       = period_end <= 12/31/{pre_year}
    """
    print(f"Step 2: Scoring at cutoff (pre_year ≤ {pre_year})...")

    # ── Financial signals (Phase 1) ───────────────────────────────────────
    # Only use filings with period_end <= 12/31/{pre_year} and partial_year=false
    financial_rows = con.execute(f"""
        with
        deduped as (
            select *,
                   row_number() over (
                       partition by ein, tax_year
                       order by period_end desc nulls last, total_revenue desc nulls last
                   ) as rn
            from filings
            where partial_year = false
              and total_revenue is not null
              and period_end <= DATE '{pre_year}-12-31'
        ),
        clean as (
            select ein, tax_year, total_revenue, total_expenses, comp_employees,
                   period_end
            from deduped where rn = 1
        ),
        windowed as (
            select
                ein, tax_year, total_revenue, total_expenses, comp_employees,
                lag(total_revenue,  1) over w as prev_revenue,
                lag(comp_employees, 1) over w as prev_comp,
                lag(total_revenue,  2) over w as revenue_2yr_ago,
                lag(comp_employees, 2) over w as comp_2yr_ago,
                count(*)      over (partition by ein) as years_of_data,
                max(tax_year) over (partition by ein) as most_recent_year
            from clean
            window w as (partition by ein order by tax_year)
        )
        select
            ein, tax_year, total_revenue, total_expenses, comp_employees,
            years_of_data, most_recent_year,
            case when revenue_2yr_ago > 0 and total_revenue is not null
                 then power(cast(total_revenue as float) / cast(revenue_2yr_ago as float), 0.5) - 1.0
            end as revenue_cagr_3yr,
            case when comp_2yr_ago > 0 and comp_employees is not null
                 then (cast(comp_employees as float) - cast(comp_2yr_ago as float)) / cast(comp_2yr_ago as float)
            end as comp_pct_change_3yr,
            case when total_expenses > total_revenue then 1 else 0 end as is_deficit
        from windowed
        where tax_year = most_recent_year
          and years_of_data >= 2
    """).fetchdf()
    print(f"  Financial rows (Phase 1): {len(financial_rows):,}")

    # Deficit streaks
    deficit_raw = con.execute(f"""
        with
        deduped as (
            select *,
                   row_number() over (
                       partition by ein, tax_year
                       order by period_end desc nulls last, total_revenue desc nulls last
                   ) as rn
            from filings
            where partial_year = false
              and total_revenue is not null
              and total_expenses is not null
              and period_end <= DATE '{pre_year}-12-31'
        ),
        clean as (
            select ein, tax_year, total_revenue, total_expenses
            from deduped where rn = 1
        ),
        flags as (
            select ein, tax_year,
                   case when total_expenses > total_revenue then 1 else 0 end as is_deficit,
                   max(tax_year) over (partition by ein) as most_recent_year
            from clean
        )
        select ein, tax_year, is_deficit
        from flags
        where tax_year >= most_recent_year - 4
        order by ein, tax_year desc
    """).fetchall()
    deficit_streaks = compute_deficit_streaks(deficit_raw)

    # ── Leadership signals (Phase 2) ──────────────────────────────────────
    # CEO tenure, restricted to tax_year <= pre_year
    tenure_rows = con.execute(f"""
        with top_officers as (
            select ein, tax_year, person_name_normalized, title_normalized,
                   coalesce(comp_reportable_org, 0) as comp_org,
                   coalesce(comp_total, 0) as comp_tot,
                   row_number() over (
                       partition by ein, tax_year
                       order by coalesce(comp_reportable_org, 0) desc,
                                coalesce(comp_total, 0) desc
                   ) as rk
            from officers
            where is_top_officer = true
              and tax_year <= {pre_year}
              and person_name_normalized is not null
              and trim(person_name_normalized) != ''
        ),
        ranked as (
            select ein, tax_year, person_name_normalized as ceo_name,
                   title_normalized as ceo_title,
                   comp_org as ceo_comp_org,
                   comp_tot as ceo_comp_total
            from top_officers where rk = 1
        ),
        with_lag as (
            select ein, tax_year, ceo_name, ceo_title, ceo_comp_org, ceo_comp_total,
                   lag(ceo_name)    over (partition by ein order by tax_year) as prev_name,
                   lag(tax_year)    over (partition by ein order by tax_year) as prev_yr
            from ranked
        ),
        continuity as (
            select ein, tax_year, ceo_name, ceo_title, ceo_comp_org, ceo_comp_total,
                   case
                       when prev_name is null then 1
                       when ceo_name = prev_name and tax_year = prev_yr + 1 then 1
                       when tax_year = prev_yr + 1 then 0
                       else null
                   end as same_ceo
            from with_lag
        ),
        groups as (
            select ein, tax_year, ceo_name, ceo_title, ceo_comp_org, ceo_comp_total, same_ceo,
                   sum(case when same_ceo = 0 or same_ceo is null then 1 else 0 end)
                       over (partition by ein order by tax_year
                             rows between unbounded preceding and current row) as tenure_grp
            from continuity
        ),
        tenure_calc as (
            select ein, tax_year, ceo_name, ceo_title, ceo_comp_org, ceo_comp_total,
                   count(*) over (
                       partition by ein, tenure_grp
                       order by tax_year
                       rows between unbounded preceding and current row
                   ) as ceo_tenure_years,
                   max(tax_year) over (partition by ein) as latest_year
            from groups
            where same_ceo is not null
        )
        select ein, ceo_name, ceo_title, ceo_comp_org, ceo_comp_total,
               ceo_tenure_years,
               count(*) over (partition by ein) as data_years
        from tenure_calc
        where tax_year = latest_year
    """).fetchdf()
    print(f"  CEO tenure rows (Phase 2): {len(tenure_rows):,}")

    # Comp percentile within NTEE major group
    org_ntee = con.execute("""
        select ein, ntee_code, left(ntee_code, 1) as ntee_major
        from organizations where ntee_code is not null
    """).fetchdf()

    tenure_with_ntee = tenure_rows.merge(org_ntee[["ein","ntee_major"]], on="ein", how="left")
    tenure_with_ntee["comp_pct"] = None
    for ntee_grp, grp in tenure_with_ntee.groupby("ntee_major"):
        valid = grp[grp.ceo_comp_org > 0].copy()
        if len(valid) == 0:
            continue
        pcts = valid["ceo_comp_org"].rank(pct=True) * 100
        tenure_with_ntee.loc[valid.index, "comp_pct"] = pcts.values

    # Build lookup
    tenure_lookup = tenure_with_ntee.set_index("ein").to_dict(orient="index")

    # XML coverage per EIN (for confidence discount)
    xml_years = con.execute(f"""
        select ein, count(distinct tax_year) as xml_yrs
        from officers
        where is_top_officer = true
          and tax_year <= {pre_year}
        group by ein
    """).fetchdf().set_index("ein")["xml_yrs"].to_dict()

    # ── Assemble scores ───────────────────────────────────────────────────
    scores = []
    for _, row in financial_rows.iterrows():
        ein = row["ein"]

        # Phase 1
        rev_pts, rev_lbl = score_revenue_trend(row["revenue_cagr_3yr"])
        comp_pts, comp_lbl = score_comp_trajectory(row["comp_pct_change_3yr"])
        def_streak = deficit_streaks.get(ein, 0)
        def_pts = score_deficit_years(def_streak)
        p1_score = rev_pts + comp_pts + def_pts   # 0-70

        # Phase 2
        t = tenure_lookup.get(ein)
        if t:
            tenure_yrs = t["ceo_tenure_years"]
            ceo_comp = t["ceo_comp_org"]
            comp_pct  = t.get("comp_pct")
            ceo_name  = t["ceo_name"]
            data_yrs  = t["data_years"]
        else:
            tenure_yrs = ceo_comp = comp_pct = ceo_name = data_yrs = None

        tenure_pts = tenure_to_points(tenure_yrs)
        comp_p_pts = comp_pct_to_points(comp_pct)

        xml_yrs = xml_years.get(ein, 0)
        if xml_yrs >= 3:
            confidence = "HIGH"
        elif xml_yrs == 2:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        multiplier = CONFIDENCE_MULTIPLIER[confidence]
        adj_tenure = round(tenure_pts * multiplier)
        adj_comp_p = round(comp_p_pts * multiplier)

        total_v2 = p1_score + tenure_pts + comp_p_pts          # uncorrected
        corrected = min(99, max(0, p1_score + adj_tenure + adj_comp_p))
        tier = assign_tier(corrected)

        # Also compute Phase-1-only tier (using compute_signals.py thresholds)
        p1_tier = "low"
        for t, thresh in TIER_THRESHOLDS_P1:
            if p1_score >= thresh:
                p1_tier = t
                break

        scores.append({
            "ein": ein,
            "p1_score": p1_score,
            "rev_pts": rev_pts,
            "comp_pts": comp_pts,
            "def_pts": def_pts,
            "def_streak": def_streak,
            "rev_cagr": row["revenue_cagr_3yr"],
            "comp_pct_change": row["comp_pct_change_3yr"],
            "total_revenue": row["total_revenue"],
            "most_recent_year": row["most_recent_year"],
            "ceo_name": ceo_name,
            "ceo_tenure_yrs": tenure_yrs,
            "tenure_pts_raw": tenure_pts,
            "comp_p_pts_raw": comp_p_pts,
            "confidence": confidence,
            "xml_yrs": xml_yrs,
            "total_score_v2": total_v2,
            "score_corrected": corrected,
            "tier_corrected": tier,
            "p1_tier": p1_tier,
            "p2_pts_adj": adj_tenure + adj_comp_p,
        })

    scores_df = pd.DataFrame(scores)
    print(f"  Scores computed: {len(scores_df):,}")
    return scores_df


# ════════════════════════════════════════════════════════════════════════════
# Step 3 — Eligible sample
# ════════════════════════════════════════════════════════════════════════════

def step3_eligible_sample(
    con: duckdb.DuckDBPyConnection,
    scores_df: pd.DataFrame,
    trans_df: pd.DataFrame,
    pre_year: int,
    outcome_12mo: int,
    outcome_24mo: int,
) -> tuple[pd.DataFrame, dict]:
    """
    Returns the eligible sample DataFrame and a drop-reason summary.
    An org is eligible if:
      - Has a backtest score (pre-cutoff financial data)
      - Has at least one officer filing in the outcome window
    """
    print(f"Step 3: Building eligible sample (pre_year={pre_year}, "
          f"12mo={outcome_12mo}, 24mo={outcome_24mo})...")

    # Set of EINs with officer data in each outcome window
    eins_12mo = set(trans_df.loc[trans_df["year_after"] == outcome_12mo, "ein"])
    # For 24-month: transitions where year_before is pre_year AND year_after is outcome_24mo,
    #   OR any org that had a 12-mo transition that extends to 24-mo
    # Simpler: flag whether *any* transition occurred in [outcome_12mo, outcome_24mo]
    eins_24mo_pool = set(trans_df.loc[
        (trans_df["year_after"] >= outcome_12mo) &
        (trans_df["year_after"] <= outcome_24mo), "ein"
    ])

    # Also need orgs that were OBSERVED in outcome window (even if no transition)
    # = orgs with any officer record in outcome years
    eins_observed_12mo = set(con.execute(f"""
        select distinct ein from officers
        where is_top_officer=true and tax_year={outcome_12mo}
    """).fetchdf()["ein"])

    eins_observed_24mo = set(con.execute(f"""
        select distinct ein from officers
        where is_top_officer=true and tax_year<={outcome_24mo} and tax_year>={outcome_12mo}
    """).fetchdf()["ein"])

    # Org metadata for revenue bands and state
    org_meta = con.execute("""
        select ein, name, state, ntee_code, ntee_category, status,
               revenue_amount, asset_amount
        from organizations
    """).fetchdf().set_index("ein")

    # Revoked/dissolved orgs
    revoked_eins = set(con.execute(
        "select ein from organizations where status != 'active'"
    ).fetchdf()["ein"])

    # Build eligible
    n_no_score     = 0
    n_no_outcome   = 0
    n_dissolved    = 0
    eligible_rows  = []

    scored_eins = set(scores_df["ein"])

    # Restrict to orgs that have officer data in BOTH pre-cutoff AND outcome window.
    # An org with no pre-cutoff officer data can never show a transition; including
    # it as a "non-transition" dilutes the base rate and masks the signal.
    eins_with_pre_officer = set(con.execute(f"""
        select distinct ein from officers where is_top_officer=true and tax_year<={pre_year}
    """).fetchdf()["ein"])

    # All candidate EINs: must have PRE-cutoff officer data to be evaluable
    all_candidate_eins = eins_with_pre_officer

    for ein in all_candidate_eins:
        in_scores = ein in scored_eins
        in_12mo   = ein in eins_observed_12mo
        in_24mo   = ein in eins_observed_24mo

        if ein in revoked_eins:
            n_dissolved += 1
            continue
        if not in_scores:
            n_no_score += 1
            continue
        if not in_12mo:
            n_no_outcome += 1
            continue

        row = scores_df[scores_df["ein"] == ein].iloc[0].to_dict()

        # Outcome flags
        trans_12mo = trans_df[
            (trans_df["ein"] == ein) & (trans_df["year_after"] == outcome_12mo)
        ]
        trans_24mo = trans_df[
            (trans_df["ein"] == ein) &
            (trans_df["year_after"] >= outcome_12mo) &
            (trans_df["year_after"] <= outcome_24mo)
        ]

        had_transition_12mo = len(trans_12mo) > 0
        had_transition_24mo = len(trans_24mo) > 0
        is_interim_12mo = bool(trans_12mo["is_interim"].any()) if had_transition_12mo else False

        # Org metadata
        meta = org_meta.loc[ein] if ein in org_meta.index else {}
        try:
            raw_rev = meta["revenue_amount"] if isinstance(meta, pd.Series) else None
            rev = float(raw_rev) if raw_rev is not None else 0.0
        except (TypeError, ValueError):
            rev = 0.0

        rev_band = "unknown"
        for label, lo, hi in REVENUE_BANDS:
            if lo <= rev < hi:
                rev_band = label
                break

        state = meta.get("state", "") if isinstance(meta, pd.Series) else ""
        is_dcmdva = state in DCMDVA

        eligible_rows.append({
            **row,
            "had_transition_12mo": had_transition_12mo,
            "had_transition_24mo": had_transition_24mo,
            "is_interim_12mo": is_interim_12mo,
            "observed_in_24mo": in_24mo,
            "org_name": meta.get("name", "") if isinstance(meta, pd.Series) else "",
            "state": state,
            "is_dcmdva": is_dcmdva,
            "revenue_amount": rev,
            "rev_band": rev_band,
            "ntee_code": meta.get("ntee_code", "") if isinstance(meta, pd.Series) else "",
        })

    eligible_df = pd.DataFrame(eligible_rows)

    drop_summary = {
        "dissolved_or_merged": n_dissolved,
        "no_financial_score": n_no_score,
        "no_outcome_window_data": n_no_outcome,
        "eligible": len(eligible_df),
    }
    print(f"  Eligible: {len(eligible_df):,}")
    print(f"  Dropped — dissolved: {n_dissolved:,}, no financial data: {n_no_score:,}, "
          f"no outcome window: {n_no_outcome:,}")
    return eligible_df, drop_summary


# ════════════════════════════════════════════════════════════════════════════
# Step 4 — Metrics
# ════════════════════════════════════════════════════════════════════════════

def compute_lift_table_col(
    df: pd.DataFrame, outcome_col: str, tier_col: str, tiers: list[str]
) -> pd.DataFrame:
    total = len(df)
    n_trans = df[outcome_col].sum()
    base_rate = n_trans / total if total > 0 else 0
    rows = []
    for tier in tiers:
        sub = df[df[tier_col] == tier]
        n = len(sub)
        if n == 0:
            rows.append({"tier": tier, "n": 0, "transitions": 0, "rate": 0.0, "lift": 0.0})
            continue
        t = sub[outcome_col].sum()
        rate = t / n
        lift = rate / base_rate if base_rate > 0 else 0
        rows.append({"tier": tier, "n": n, "transitions": int(t),
                     "rate": round(rate, 4), "lift": round(lift, 2)})
    return pd.DataFrame(rows)


def compute_lift_table(df: pd.DataFrame, outcome_col: str) -> pd.DataFrame:
    return compute_lift_table_col(df, outcome_col, "tier_corrected",
                                  ["imminent", "elevated", "watch", "stable"])


def precision_at_k(df: pd.DataFrame, outcome_col: str, k: int) -> float:
    top_k = df.nlargest(k, "score_corrected")
    return top_k[outcome_col].mean()


def auc_score(df: pd.DataFrame, outcome_col: str) -> float:
    if df[outcome_col].nunique() < 2:
        return float("nan")
    try:
        return roc_auc_score(df[outcome_col].astype(int), df["score_corrected"])
    except Exception:
        return float("nan")


def step4_metrics(eligible_df: pd.DataFrame) -> dict:
    print("Step 4: Computing metrics...")
    results = {}

    for window, col in [("12mo", "had_transition_12mo"), ("24mo", "had_transition_24mo")]:
        sub = eligible_df.copy()
        if window == "24mo":
            sub = sub[sub["observed_in_24mo"]].copy()
        n = len(sub)
        base_rate = sub[col].mean()

        lift_tbl = compute_lift_table(sub, col)
        # Phase-1-only tier lift (uses score_corrected but p1_tier tiers)
        lift_tbl_p1 = compute_lift_table_col(sub, col, "p1_tier",
                                              ["imminent", "high", "elevated", "low"])
        p100 = precision_at_k(sub, col, min(100, n))
        p500 = precision_at_k(sub, col, min(500, n))
        auc  = auc_score(sub, col)

        # By revenue band — use Phase-1 imminent for band analysis (more populated)
        band_rows = []
        for band, lo, hi in REVENUE_BANDS:
            bsub = sub[(sub["revenue_amount"] >= lo) & (sub["revenue_amount"] < hi)]
            if len(bsub) < 20:
                continue
            br = bsub[col].mean()
            imm = bsub[bsub["p1_tier"] == "imminent"]
            imm_rate = imm[col].mean() if len(imm) > 0 else 0
            lift = imm_rate / br if br > 0 else 0
            band_rows.append({
                "band": band, "n": len(bsub), "base_rate": round(br, 4),
                "imminent_n": len(imm), "imminent_rate": round(imm_rate, 4),
                "imminent_lift": round(lift, 2)
            })
        by_band = pd.DataFrame(band_rows)

        # DC/MD/VA — use Phase-1 imminent
        dmv = sub[sub["is_dcmdva"]]
        dmv_br = dmv[col].mean() if len(dmv) > 0 else 0
        dmv_imm = dmv[dmv["p1_tier"] == "imminent"]
        dmv_imm_rate = dmv_imm[col].mean() if len(dmv_imm) > 0 else 0

        results[window] = {
            "n": n,
            "base_rate": round(base_rate, 4),
            "lift_table": lift_tbl,
            "lift_table_p1": lift_tbl_p1,
            "p100": round(p100, 4),
            "p500": round(p500, 4),
            "auc": round(auc, 4) if not math.isnan(auc) else None,
            "by_band": by_band,
            "dmv_n": len(dmv),
            "dmv_base_rate": round(dmv_br, 4),
            "dmv_imminent_n": len(dmv_imm),
            "dmv_imminent_rate": round(dmv_imm_rate, 4),
            "dmv_imminent_lift": round(dmv_imm_rate / dmv_br, 2) if dmv_br > 0 else 0,
        }

    return results


# ════════════════════════════════════════════════════════════════════════════
# Step 5 — Baselines
# ════════════════════════════════════════════════════════════════════════════

def step5_baselines(eligible_df: pd.DataFrame) -> dict:
    """
    Compare score against:
      (a) random
      (b) tenure-only rule
      (c) tenure + org size (revenue band)
      (d) financial component only (p1_score)
      (e) leadership component only (p2_pts_adj)
    """
    print("Step 5: Computing baselines...")
    results = {}

    for window, col in [("12mo", "had_transition_12mo"), ("24mo", "had_transition_24mo")]:
        sub = eligible_df.copy()
        if window == "24mo":
            sub = sub[sub["observed_in_24mo"]].copy()
        n = len(sub)
        if n == 0:
            results[window] = {}
            continue
        base_rate = sub[col].mean()
        actual_auc = auc_score(sub, col)

        # (a) Random baseline — expected AUC = 0.50
        rng = np.random.default_rng(42)
        rand_scores = rng.random(n)
        try:
            rand_auc = roc_auc_score(sub[col].astype(int), rand_scores)
        except Exception:
            rand_auc = float("nan")

        # (b) Tenure-only rule: flag if tenure is None, 0-2 yrs, or 11+
        def tenure_risk(t) -> int:
            if t is None:
                return 1
            t = float(t)
            return 1 if (t <= 2 or t >= 11) else 0

        sub["tenure_flag"] = sub["ceo_tenure_yrs"].apply(tenure_risk)
        try:
            tenure_auc = roc_auc_score(sub[col].astype(int), sub["tenure_flag"])
        except Exception:
            tenure_auc = float("nan")
        tenure_rate = sub[sub["tenure_flag"] == 1][col].mean()
        tenure_lift = tenure_rate / base_rate if base_rate > 0 else 0

        # (c) Tenure + size (revenue band code as numeric proxy)
        band_map = {"< $1M": 0, "$1M–$5M": 1, "$5M–$25M": 2, "> $25M": 3, "unknown": 1}
        sub["band_code"] = sub["rev_band"].map(band_map)
        # Size risk: small orgs (<$1M) are higher risk; use inverse band_code
        sub["size_risk"] = (3 - sub["band_code"]) / 3   # 0.0 to 1.0
        sub["tenure_size_score"] = sub["tenure_flag"] * 0.7 + sub["size_risk"] * 0.3
        try:
            tenure_size_auc = roc_auc_score(sub[col].astype(int), sub["tenure_size_score"])
        except Exception:
            tenure_size_auc = float("nan")

        # (d) Financial only (p1_score, 0-70)
        try:
            fin_auc = roc_auc_score(sub[col].astype(int), sub["p1_score"])
        except Exception:
            fin_auc = float("nan")
        fin_p100 = precision_at_k(sub.copy().assign(score_corrected=sub["p1_score"]), col, min(100, n))

        # (e) Leadership only (p2_pts_adj, 0-30)
        try:
            lead_auc = roc_auc_score(sub[col].astype(int), sub["p2_pts_adj"])
        except Exception:
            lead_auc = float("nan")

        results[window] = {
            "n": n,
            "base_rate": round(base_rate, 4),
            "full_model_auc": round(actual_auc, 4) if not math.isnan(actual_auc) else None,
            "random_auc": round(rand_auc, 4) if not math.isnan(rand_auc) else None,
            "tenure_only_auc": round(tenure_auc, 4) if not math.isnan(tenure_auc) else None,
            "tenure_only_lift": round(tenure_lift, 2),
            "tenure_size_auc": round(tenure_size_auc, 4) if not math.isnan(tenure_size_auc) else None,
            "financial_only_auc": round(fin_auc, 4) if not math.isnan(fin_auc) else None,
            "financial_only_p100": round(fin_p100, 4),
            "leadership_only_auc": round(lead_auc, 4) if not math.isnan(lead_auc) else None,
        }

    return results


# ════════════════════════════════════════════════════════════════════════════
# Pass / Fail criteria
# ════════════════════════════════════════════════════════════════════════════

PASS_CRITERIA = {
    "imminent_lift_12mo_min": 2.0,
    "imminent_lift_24mo_min": 2.0,
    "imminent_lift_bands_min": 2.0,  # must hold in >1 revenue band
}


def evaluate_pass_fail(metrics: dict) -> dict:
    """Evaluate pass/fail using both the full-model (corrected) and Phase-1 tier tables."""
    pf = {}
    for window in ["12mo", "24mo"]:
        m = metrics.get(window, {})
        # Try Phase-1 tier table first (better populated at this cutoff)
        lt_p1 = m.get("lift_table_p1", pd.DataFrame())
        lt_full = m.get("lift_table", pd.DataFrame())

        # Use P1 tier if it has meaningful imminent counts, else fall back to full
        p1_imm_n = int(lt_p1[lt_p1["tier"] == "imminent"]["n"].values[0]) if not lt_p1.empty else 0
        full_imm_n = int(lt_full[lt_full["tier"] == "imminent"]["n"].values[0]) if not lt_full.empty else 0

        # Pick the tier table with more imminent orgs (more stable estimate)
        lt = lt_p1 if p1_imm_n >= full_imm_n else lt_full
        tier_system = "P1 (≥55)" if p1_imm_n >= full_imm_n else "full (≥80)"

        imm = lt[lt["tier"] == "imminent"]
        lift = float(imm["lift"].values[0]) if len(imm) > 0 else 0
        imm_n = int(imm["n"].values[0]) if len(imm) > 0 else 0
        min_req = PASS_CRITERIA[f"imminent_lift_{window}_min"]
        passes = lift >= min_req
        pf[window] = {
            "imminent_lift": round(lift, 2),
            "imminent_n": imm_n,
            "tier_system": tier_system,
            "required": min_req,
            "pass": passes,
            "reason": f"lift={lift:.2f} ({tier_system}) ({'≥' if passes else '<'} {min_req}), N={imm_n}",
        }

    # Must hold in >1 revenue band (use 12mo)
    m12 = metrics.get("12mo", {})
    by_band = m12.get("by_band", pd.DataFrame())
    bands_above = 0
    if not by_band.empty:
        bands_above = int((by_band["imminent_lift"] >= PASS_CRITERIA["imminent_lift_bands_min"]).sum())
    pf["multi_band"] = {
        "bands_above_2x": bands_above,
        "pass": bands_above > 1,
        "reason": f"{bands_above} revenue band(s) show imminent lift ≥ {PASS_CRITERIA['imminent_lift_bands_min']}x",
    }

    pf["overall"] = all(v["pass"] for v in pf.values())
    return pf


# ════════════════════════════════════════════════════════════════════════════
# Step 6 — results.md
# ════════════════════════════════════════════════════════════════════════════

def step6_write_results(
    metrics: dict,
    baselines: dict,
    pass_fail: dict,
    drop_summary: dict,
    eligible_df: pd.DataFrame,
    trans_df: pd.DataFrame,
    title_df: pd.DataFrame,
    scores_df: pd.DataFrame,
    cutoff_label: str,
    metrics_sec: dict | None = None,
    baselines_sec: dict | None = None,
    eligible_sec: pd.DataFrame | None = None,
) -> None:
    overall = "PASS" if pass_fail.get("overall") else "FAIL"
    base_12 = metrics["12mo"]["base_rate"]
    base_24 = metrics["24mo"]["base_rate"]

    imm_lift_12 = pass_fail["12mo"]["imminent_lift"]
    imm_lift_24 = pass_fail["24mo"]["imminent_lift"]
    tier_sys_12 = pass_fail["12mo"]["tier_system"]
    tier_sys_24 = pass_fail["24mo"]["tier_system"]
    imm_n_12    = pass_fail["12mo"]["imminent_n"]
    imm_n_24    = pass_fail["24mo"]["imminent_n"]

    lt12 = metrics["12mo"]["lift_table"]
    lt12_p1 = metrics["12mo"].get("lift_table_p1", pd.DataFrame())
    lt24 = metrics["24mo"]["lift_table"]
    lt24_p1 = metrics["24mo"].get("lift_table_p1", pd.DataFrame())

    b12 = baselines.get("12mo", {})

    tier_counts_full = eligible_df["tier_corrected"].value_counts().to_dict()
    tier_counts_p1   = eligible_df["p1_tier"].value_counts().to_dict()

    lines = [
        "# SectorWindow Transition Signal Score — Backtest Results",
        "",
        f"**Cutoff:** {cutoff_label}  |  **Scoring data:** officer + filing data public at cutoff  |  **Generated:** 2026-11-18",
        "",
        f"## Overall verdict: {overall}",
        "",
        "Pass criteria (pre-specified):",
        "- Imminent tier shows ≥ 2× base rate in both 12-month and 24-month outcome windows",
        "- Holds in more than one revenue band",
        "",
        f"| Criterion | Required | Actual | Result |",
        f"|---|---|---|---|",
        f"| Imminent lift (12-month, {tier_sys_12}) | ≥ 2.0× | {imm_lift_12:.2f}× (N={imm_n_12:,}) | {'✓ PASS' if pass_fail['12mo']['pass'] else '✗ FAIL'} |",
        f"| Imminent lift (24-month, {tier_sys_24}) | ≥ 2.0× | {imm_lift_24:.2f}× (N={imm_n_24:,}) | {'✓ PASS' if pass_fail['24mo']['pass'] else '✗ FAIL'} |",
        f"| Multi-band (>1 band ≥ 2×) | ≥ 2 bands | {pass_fail['multi_band']['bands_above_2x']} band(s) | {'✓ PASS' if pass_fail['multi_band']['pass'] else '✗ FAIL'} |",
        "",
        "---",
        "",
        "## Step 0 — Coverage Gate",
        "",
        f"| Year | Orgs with top-officer data |",
        f"|---|---|",
    ]
    year_counts = [(2017,30),(2018,790),(2019,10547),(2020,32001),(2021,34026),(2022,2720)]
    for yr, n in year_counts:
        lines.append(f"| {yr} | {n:,} |")

    lines += [
        "",
        "**Recommended cutoff: 12/31/2021** — largest eligible sample, robust 12-month window, more orgs at MEDIUM confidence for leadership signal.",
        "24-month window severely limited (2022 data sparse, adds only ~27 unique orgs vs 12-month). Reported with caveat.",
        "",
        "---",
        "",
        "## Step 3 — Sample Sizes and Dropped Orgs",
        "",
        f"| Category | Count |",
        f"|---|---|",
        f"| Orgs with pre-cutoff score | {len(scores_df):,} |",
        f"| Eligible (12-month) | {metrics['12mo']['n']:,} |",
        f"| Eligible (24-month) | {metrics['24mo']['n']:,} |",
        f"| Dropped — dissolved / merged | {drop_summary['dissolved_or_merged']:,} |",
        f"| Dropped — no financial data | {drop_summary['no_financial_score']:,} |",
        f"| Dropped — no outcome window | {drop_summary['no_outcome_window_data']:,} |",
        "",
        "Score tier distribution (eligible sample):",
        "",
        "**Full-model tiers** (score_corrected: imminent ≥80, elevated ≥60, watch ≥40, stable <40):",
        "",
        f"| Tier | Count |",
        f"|---|---|",
    ]
    for tier in ["imminent","elevated","watch","stable"]:
        n = tier_counts_full.get(tier, 0)
        lines.append(f"| {tier} | {n:,} |")
    lines += [
        "",
        "**Phase-1 tiers** (p1_score: imminent ≥55, high ≥40, elevated ≥20, low <20):",
        "_(Most orgs score primarily on financial signals due to LOW confidence at this cutoff.)_",
        "",
        f"| Tier | Count |",
        f"|---|---|",
    ]
    for tier in ["imminent","high","elevated","low"]:
        n = tier_counts_p1.get(tier, 0)
        lines.append(f"| {tier} | {n:,} |")

    lines += [
        "",
        "---",
        "",
        "## Step 4 — Metrics",
        "",
        "### 12-Month Outcome Window",
        "",
        f"**Base rate:** {base_12:.1%}  |  **N:** {metrics['12mo']['n']:,}  |  **AUC:** {metrics['12mo']['auc'] or 'n/a'}",
        "",
        "#### Lift by tier — Full model (score_corrected, imminent ≥ 80)",
        "",
        "| Tier | N | Transitions | Rate | Lift |",
        "|---|---|---|---|---|",
    ]
    for _, r in lt12.iterrows():
        lines.append(f"| {r['tier']} | {int(r['n']):,} | {int(r['transitions']):,} | {r['rate']:.1%} | {r['lift']:.2f}× |")

    lines += [
        "",
        "#### Lift by tier — Phase-1 score (p1_score, imminent ≥ 55)",
        "_Note: Most orgs score primarily on financial signals at this cutoff (71% LOW confidence → Phase 2 pts = 0)._",
        "",
        "| Tier | N | Transitions | Rate | Lift |",
        "|---|---|---|---|---|",
    ]
    for _, r in lt12_p1.iterrows():
        lines.append(f"| {r['tier']} | {int(r['n']):,} | {int(r['transitions']):,} | {r['rate']:.1%} | {r['lift']:.2f}× |")

    lines += [
        "",
        f"**Precision @ top 100:** {metrics['12mo']['p100']:.1%}  |  **Precision @ top 500:** {metrics['12mo']['p500']:.1%}",
        "",
        "#### By revenue band (Phase-1 imminent tier)",
        "",
        "| Band | N | Base rate | Imminent N | Imminent rate | Lift |",
        "|---|---|---|---|---|---|",
    ]
    by_band = metrics["12mo"]["by_band"]
    if not by_band.empty:
        for _, r in by_band.iterrows():
            lines.append(f"| {r['band']} | {int(r['n']):,} | {r['base_rate']:.1%} | {int(r['imminent_n']):,} | {r['imminent_rate']:.1%} | {r['imminent_lift']:.2f}× |")

    lines += [
        "",
        f"**DC/MD/VA only:** N={metrics['12mo']['dmv_n']:,}, base rate={metrics['12mo']['dmv_base_rate']:.1%}, "
        f"imminent N={metrics['12mo']['dmv_imminent_n']:,}, "
        f"imminent rate={metrics['12mo']['dmv_imminent_rate']:.1%}, "
        f"lift={metrics['12mo']['dmv_imminent_lift']:.2f}×",
        "",
        "### 24-Month Outcome Window",
        "",
        f"> **Caveat:** 24-month outcome at 12/31/2021 cutoff adds only ~27 orgs beyond 12-month (2022 data is sparse). Results are nearly identical to 12-month.",
        "",
        f"**Base rate:** {base_24:.1%}  |  **N:** {metrics['24mo']['n']:,}  |  **AUC:** {metrics['24mo']['auc'] or 'n/a'}",
        "",
        "#### Lift by tier",
        "",
        "| Tier | N | Transitions | Rate | Lift |",
        "|---|---|---|---|---|",
    ]
    for _, r in lt24.iterrows():
        lines.append(f"| {r['tier']} | {int(r['n']):,} | {int(r['transitions']):,} | {r['rate']:.1%} | {r['lift']:.2f}× |")

    lines += [
        "",
        "---",
        "",
        "## Step 5 — Baseline Comparison (12-Month Window)",
        "",
        f"| Model | AUC | Notes |",
        f"|---|---|---|",
        f"| Full model (score_corrected) | {b12.get('full_model_auc','n/a')} | Phase 1 + Phase 2 + confidence discount |",
        f"| Random baseline | {b12.get('random_auc','n/a')} | Expected ≈ 0.50 |",
        f"| Tenure-only rule | {b12.get('tenure_only_auc','n/a')} | Flag if tenure ≤2 or ≥11 yrs |",
        f"| Tenure + org size | {b12.get('tenure_size_auc','n/a')} | Tenure flag weighted with revenue band |",
        f"| Financial only (Phase 1) | {b12.get('financial_only_auc','n/a')} | Revenue trend + comp + deficit (0–70 pts) |",
        f"| Leadership only (Phase 2) | {b12.get('leadership_only_auc','n/a')} | Tenure + comp percentile, discounted (0–30 pts) |",
        "",
        f"Financial-only Precision @ top 100: {b12.get('financial_only_p100','n/a'):.1%}" if b12.get('financial_only_p100') else "Financial-only Precision @ top 100: n/a",
        "",
        "---",
        "",
        "## Step 1 — Transition Event Summary",
        "",
        f"| Metric | Count |",
        f"|---|---|",
        f"| Total transitions detected (all years, 2017–2022) | {len(trans_df):,} |",
        f"| Title-only changes (same person, new title) | {len(title_df):,} |",
        f"| Transitions flagged interim | {int(trans_df['is_interim'].sum()) if 'is_interim' in trans_df.columns else 0:,} |",
        "",
        "---",
        "",
    ]

    # Secondary cutoff (12/31/2020) section
    if metrics_sec is not None:
        sec_12 = metrics_sec.get("12mo", {})
        sec_24 = metrics_sec.get("24mo", {})
        b12_sec = baselines_sec.get("12mo", {}) if baselines_sec else {}
        pf_sec = evaluate_pass_fail(metrics_sec)

        lines += [
            "## Secondary Cutoff: 12/31/2020 (cross-check with genuine 24-month window)",
            "",
            f"At this cutoff, scoring uses data with tax_year ≤ 2019. The 12-month outcome is 2020 "
            f"and the 24-month outcome is 2021 — genuinely distinct windows. "
            f"Pre-cutoff confidence is almost entirely LOW (only 531 orgs have ≥2 years of data), "
            f"so this is effectively a **financial-only** test.",
            "",
            f"| Window | N | Base rate | AUC | Imminent (P1) lift |",
            f"|---|---|---|---|---|",
            f"| 12-month (2020 outcome) | {sec_12.get('n','?'):,} | {sec_12.get('base_rate',0):.1%} | {sec_12.get('auc','n/a')} | "
            f"{pf_sec.get('12mo',{}).get('imminent_lift','?'):.2f}× |",
            f"| 24-month (2021 outcome) | {sec_24.get('n','?'):,} | {sec_24.get('base_rate',0):.1%} | {sec_24.get('auc','n/a')} | "
            f"{pf_sec.get('24mo',{}).get('imminent_lift','?'):.2f}× |",
            "",
            f"Full-model AUC (secondary, 12-month): {b12_sec.get('full_model_auc','n/a')}  |  "
            f"Financial only: {b12_sec.get('financial_only_auc','n/a')}  |  "
            f"Tenure + size: {b12_sec.get('tenure_size_auc','n/a')}",
            "",
            "12-month lift table (Phase-1 tiers):",
            "",
            "| Tier | N | Transitions | Rate | Lift |",
            "|---|---|---|---|---|",
        ]
        lt_sec_p1 = sec_12.get("lift_table_p1", pd.DataFrame())
        if not lt_sec_p1.empty:
            for _, r in lt_sec_p1.iterrows():
                lines.append(f"| {r['tier']} | {int(r['n']):,} | {int(r['transitions']):,} | {r['rate']:.1%} | {r['lift']:.2f}× |")
        else:
            lines.append("| (no P1 tier data) | | | | |")

        lines += [
            "",
            f"**Secondary verdict:** {'PASS' if pf_sec.get('overall') else 'FAIL'} "
            f"(imminent lift: 12mo={pf_sec.get('12mo',{}).get('imminent_lift','?'):.2f}×, "
            f"24mo={pf_sec.get('24mo',{}).get('imminent_lift','?'):.2f}×). "
            f"Consistent with primary cutoff — no meaningful signal at any tier.",
            "",
            "---",
            "",
        ]

    lines += [
        "## Interpretation",
        "",
        "**The score does not meet the pre-specified pass criteria.** Key findings:",
        "",
        "1. **Imminent tier lift is 1.16× (Phase-1 tier) and 0.62× (full-model tier)**, well below the 2× target. "
        "The imminent tier has only 820 orgs (P1 ≥55) of which 20.7% had a transition vs. 17.8% base rate — a small edge, not a reliable signal.",
        "",
        "2. **AUC = 0.52**, barely above random (0.50). Every component tested — full model, financial only, "
        "leadership only, tenure only — lands within 0.03 of random. This is the main finding.",
        "",
        "3. **Financial signals are the strongest component** (AUC 0.517), "
        "but they barely outperform tenure + revenue-band (AUC 0.534). "
        "The Phase 2 leadership component adds no detectable signal over Phase 1 at this cutoff.",
        "",
        "4. **Why Phase 2 is undetectable here:** 71% of eligible orgs (23,246/33,065) "
        "have only 1 year of pre-cutoff officer data → LOW confidence → Phase 2 score = 0. "
        "Only 477 orgs have HIGH confidence (3+ years). The leadership component cannot be "
        "evaluated fairly until multiple years of XML data are available per org.",
        "",
        "5. **Revenue band pattern:** The $1M–$25M band shows modestly higher lift (1.41–1.56×) "
        "than the full sample. Very large orgs (>$25M) show lift below 1×. "
        "This suggests the score may have different characteristics by revenue band.",
        "",
        "6. **DC/MD/VA shows no region-specific lift** (1.15×), consistent with the overall results.",
        "",
        "**What is needed before re-running:**",
        "- Wait for 2023 and 2024 XML data to load; this gives genuine 2-year pre-cutoff coverage for many more orgs.",
        "- With 3+ years of officer data, HIGH confidence orgs will be large enough to test Phase 2 signal independently.",
        "- Consider recalibrating tier thresholds using percentile ranks rather than absolute score boundaries.",
        "",
        "---",
        "",
        "## Notes",
        "",
        "- **No look-ahead:** Scores computed using only filings and officer data with period_end ≤ 12/31/2020 (public by 12/31/2021). Financial 3-year CAGR uses up to 2018–2020 data.",
        "- **Coverage confidence:** 23,246 of 33,065 pre-cutoff orgs (70.3%) have only 1 year of officer data → LOW confidence → Phase 2 pts discounted to 0.",
        "- **Transition definition:** Consecutive-year change in highest-compensated `is_top_officer` person. Names fuzzy-matched at ≥ 0.90 similarity (difflib SequenceMatcher). PAST/ELECT/FORMER/BOARD roles excluded when a current role exists.",
        "- **24-month caveat:** 2022 officer data covers only 2,720 orgs; the 24-month window adds only ~27 orgs beyond 12-month. Numbers should be treated as near-identical to 12-month.",
        "- **Step 6 discipline:** No weights or thresholds were adjusted based on these results. If tuning is desired, split by state first.",
        "",
        "---",
        "",
        "_All numbers reproducible from `backtest/run_backtest.py` and `backtest/00_coverage.py`._",
    ]

    results_path = Path(__file__).resolve().parent / "results.md"
    results_path.write_text("\n".join(lines))
    print(f"\nResults written to {results_path}")


# ════════════════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════════════════

def main() -> None:
    print(f"SectorWindow Backtest\nDB: {DB_PATH}\n")
    con = duckdb.connect(DB_PATH, read_only=True)

    # Step 1: Transition events (all years 2017–2022, for complete picture)
    trans_df, title_df = step1_detect_transitions(con, all_years_max=2022)
    trans_df.to_csv(OUT_DIR / "transitions.csv", index=False)
    title_df.to_csv(OUT_DIR / "title_only_changes.csv", index=False)
    print()

    # Step 2: No-lookahead scoring at primary cutoff (12/31/2021, pre = ≤2020)
    scores_primary = step2_score_at_cutoff(con, pre_year=PRIMARY_PRE_YEAR)
    scores_primary.to_csv(OUT_DIR / "scores_cutoff_2021.csv", index=False)
    print()

    # Step 3: Eligible sample (primary cutoff)
    eligible_df, drop_summary = step3_eligible_sample(
        con, scores_primary, trans_df,
        pre_year=PRIMARY_PRE_YEAR,
        outcome_12mo=PRIMARY_12MO_YEAR,
        outcome_24mo=PRIMARY_24MO_YEAR,
    )
    eligible_df.to_csv(OUT_DIR / "eligible_sample.csv", index=False)
    print()

    # Step 4: Metrics
    metrics = step4_metrics(eligible_df)
    for window, m in metrics.items():
        print(f"\n--- {window} window ---")
        print(f"  N={m['n']:,}, base_rate={m['base_rate']:.1%}, AUC={m['auc']}")
        print(m["lift_table"].to_string(index=False))

    # Step 5: Baselines
    baselines = step5_baselines(eligible_df)
    for window, b in baselines.items():
        print(f"\n--- Baselines {window} ---")
        for k, v in b.items():
            print(f"  {k}: {v}")

    # Pass/fail
    pf = evaluate_pass_fail(metrics)
    print(f"\n=== PASS/FAIL ===")
    for k, v in pf.items():
        print(f"  {k}: {v}")

    # Save eligibility details
    pd.DataFrame([{
        "window": w,
        "base_rate": m["base_rate"],
        "n": m["n"],
        "auc": m["auc"],
        "p100": m["p100"],
        "p500": m["p500"],
    } for w, m in metrics.items()]).to_csv(OUT_DIR / "metrics_summary.csv", index=False)

    # Secondary cutoff (12/31/2020) for validation
    print("\n--- Secondary cutoff 12/31/2020 (cross-check) ---")
    scores_secondary = step2_score_at_cutoff(con, pre_year=SECONDARY_PRE_YEAR)
    scores_secondary.to_csv(OUT_DIR / "scores_cutoff_2020.csv", index=False)

    eligible_sec, drop_sec = step3_eligible_sample(
        con, scores_secondary, trans_df,
        pre_year=SECONDARY_PRE_YEAR,
        outcome_12mo=SECONDARY_12MO_YEAR,
        outcome_24mo=SECONDARY_24MO_YEAR,
    )
    eligible_sec.to_csv(OUT_DIR / "eligible_sample_2020cutoff.csv", index=False)
    metrics_sec = step4_metrics(eligible_sec)
    baselines_sec = step5_baselines(eligible_sec)
    for window, m in metrics_sec.items():
        print(f"\n  Secondary {window}: N={m['n']:,}, base={m['base_rate']:.1%}, AUC={m['auc']}")
        print(m["lift_table"].to_string(index=False))

    # Step 6: Write results.md
    step6_write_results(
        metrics=metrics,
        baselines=baselines,
        pass_fail=pf,
        drop_summary=drop_summary,
        eligible_df=eligible_df,
        trans_df=trans_df,
        title_df=title_df,
        scores_df=scores_primary,
        cutoff_label="12/31/2021 (primary) + 12/31/2020 (secondary)",
        metrics_sec=metrics_sec,
        baselines_sec=baselines_sec,
        eligible_sec=eligible_sec,
    )

    con.close()
    print("\nBacktest complete.")


if __name__ == "__main__":
    main()
