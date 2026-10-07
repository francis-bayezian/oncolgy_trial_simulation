#!/usr/bin/env bash
# The v2 assets from evidence asset v2 (5,000 trials started before 2023), in dependency order, under data/corpus_v2:
#   V1 parameters -> V2 parameters -> safety asset (calibrated) -> operational asset -> V3 parameters.
# Every step reads and writes through the asset profile (CLINICAL_ASSET_PROFILE=v2). Each step is skipped when its
# manifest already exists, so a stopped chain resumes; a failing step stops the chain.
# usage (detached): nohup bash scripts/build_assets_v2.sh > data/corpus_v2/build/assets_chain.log 2>&1 &
set -uo pipefail
export CLINICAL_ASSET_PROFILE=v2 PYTHONPATH=. PYTHONIOENCODING=utf-8
P=".venv/Scripts/python.exe -m clinical_asset.cli"
B=data/corpus_v2/build
TODAY=$(date +%F)
step() {  # name, done-marker, command...
  local name=$1 marker=$2; shift 2
  if [ -e "$marker" ]; then echo "$(date +%T) skip $name (done)"; return 0; fi
  echo "$(date +%T) start $name"
  "$@" > "$B/$name.log" 2>&1 || { echo "$(date +%T) FAILED $name: $(tail -2 "$B/$name.log")"; exit 1; }
  echo "$(date +%T) done $name"
}
# a V1-parameter build started earlier: wait for it instead of starting a second one
while pgrep -f "clinical_asset.cli build-parameters$" > /dev/null 2>&1 || powershell -NoProfile -Command \
  "if (Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | Where-Object { \$_.CommandLine -match 'build-parameters\$' }) { exit 0 } else { exit 1 }" > /dev/null 2>&1; do
  sleep 60
done
step params_v1 data/corpus_v2/simulation_parameters_v1/manifest.json $P build-parameters
step params_v2 data/corpus_v2/simulation_parameters_v2/manifest.json $P build-parameters-v2
step safety data/corpus_v2/safety_asset/manifest.json $P build-safety-asset-v3 --created "$TODAY" --workers "${SAFETY_WORKERS:-2}"   # 6 workers ran out of memory on 5,000 trials
step operational data/corpus_v2/operational/manifest.json $P build-operational-asset --holdout data/manifest/corpus_v2_holdout.json \
  --family-map data/corpus_v2/simulation_parameters_v2/hierarchy/disease_family_map.parquet --out data/corpus_v2/operational --created "$TODAY"
step params_v3 data/corpus_v2/simulation_parameters_v3/manifest.json $P build-parameters-v3
echo "$(date +%T) all v2 assets built"
