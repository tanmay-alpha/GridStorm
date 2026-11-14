#!/usr/bin/env bash
# Regenerate small reference artifacts into a scratch dir and compare them with the
# committed ones (data/artifacts/<engine>/, benchmarks/stormbench/results/) using
# scripts/compare_artifacts.py. Used by .github/workflows/scientific.yml.
#
# Usage: scripts/regenerate_reference.sh [OUT_DIR] [engine ...]
# Each engine below has: component dir, generator script (relative to the component),
# committed reference dir. A generator is invoked as
#     uv run --locked python <script> --out-dir <OUT_DIR>/<engine>
# and must write files with the same relative names as the committed reference.
# Engines whose generator or reference does not exist yet are reported NOT-CONFIGURED
# (never silently counted as passing). Exit 1 if any configured engine mismatches.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 2
OUT="${1:-$ROOT/.regen}"
shift || true
mkdir -p "$OUT"

# engine|component|generator|generator args|reference|rel_tol|abs_tol|extra compare args
# (generator args / compare args are word-split; keep them free of spaces inside values)
ENGINES=(
  "pypsa|workers/pypsa|scripts/precompute_presets.py||data/artifacts/pypsa|1e-4|1e-3|--ignore payload_sha256 --ignore wall_time_s --ignore manifest --ignore measurements"
  "pandapower|workers/pandapower|scripts/run_studies.py|--cases pglib-case14-ieee|data/artifacts/pandapower|1e-4|1e-4|--ignore-suffix _s --ignore payload_sha256 --ignore command --allow-missing --exclude index.json"
  "stormbench|packages/stormbench|scripts/generate_artifacts.py|--cases case14_ieee,case30_ieee|data/artifacts/stormbench|1e-4|1e-4|--ignore-suffix _s --ignore-suffix _bytes --ignore-suffix _mib --ignore payload_sha256 --ignore command --allow-missing --exclude index.json"
)

WANT=("$@")
status_rows=()
rc_all=0
for spec in "${ENGINES[@]}"; do
  IFS='|' read -r eng comp gen gen_args ref rtol atol cmp_args <<<"$spec"
  read -ra gen_argv <<<"$gen_args"
  read -ra cmp_argv <<<"$cmp_args"
  if [ ${#WANT[@]} -gt 0 ] && [[ ! " ${WANT[*]} " =~ \ $eng\  ]]; then continue; fi
  echo "=== $eng"
  if [ ! -f "$comp/$gen" ] || [ -z "$(find "$ref" -name '*.json' 2>/dev/null | head -n1)" ]; then
    echo "::warning::$eng: generator $comp/$gen or reference $ref/*.json missing"
    status_rows+=("$eng NOT-CONFIGURED")
    continue
  fi
  dest="$OUT/$eng"
  rm -rf "$dest"; mkdir -p "$dest"
  if ! (cd "$comp" && uv run --locked python "$gen" "${gen_argv[@]}" --out-dir "$dest"); then
    status_rows+=("$eng GENERATOR-ERROR"); rc_all=1; continue
  fi
  if python3 scripts/compare_artifacts.py "$ref" "$dest" --rel-tol "$rtol" --abs-tol "$atol" \
      --ignore engine_version "${cmp_argv[@]}"; then
    status_rows+=("$eng MATCH")
  else
    status_rows+=("$eng MISMATCH"); rc_all=1
  fi
done

echo
printf '%s\n' "${status_rows[@]}" | column -t 2>/dev/null || printf '%s\n' "${status_rows[@]}"
exit $rc_all
