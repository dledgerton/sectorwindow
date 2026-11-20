# Schema & Scoring Code — Investigation Notes
_Inspected 2026-11-18, before writing any backtest code._

## Tables (production)

| Table | Rows | Purpose |
|---|---|---|
| `organizations` | 237,697 | BMF org metadata (ein, name, state, ntee_code, status) |
| `filings` | 414,613 | NCCS Core financials (tax_year, period_end, total_revenue, total_expenses, comp_employees, partial_year) |
| `officers` | 1,268,552 | 990 XML Part VII (person_name_normalized, title_normalized, is_top_officer, comp_reportable_org, tax_year) |
| `transition_scores` | 78,067 | Scored orgs (score, tier, total_score_v2, score_corrected, tier_corrected) |
| `xml_filing_log` | 97,943 | Which XML files were parsed (tax_year 2017-2022) |

## Views (production)

- `v_filing_trends` — most-recent non-partial filing per org with 3-yr trend metrics
- `v_consecutive_deficits` — deficit flag per (ein, tax_year) for streak counting
- `v_org_signals` — org metadata joined to filing trends (active orgs only)
- `v_ceo_tenure` — tenure group per org-year, based on highest-comp is_top_officer person

## Scoring model (production, `compute_signals.py` + `phase2_step3_officer_signals.py` + `phase2_score_correction.py`)

### Phase 1 — Financial (0–70 pts)

| Signal | Column | Points |
|---|---|---|
| Revenue trend (3-yr CAGR) | `revenue_cagr_3yr` | 0–25 |
| Comp trajectory (3-yr %) | `comp_pct_change_3yr` | 0–15 |
| Deficit streak | consecutive losses at trailing edge | 0–30 |

**Revenue trend thresholds:**
- ≤ −30%: 25 pts (steep_decline)
- ≤ −15%: 20 pts (decline)
- ≤ −5%: 12 pts (soft_decline)
- ≤ +5%: 5 pts (flat)
- ≤ +15%: 2 pts (growth)
- > +15%: 0 pts (strong_growth)

**Comp trajectory thresholds:**
- ≤ −20%: 15 pts (declining)
- ≤ −5%: 10 pts (softening)
- ≤ +5%: 8 pts (flat)
- ≤ +20%: 3 pts (growing)
- > +20%: 0 pts (strong_growth)

**Deficit streak:**
- 3+ consecutive: 30 pts
- 2 consecutive: 20 pts
- 1: 10 pts
- 0: 0 pts

### Phase 2 — Leadership (0–30 pts, subject to coverage discount)

| Signal | Column | Points |
|---|---|---|
| CEO tenure | `ceo_tenure_years` | 0–20 |
| CEO comp percentile (vs NTEE peers) | `ceo_comp_pct_ntee` | 0–10 |

**Tenure points (`phase2_step3_officer_signals.py` `TENURE_SCORE_TABLE`):**
- 0–1 yrs: 20 pts (very new)
- 2 yrs: 15 pts
- 3–4 yrs: 10 pts
- 5–6 yrs: 8 pts
- 7–10 yrs: 12 pts
- 11–14 yrs: 16 pts
- 15+ yrs: 20 pts (very long, departure imminent)
- Unknown: 5 pts default

**Comp percentile points:**
- ≥ 90th: 8 pts (overcompensated — potential exit)
- ≥ 75th: 5 pts
- 25th–74th: 3 pts (normal)
- 10th–24th: 6 pts (undercompensated)
- < 10th: 9 pts (severely undercompensated — flight risk)
- Unknown: 3 pts default

### Coverage-confidence discount (`phase2_score_correction.py`)

| XML coverage years | Confidence | Multiplier (applied to Phase 2 pts) |
|---|---|---|
| 3+ | HIGH | 1.0 |
| 2 | MEDIUM | 0.5 |
| 1 | LOW | 0.0 |

`score_corrected = score + (confidence_multiplier – 1) × (tenure_pts + comp_pts)`

### Tier thresholds (corrected score, 0–100)

| Tier | Threshold |
|---|---|
| `imminent` | ≥ 80 |
| `elevated` | ≥ 60 |
| `watch` | ≥ 40 |
| `stable` | < 40 |

_Note: The Phase 1-only `tier` column in `transition_scores` uses different thresholds (imminent ≥ 55). The backtest uses the full-model `tier_corrected` thresholds above._

## Officer data coverage

XML filing data is concentrated in 2019–2021 (Phase 2 data load):

| Year | Orgs with top-officer data |
|---|---|
| 2017 | 30 |
| 2018 | 790 |
| 2019 | 10,547 |
| 2020 | 32,001 |
| 2021 | 34,026 |
| 2022 | 2,720 |

Consecutive-year pairs available for transition detection:
- 2019→2020: 9,540 orgs
- 2020→2021: 28,710 orgs
- 2021→2022: 2,497 orgs

Production `v_ceo_tenure` shows a ~19–21% annual CEO-change rate across all years.

## Key column notes

- `officers.is_top_officer`: set by production loader; includes "PAST PRESIDENT", "PRESIDENT ELECT" etc. The backtest applies additional title filters when identifying the **current** top executive.
- `filings.partial_year`: exclude when computing financial trends.
- `organizations.status`: production scoring filters to `'active'` only.
- `transition_scores.score_corrected` / `.tier_corrected`: the final production columns used for ranking.
