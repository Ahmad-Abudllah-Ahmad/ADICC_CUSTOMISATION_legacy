#!/usr/bin/env bash
# parallel-runner.sh — wrapper invoked by the QA orchestrator agent.
#
# Usage:
#   ./tests/e2e/runner/parallel-runner.sh batch-01-auth
#   ./tests/e2e/runner/parallel-runner.sh batch-02-dashboard --project=chromium
#
# Resolution: the batch name is matched against `tests/e2e/<glob>` so a
# batch called "batch-01-auth" runs `tests/e2e/batch-01-auth/**/*.spec.ts`.
# If no such directory exists, the batch is treated as a free-form glob
# (e.g. "smoke/auth.spec.ts").
#
# Output:
#   qa-output/<batch>/qa-report/        — HTML report
#   qa-output/<batch>/qa-screenshots/   — screenshots, module-routed
#   qa-output/<batch>/qa-results.json   — machine-readable summary
#   qa-output/<batch>/summary.json      — one-line orchestrator summary
#
# Exit code: 0 on success, 1 on test failure, 2 on infra failure
#   (missing batch / playwright not installed / unreachable backend).

set -uo pipefail

# Disable pipefail for the playwright run so we can capture exit code.
BATCH="${1:-}"
if [[ -z "$BATCH" ]]; then
  echo "usage: $0 <batch-name-or-glob> [--project=chromium] [--workers=N]" >&2
  exit 2
fi
shift || true

# Resolve repo root: this script lives at frontend/tests/e2e/runner/.
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
FRONTEND_DIR="$( cd "$SCRIPT_DIR/../../.." && pwd )"
cd "$FRONTEND_DIR"

# Resolve glob.
if [[ -d "tests/e2e/$BATCH" ]]; then
  GLOB="tests/e2e/$BATCH/**/*.spec.ts"
elif [[ -d "tests/e2e/${BATCH#batch-}" ]]; then
  GLOB="tests/e2e/${BATCH#batch-}/**/*.spec.ts"
else
  # Treat as free-form glob relative to tests/e2e/
  GLOB="tests/e2e/$BATCH"
fi

# Sanitize batch name for the filesystem (slashes → dashes).
SAFE_BATCH="${BATCH//\//-}"
OUT_DIR="qa-output/$SAFE_BATCH"
mkdir -p "$OUT_DIR"

# Clean default-location artefacts from a prior run so the post-run copy
# only carries this batch's outputs.
rm -rf qa-report qa-results.json
# NOTE: do NOT delete qa-screenshots/ — the fixture appends to it, and
# we want to keep cross-batch screenshots browsable.

echo "[parallel-runner] batch=$BATCH glob=$GLOB"
echo "[parallel-runner] output=$OUT_DIR"

# Run.
START_TS=$(date +%s)
npx playwright test "$GLOB" "$@"
EXIT=$?
END_TS=$(date +%s)
DURATION=$((END_TS - START_TS))

# Move artefacts into the batch folder if Playwright wrote them at the
# default location (the playwright.config.ts reporters write to
# `qa-report/`, `qa-results.json`, `qa-screenshots/` at the cwd root).
mkdir -p "$OUT_DIR/qa-report" "$OUT_DIR/qa-screenshots"
if [[ -d qa-report ]]; then
  cp -r qa-report/* "$OUT_DIR/qa-report/" 2>/dev/null || true
fi
if [[ -d qa-screenshots ]]; then
  cp -r qa-screenshots/* "$OUT_DIR/qa-screenshots/" 2>/dev/null || true
fi
if [[ -f qa-results.json ]]; then
  cp qa-results.json "$OUT_DIR/qa-results.json"
fi

# Write a tiny machine-readable summary for the orchestrator.
PASSED='null'
FAILED='null'
TOTAL='null'
if [[ -f "$OUT_DIR/qa-results.json" ]] && command -v python >/dev/null 2>&1; then
  read -r PASSED FAILED TOTAL < <(python - "$OUT_DIR/qa-results.json" <<'PY'
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as f:
        d = json.load(f)
    stats = d.get("stats", {})
    expected = stats.get("expected", 0)
    unexpected = stats.get("unexpected", 0)
    print(expected, unexpected, expected + unexpected)
except Exception:
    print("null null null")
PY
)
fi

cat > "$OUT_DIR/summary.json" <<JSON
{
  "batch": "$BATCH",
  "glob": "$GLOB",
  "exit_code": $EXIT,
  "duration_seconds": $DURATION,
  "passed": $PASSED,
  "failed": $FAILED,
  "total": $TOTAL,
  "report_path": "$OUT_DIR/qa-report/index.html",
  "screenshots_path": "$OUT_DIR/qa-screenshots/"
}
JSON

echo "[parallel-runner] done exit=$EXIT duration=${DURATION}s passed=$PASSED failed=$FAILED"
exit $EXIT
