#!/usr/bin/env bash
# Run every Python component's tests in its own uv environment, sequentially,
# then print a summary table. Components are discovered as directories with a
# pyproject.toml under packages/, workers/, services/, pipelines/, tests/.
#
# Usage: scripts/test_all.sh [--all] [--no-sync] [component-dir ...]
#   default  : pytest -m "not slow and not network and not docker" (same as CI)
#   --all    : run every test, including slow/network/docker-marked ones
#   --no-sync: skip `uv sync --locked` (use existing .venv)
# Exit status: 0 if no component failed/errored; pytest exit 5 (no tests) counts as ok.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 2

MARKEXPR="not slow and not network and not docker"
SYNC=1
COMPONENTS=()
for arg in "$@"; do
  case "$arg" in
    --all) MARKEXPR="" ;;
    --no-sync) SYNC=0 ;;
    -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
    *) COMPONENTS+=("${arg%/}") ;;
  esac
done
if [ ${#COMPONENTS[@]} -eq 0 ]; then
  for d in packages/* workers/* services/* pipelines/* tests/*; do
    [ -f "$d/pyproject.toml" ] && COMPONENTS+=("$d")
  done
fi

LOGDIR="$ROOT/.test-logs"
mkdir -p "$LOGDIR"
ROWS=()
OVERALL=0

count() { # count <word> <summary-line>
  local n
  n=$(grep -oE "[0-9]+ $1" <<<"$2" | head -n1 | cut -d' ' -f1)
  echo "${n:-0}"
}

for c in "${COMPONENTS[@]}"; do
  log="$LOGDIR/$(tr '/' '_' <<<"$c").log"
  echo "=== $c"
  : >"$log"
  start=$(date +%s)
  status="ok"
  if [ ! -f "$c/uv.lock" ]; then
    status="no-lock"
  elif [ "$SYNC" = 1 ] && ! (cd "$c" && uv sync --locked --python 3.11 -q) >"$log" 2>&1; then
    status="sync-error"
  fi
  if [ "$status" = ok ]; then
    args=(-q -p no:cacheprovider)
    [ -n "$MARKEXPR" ] && args+=(-m "$MARKEXPR")
    (cd "$c" && uv run --no-sync pytest "${args[@]}") >>"$log" 2>&1
    rc=$?
    case $rc in
      0) status="ok" ;;
      5) status="no-tests" ;;
      1) status="FAILED" ;;
      *) status="ERROR($rc)" ;;
    esac
  fi
  dur=$(( $(date +%s) - start ))
  line=$(grep -E "[0-9]+ (passed|failed|error|skipped|deselected)|no tests ran" "$log" | tail -n1)
  p=$(count passed "$line"); f=$(count failed "$line"); e=$(count error "$line")
  s=$(count skipped "$line"); dsel=$(count deselected "$line")
  case "$status" in ok|no-tests) ;; *) OVERALL=1 ;; esac
  ROWS+=("$(printf '%-28s %-11s %6s %6s %6s %7s %10s %6ss' "$c" "$status" "$p" "$f" "$e" "$s" "$dsel" "$dur")")
  tail -n 3 "$log"
done

echo
printf '%-28s %-11s %6s %6s %6s %7s %10s %7s\n' component status passed failed errors skipped deselected time
printf '%.0s-' {1..92}; echo
printf '%s\n' "${ROWS[@]}"
echo "markers: ${MARKEXPR:-<all tests>}   logs: $LOGDIR"
exit $OVERALL
