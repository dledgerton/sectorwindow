#!/bin/zsh
# SectorWindow data refresh. Run from anywhere; it moves to the repo root.
#   scripts/ops/refresh.sh              full refresh, then sync to MotherDuck
#   scripts/ops/refresh.sh --skip-sync  refresh the local database only
# Stops at the first failing step. Log: logs/refresh-YYYY-MM-DD.log
set -euo pipefail
cd "${0:A:h}/../.."

SKIP_SYNC=0
[[ "${1:-}" == "--skip-sync" ]] && SKIP_SYNC=1

PY=.venv/bin/python
YEAR=$(date +%Y)
PREV=$((YEAR - 1))
mkdir -p logs data
LOG="logs/refresh-$(date +%F).log"
export DEJ_CACHE_DIR="${DEJ_CACHE_DIR:-/Volumes/ExternalHardDrive/dej-intelligence-data/xml_cache}"

if [[ ! -d "$(dirname "$DEJ_CACHE_DIR")" ]]; then
  echo "External drive folder $(dirname "$DEJ_CACHE_DIR") not found. Plug in the drive or set DEJ_CACHE_DIR." >&2
  exit 1
fi
mkdir -p "$DEJ_CACHE_DIR"

step() { echo; echo "=== $(date +%T) $1"; }

{
  step "0/8 Back up local database (keeps the 3 newest)"
  cp data/dej_intelligence.duckdb "data/dej_intelligence.backup-$(date +%F).duckdb"
  ls -1t data/dej_intelligence.backup-*.duckdb | tail -n +4 | xargs rm -f

  step "1/8 Org list (IRS BMF, adds new orgs)"
  $PY scripts/duckdb/load_bmf_duckdb.py

  step "2/8 Financials (NCCS Core, new layout; missing years are skipped)"
  $PY scripts/duckdb/nccs_loader_duckdb.py

  step "3/8 NTEE codes for new orgs"
  $PY scripts/phase3_ntee_classifier.py --null-only --report

  step "4/8 Officers from IRS XML, $PREV and $YEAR"
  $PY scripts/duckdb/phase2_step2_load_990_xml.py --year "$PREV" --resume
  $PY scripts/duckdb/phase2_step2_load_990_xml.py --year "$YEAR" --resume

  step "5/8 Scores: financial signals, then officer signals, then coverage correction"
  $PY scripts/duckdb/compute_signals.py
  $PY scripts/ops/prune_old_scores.py
  $PY scripts/duckdb/phase2_step3_officer_signals.py
  $PY scripts/phase2_score_correction.py

  step "6/8 Spot-check known orgs (read the output; validate_load.py is a retired Supabase script)"
  $PY scripts/duckdb/compute_signals.py --validate-only

  if [[ $SKIP_SYNC -eq 0 ]]; then
    step "7/8 Sync to MotherDuck"
    $PY scripts/sync_to_motherduck.py
  else
    step "7/8 Sync skipped (--skip-sync)"
  fi

  step "8/8 Record new freshness baseline"
  python3 scripts/ops/check_freshness.py --mark-refreshed

  echo; echo "Refresh finished $(date)."
} 2>&1 | tee -a "$LOG"
