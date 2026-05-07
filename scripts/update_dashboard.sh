#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/generate_dashboard_data.py >/dev/null
python3 scripts/generate_test_split_data.py >/dev/null
if git diff --quiet -- data/dashboard-data.json data/dashboard-history.json data/test; then
  echo "dashboard data unchanged"
  exit 0
fi

# Stop before commit/push only if public JSON diff contains actual credentials,
# account identifiers, or order-execution clues. Public analysis labels such as
# kisEnrichment / K-O-R / sale_account are allowed.
python3 scripts/public_diff_safety_scan.py
git add data/dashboard-data.json data/dashboard-history.json data/test
# Keep public branch as a rolling single-snapshot history, so old data is not easily analyzed via git history.
git commit --amend --no-edit
git push --force-with-lease origin main
