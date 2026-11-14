#!/usr/bin/env bash
# Reproducible build of the reduced PyPSA-Eur Belgium tutorial electricity network.
# Runs the upstream Snakemake workflow inside a Linux container (pixi image), so it
# works identically on Windows/macOS/Linux hosts. Nothing is written into the GridStorm
# repo except the final copied outputs in $OUT_DIR.
#
# Usage: pipelines/pypsa-eur/build.sh <path-to-pypsa-eur-clone> <out-dir>
set -euo pipefail

PYPSA_EUR_SHA="${PYPSA_EUR_SHA:-c8209014468dbb3bf43257f45d34abc6e3c8c898}"
PIXI_IMAGE="${PIXI_IMAGE:-ghcr.io/prefix-dev/pixi:0.81.0}"
TARGET="${TARGET:-results/test-elec/networks/solved_2050.nc}"
VOLUME="${VOLUME:-gridstorm-pypsa-eur-work}"
CORES="${CORES:-1}"
BUILD_TIMEOUT_S="${BUILD_TIMEOUT_S:-2400}"

SRC="$(cd "$1" && pwd)"
OUT="$(mkdir -p "$2" && cd "$2" && pwd)"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

docker volume create "$VOLUME" >/dev/null

# MSYS_NO_PATHCONV stops Git-Bash on Windows from rewriting container paths.
# The named volume persists the clone, the pixi env, the rattler package cache and
# downloaded data, so a rerun after an interruption resumes instead of starting over.
MSYS_NO_PATHCONV=1 docker run --rm --name gridstorm-pypsa-eur-build \
  -v "$SRC:/src:ro" \
  -v "$HERE:/cfg:ro" \
  -v "$OUT:/out" \
  -v "$VOLUME:/work" \
  -e PINNED_UPSTREAM_SHA="$PYPSA_EUR_SHA" -e TARGET="$TARGET" -e CORES="$CORES" \
  -e RATTLER_CACHE_DIR=/work/.cache/rattler \
  -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 \
  "$PIXI_IMAGE" timeout --signal=TERM --kill-after=30 "$BUILD_TIMEOUT_S" bash -c '
set -euo pipefail
apt-get update -qq && apt-get install -y -qq --no-install-recommends ca-certificates git >/dev/null
git config --global --add safe.directory "*"
if [ ! -d /work/pypsa-eur/.git ]; then git clone -q /src /work/pypsa-eur; fi
cd /work/pypsa-eur
git fetch -q /src && git checkout -q "$PINNED_UPSTREAM_SHA"
test "$(git rev-parse HEAD)" = "$PINNED_UPSTREAM_SHA"
pixi install -e default --locked 2>&1 | tail -n 5
start=$(date +%s)
pixi run -e default snakemake --cores "$CORES" "$TARGET" \
  --configfile config/test/config.electricity.yaml /cfg/config.gridstorm.yaml \
  2>&1 | tee /out/snakemake.log
echo "snakemake_wall_s=$(( $(date +%s) - start ))" | tee -a /out/snakemake.log
cp resources/test-elec/networks/*.nc /out/
cp results/test-elec/networks/*.nc /out/
ls -la /out
'
