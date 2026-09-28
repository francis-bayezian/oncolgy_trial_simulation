#!/usr/bin/env bash
# Standard chain after the science stage: outcome model (if missing) -> planning report -> safety results, all locked;
# then the registry comparisons (planning timeline, adverse events), each locked. Stops at the first failure.
# usage: scripts/registry_comparisons.sh ID NCT REGISTRY_FETCHED_AT STUDYSPEC_V ELIGIBILITY_V COHORTS_V BLIND(0|1) PLANNING_V [ASSET_DIR ASSET_LOCK]
set -euo pipefail
ID=$1; NCT=$2; FETCHED=$3; SV=$4; EV=$5; CV=$6; BLIND=$7; PV=${8:-1.0.0}
ASSET=${9:-data/planning_asset_v1/accrual}; ASSET_LOCK=${10:-data/locked/planning_asset/accrual_v1.0.0/lock.json}
export PYTHONPATH=. PYTHONIOENCODING=utf-8
P=".venv/Scripts/python.exe -m clinical_asset.cli"; L=data/locked/$ID; T=${TRIAL_ROOT:-data/trial/unblinded}/$ID; REG=data/holdout_comparison/$NCT.json
SPEC=$L/studyspec_v$SV; ELIG=$L/eligibility_v$EV; COH=$L/cohorts_v$CV; RES=$L/results_v1.0.0
lock() { $P lock-stage --stage "$1" --out "$2" --kind "$3" --version "$4" "${@:5}" --code clinical_asset > /dev/null; echo "locked $2"; }

if [ ! -d "$L/outcomes_v1.0.0" ]; then
  $P build-outcome-model --studyspec "$SPEC" --facts "$L/protocol_facts_v1.0.0" --out "$T/outcomes" > "$T/outcomes.log"
  lock "$T/outcomes" "$L/outcomes_v1.0.0" outcomes 1.0.0 --input studyspec=$SPEC/lock.json --input facts=$L/protocol_facts_v1.0.0/lock.json \
    --input simulation_parameters_v2_toxicity=data/simulation_parameters_v2/toxicity/censored_toxicity_parameters.parquet \
    --input simulation_parameters_v2_classes=data/simulation_parameters_v2/hierarchy/drug_class_map.parquet
fi
OUT=$L/outcomes_v1.0.0

if [ ! -d "$L/planning_v$PV" ]; then
  rm -rf "$T/planning"
  $P build-planning-report --studyspec "$SPEC" --cohorts "$COH" --eligibility "$ELIG" --results "$RES" --outcomes "$OUT" \
    --accrual-asset "$ASSET" --out "$T/planning" $([ "$BLIND" = 1 ] && echo --blind) > /dev/null
  lock "$T/planning" "$L/planning_v$PV" planning "$PV" --input studyspec=$SPEC/lock.json --input cohorts=$COH/lock.json \
    --input eligibility=$ELIG/lock.json --input results=$RES/lock.json --input outcomes=$OUT/lock.json \
    --input accrual_asset=$ASSET_LOCK
fi
if [ ! -d "$L/safety_v1.0.0" ]; then
  $P run-safety --outcomes "$OUT" --cohorts "$COH" --out "$T/safety" > /dev/null
  lock "$T/safety" "$L/safety_v1.0.0" safety 1.0.0 --input outcomes=$OUT/lock.json --input cohorts=$COH/lock.json
fi

version() { local n=0; while [ -d "$L/$1_v1.$n.0" ]; do n=$((n+1)); done; echo "1.$n.0"; }

rm -rf "$T/planning_comparison"; [ "${PLANNING_ONLY:-0}" = 1 ] || rm -rf "$T/safety_comparison"
$P compare-registry-planning --planning "$L/planning_v$PV" --registry "$REG" --fetched-at "$FETCHED" --out "$T/planning_comparison" > /dev/null
lock "$T/planning_comparison" "$L/planning_comparison_v$(version planning_comparison)" planning_comparison "$(version planning_comparison)" \
  --input planning=$L/planning_v$PV/lock.json --input registry_$NCT=$REG
[ "${PLANNING_ONLY:-0}" = 1 ] && exit 0
$P compare-registry-safety --results "$L/safety_v1.0.0" --registry "$REG" --fetched-at "$FETCHED" --out "$T/safety_comparison" > /dev/null
lock "$T/safety_comparison" "$L/safety_comparison_v$(version safety_comparison)" safety_comparison "$(version safety_comparison)" \
  --input safety=$L/safety_v1.0.0/lock.json --input registry_$NCT=$REG
