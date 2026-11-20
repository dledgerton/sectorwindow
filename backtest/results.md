# SectorWindow Transition Signal Score — Backtest Results

**Cutoff:** 12/31/2021 (primary) + 12/31/2020 (secondary)  |  **Scoring data:** officer + filing data public at cutoff  |  **Generated:** 2026-11-18

## Overall verdict: FAIL

Pass criteria (pre-specified):
- Imminent tier shows ≥ 2× base rate in both 12-month and 24-month outcome windows
- Holds in more than one revenue band

| Criterion | Required | Actual | Result |
|---|---|---|---|
| Imminent lift (12-month, P1 (≥55)) | ≥ 2.0× | 1.16× (N=820) | ✗ FAIL |
| Imminent lift (24-month, P1 (≥55)) | ≥ 2.0× | 1.15× (N=820) | ✗ FAIL |
| Multi-band (>1 band ≥ 2×) | ≥ 2 bands | 0 band(s) | ✗ FAIL |

---

## Step 0 — Coverage Gate

| Year | Orgs with top-officer data |
|---|---|
| 2017 | 30 |
| 2018 | 790 |
| 2019 | 10,547 |
| 2020 | 32,001 |
| 2021 | 34,026 |
| 2022 | 2,720 |

**Recommended cutoff: 12/31/2021** — largest eligible sample, robust 12-month window, more orgs at MEDIUM confidence for leadership signal.
24-month window severely limited (2022 data sparse, adds only ~27 unique orgs vs 12-month). Reported with caveat.

---

## Step 3 — Sample Sizes and Dropped Orgs

| Category | Count |
|---|---|
| Orgs with pre-cutoff score | 74,189 |
| Eligible (12-month) | 28,600 |
| Eligible (24-month) | 28,600 |
| Dropped — dissolved / merged | 0 |
| Dropped — no financial data | 814 |
| Dropped — no outcome window | 3,651 |

Score tier distribution (eligible sample):

**Full-model tiers** (score_corrected: imminent ≥80, elevated ≥60, watch ≥40, stable <40):

| Tier | Count |
|---|---|
| imminent | 18 |
| elevated | 668 |
| watch | 4,361 |
| stable | 23,553 |

**Phase-1 tiers** (p1_score: imminent ≥55, high ≥40, elevated ≥20, low <20):
_(Most orgs score primarily on financial signals due to LOW confidence at this cutoff.)_

| Tier | Count |
|---|---|
| imminent | 820 |
| high | 2,887 |
| elevated | 8,800 |
| low | 16,093 |

---

## Step 4 — Metrics

### 12-Month Outcome Window

**Base rate:** 17.8%  |  **N:** 28,600  |  **AUC:** 0.5157

#### Lift by tier — Full model (score_corrected, imminent ≥ 80)

| Tier | N | Transitions | Rate | Lift |
|---|---|---|---|---|
| imminent | 18 | 2 | 11.1% | 0.62× |
| elevated | 668 | 133 | 19.9% | 1.12× |
| watch | 4,361 | 808 | 18.5% | 1.04× |
| stable | 23,553 | 4,160 | 17.7% | 0.99× |

#### Lift by tier — Phase-1 score (p1_score, imminent ≥ 55)
_Note: Most orgs score primarily on financial signals at this cutoff (71% LOW confidence → Phase 2 pts = 0)._

| Tier | N | Transitions | Rate | Lift |
|---|---|---|---|---|
| imminent | 820 | 170 | 20.7% | 1.16× |
| high | 2,887 | 525 | 18.2% | 1.02× |
| elevated | 8,800 | 1,655 | 18.8% | 1.05× |
| low | 16,093 | 2,753 | 17.1% | 0.96× |

**Precision @ top 100:** 20.0%  |  **Precision @ top 500:** 21.4%

#### By revenue band (Phase-1 imminent tier)

| Band | N | Base rate | Imminent N | Imminent rate | Lift |
|---|---|---|---|---|---|
| < $1M | 14,624 | 19.5% | 526 | 19.8% | 1.01× |
| $1M–$5M | 7,565 | 16.9% | 180 | 23.9% | 1.41× |
| $5M–$25M | 4,232 | 14.6% | 88 | 22.7% | 1.56× |
| > $25M | 2,119 | 16.1% | 24 | 12.5% | 0.78× |

**DC/MD/VA only:** N=11,467, base rate=19.3%, imminent N=329, imminent rate=22.2%, lift=1.15×

### 24-Month Outcome Window

> **Caveat:** 24-month outcome at 12/31/2021 cutoff adds only ~27 orgs beyond 12-month (2022 data is sparse). Results are nearly identical to 12-month.

**Base rate:** 18.4%  |  **N:** 28,600  |  **AUC:** 0.5136

#### Lift by tier

| Tier | N | Transitions | Rate | Lift |
|---|---|---|---|---|
| imminent | 18 | 2 | 11.1% | 0.60× |
| elevated | 668 | 135 | 20.2% | 1.10× |
| watch | 4,361 | 832 | 19.1% | 1.04× |
| stable | 23,553 | 4,301 | 18.3% | 0.99× |

---

## Step 5 — Baseline Comparison (12-Month Window)

| Model | AUC | Notes |
|---|---|---|
| Full model (score_corrected) | 0.5157 | Phase 1 + Phase 2 + confidence discount |
| Random baseline | 0.5017 | Expected ≈ 0.50 |
| Tenure-only rule | 0.5009 | Flag if tenure ≤2 or ≥11 yrs |
| Tenure + org size | 0.5337 | Tenure flag weighted with revenue band |
| Financial only (Phase 1) | 0.5169 | Revenue trend + comp + deficit (0–70 pts) |
| Leadership only (Phase 2) | 0.5032 | Tenure + comp percentile, discounted (0–30 pts) |

Financial-only Precision @ top 100: 20.0%

---

## Step 1 — Transition Event Summary

| Metric | Count |
|---|---|
| Total transitions detected (all years, 2017–2022) | 7,649 |
| Title-only changes (same person, new title) | 2,312 |
| Transitions flagged interim | 100 |

---

## Secondary Cutoff: 12/31/2020 (cross-check with genuine 24-month window)

At this cutoff, scoring uses data with tax_year ≤ 2019. The 12-month outcome is 2020 and the 24-month outcome is 2021 — genuinely distinct windows. Pre-cutoff confidence is almost entirely LOW (only 531 orgs have ≥2 years of data), so this is effectively a **financial-only** test.

| Window | N | Base rate | AUC | Imminent (P1) lift |
|---|---|---|---|---|
| 12-month (2020 outcome) | 9,532 | 18.4% | 0.5022 | 0.89× |
| 24-month (2021 outcome) | 9,532 | 28.7% | 0.5006 | 1.02× |

Full-model AUC (secondary, 12-month): 0.5022  |  Financial only: 0.5041  |  Tenure + size: 0.533

12-month lift table (Phase-1 tiers):

| Tier | N | Transitions | Rate | Lift |
|---|---|---|---|---|
| imminent | 116 | 19 | 16.4% | 0.89× |
| high | 687 | 130 | 18.9% | 1.03× |
| elevated | 2,612 | 488 | 18.7% | 1.02× |
| low | 6,117 | 1,116 | 18.2% | 0.99× |

**Secondary verdict:** FAIL (imminent lift: 12mo=0.89×, 24mo=1.02×). Consistent with primary cutoff — no meaningful signal at any tier.

---

## Interpretation

**The score does not meet the pre-specified pass criteria.** Key findings:

1. **Imminent tier lift is 1.16× (Phase-1 tier) and 0.62× (full-model tier)**, well below the 2× target. The imminent tier has only 820 orgs (P1 ≥55) of which 20.7% had a transition vs. 17.8% base rate — a small edge, not a reliable signal.

2. **AUC = 0.52**, barely above random (0.50). Every component tested — full model, financial only, leadership only, tenure only — lands within 0.03 of random. This is the main finding.

3. **Financial signals are the strongest component** (AUC 0.517), but they barely outperform tenure + revenue-band (AUC 0.534). The Phase 2 leadership component adds no detectable signal over Phase 1 at this cutoff.

4. **Why Phase 2 is undetectable here:** 71% of eligible orgs (23,246/33,065) have only 1 year of pre-cutoff officer data → LOW confidence → Phase 2 score = 0. Only 477 orgs have HIGH confidence (3+ years). The leadership component cannot be evaluated fairly until multiple years of XML data are available per org.

5. **Revenue band pattern:** The $1M–$25M band shows modestly higher lift (1.41–1.56×) than the full sample. Very large orgs (>$25M) show lift below 1×. This suggests the score may have different characteristics by revenue band.

6. **DC/MD/VA shows no region-specific lift** (1.15×), consistent with the overall results.

**What is needed before re-running:**
- Wait for 2023 and 2024 XML data to load; this gives genuine 2-year pre-cutoff coverage for many more orgs.
- With 3+ years of officer data, HIGH confidence orgs will be large enough to test Phase 2 signal independently.
- Consider recalibrating tier thresholds using percentile ranks rather than absolute score boundaries.

---

## Notes

- **No look-ahead:** Scores computed using only filings and officer data with period_end ≤ 12/31/2020 (public by 12/31/2021). Financial 3-year CAGR uses up to 2018–2020 data.
- **Coverage confidence:** 23,246 of 33,065 pre-cutoff orgs (70.3%) have only 1 year of officer data → LOW confidence → Phase 2 pts discounted to 0.
- **Transition definition:** Consecutive-year change in highest-compensated `is_top_officer` person. Names fuzzy-matched at ≥ 0.90 similarity (difflib SequenceMatcher). PAST/ELECT/FORMER/BOARD roles excluded when a current role exists.
- **24-month caveat:** 2022 officer data covers only 2,720 orgs; the 24-month window adds only ~27 orgs beyond 12-month. Numbers should be treated as near-identical to 12-month.
- **Step 6 discipline:** No weights or thresholds were adjusted based on these results. If tuning is desired, split by state first.

---

_All numbers reproducible from `backtest/run_backtest.py` and `backtest/00_coverage.py`._