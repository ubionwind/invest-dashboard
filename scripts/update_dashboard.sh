#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

log_file="${DASHBOARD_UPDATE_LOG:-/tmp/invest-dashboard-update.log}"
: >"$log_file"
exec > >(tee -a "$log_file") 2>&1
trap 'rc=$?; echo "dashboard update failed rc=$rc mode=${mode:-unknown} line=$LINENO cmd=$BASH_COMMAND"; echo "--- log tail ---"; tail -120 "$log_file" || true; exit $rc' ERR

# Layered update policy:
# - fast-market: every cron run; refresh only quote/holding/card numbers.
# - full: periodically or when forced; rebuild strategy/fundamental/technical data from runtime sources.
# Force full with DASHBOARD_FULL=1. Force fast with DASHBOARD_FAST=1.
mode="fast"
minute="$(date +%M)"
if [[ "${DASHBOARD_FULL:-}" == "1" ]]; then
  mode="full"
elif [[ "${DASHBOARD_FAST:-}" == "1" ]]; then
  mode="fast"
elif [[ ! -s data/dashboard-data.json ]]; then
  mode="full"
elif (( 10#$minute % 15 == 0 )); then
  mode="full"
fi

if [[ "$mode" == "full" ]]; then
  python3 scripts/generate_dashboard_data.py
else
  python3 scripts/refresh_fast_market_data.py
fi

runtime_ohlcv="/home/ubion/.openclaw/workspace/shared/invest_api_common/runtime/fundamentals/daily_ohlcv_latest.json"
if [[ -s "$runtime_ohlcv" ]]; then
  mkdir -p data/fundamentals data/test/fundamentals
  cp "$runtime_ohlcv" data/fundamentals/daily_ohlcv_latest.json
  cp "$runtime_ohlcv" data/test/fundamentals/daily_ohlcv_latest.json
fi

python3 scripts/generate_test_split_data.py
python3 scripts/write_dashboard_layers.py
python3 scripts/audit_dashboard_analysis.py
python3 scripts/generate_survival_v1_data.py

if git diff --quiet -- data/dashboard-data.json data/dashboard-history.json data/survival-ledger.json data/survival-review.json data/survival-v1.json data/fundamentals data/futures data/test data/layers data/stocks; then
  echo "dashboard data unchanged ($mode layer)"
  exit 0
fi

# Stop before commit/push only if public JSON diff contains actual credentials,
# account identifiers, or order-execution clues. Public analysis labels such as
# kisEnrichment / K-O-R / sale_account are allowed.
python3 scripts/public_diff_safety_scan.py
git add data/dashboard-data.json data/dashboard-history.json data/survival-ledger.json data/survival-review.json data/survival-v1.json data/fundamentals data/futures data/test data/layers data/stocks
# Keep public branch as a rolling single-snapshot history, so old data is not easily analyzed via git history.
git commit --amend --no-edit
git push --force-with-lease origin main
echo "dashboard $mode layer update pushed"
