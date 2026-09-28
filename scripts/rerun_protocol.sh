#!/usr/bin/env bash
# The whole pipeline for one protocol, every stage locked at one version, stopping at the first failure:
# StudySpec -> (facts) -> population -> eligibility -> cohorts -> outcome model -> science engine -> planning report
# -> simulated safety; then, only when a registry record is given, the registry comparisons.
# usage: scripts/rerun_protocol.sh ID PDF SPEC_DIR ENGINE(tte|binary|escalation) VERSION FACTS(existing version | new) OUT_ROOT [NCT FETCHED_AT]
set -euo pipefail
ID=$1; PDF=$2; SPEC_DIR=$3; ENGINE=$4; V=$5; FACTS=$6; OUT_ROOT=$7; NCT=${8:-}; FETCHED=${9:-}
export PYTHONPATH=. PYTHONIOENCODING=utf-8
P=".venv/Scripts/python.exe -m clinical_asset.cli"; L=data/locked/$ID; T=$OUT_ROOT/$ID/v$V
ASSET=data/planning_asset_v2_2/operational; ASSET_LOCK=data/locked/planning_asset/operational_v2.2.0/lock.json
SAFETY=${SAFETY_ASSET:-data/locked/safety_asset/v3.1.0}
mkdir -p "$T"
lock() { if [ -d "$2" ]; then echo "exists $2 (kept)"; return; fi
  $P lock-stage --stage "$1" --out "$2" --kind "$3" --version "$V" "${@:4}" --code clinical_asset > /dev/null; echo "locked $2"; }
locked() { [ -d "$1" ]; }

if [ -d "$L/studyspec_v$V" ]; then echo "exists $L/studyspec_v$V (resuming)"; else
  $P lock-studyspec --spec "$SPEC_DIR" --protocol "$PDF" --out "$L/studyspec_v$V" --version "$V" > /dev/null; echo "locked $L/studyspec_v$V"; fi
SPEC=$L/studyspec_v$V
# the protocol's condition and any agent new to the drug-class map are mapped by the evidence build's mappers (cached)
$P map-protocol-conditions --studyspec "$SPEC" > "$T/condition_family.json"
$P extend-drug-classes --studyspec "$SPEC" --created "$(date +%F)" > "$T/drug_classes.json"
if [ "$FACTS" = new ] && ! locked "$L/protocol_facts_v$V"; then
  $P extract-facts --protocol "$PDF" --out "$T/facts" > "$T/facts.log"
  $P lock-facts --facts "$T/facts" --protocol "$PDF" --out "$L/protocol_facts_v$V" --version "$V" > /dev/null; echo "locked $L/protocol_facts_v$V"
  FACTS_LOCK=$L/protocol_facts_v$V
elif [ "$FACTS" = new ]; then
  FACTS_LOCK=$L/protocol_facts_v$V
else
  FACTS_LOCK=$L/protocol_facts_v$FACTS
fi
locked "$L/population_v$V" || $P build-population --studyspec "$SPEC" --facts "$FACTS_LOCK" --out "$T/population" --n 10000 --seed 20260927 > /dev/null
lock "$T/population" "$L/population_v$V" population --input studyspec=$SPEC/lock.json --input facts=$FACTS_LOCK/lock.json \
  --input simulation_parameters_v3=data/simulation_parameters_v3/manifest.json
locked "$L/eligibility_v$V" || $P build-eligibility --studyspec "$SPEC" --population "$L/population_v$V" --out "$T/eligibility" > /dev/null
lock "$T/eligibility" "$L/eligibility_v$V" eligibility --input studyspec=$SPEC/lock.json --input population=$L/population_v$V/lock.json
locked "$L/cohorts_v$V" || $P build-cohorts --studyspec "$SPEC" --population "$L/population_v$V" --eligibility "$L/eligibility_v$V" --out "$T/cohorts" --seed 20260927 > /dev/null
lock "$T/cohorts" "$L/cohorts_v$V" cohorts --input studyspec=$SPEC/lock.json --input population=$L/population_v$V/lock.json \
  --input eligibility=$L/eligibility_v$V/lock.json
locked "$L/outcomes_v$V" || $P build-outcome-model --studyspec "$SPEC" --facts "$FACTS_LOCK" --out "$T/outcomes" > "$T/outcomes.log"
lock "$T/outcomes" "$L/outcomes_v$V" outcomes --input studyspec=$SPEC/lock.json --input facts=$FACTS_LOCK/lock.json \
  --input simulation_parameters_v3=data/simulation_parameters_v3/manifest.json --input simulation_parameters_v2=data/simulation_parameters_v2/manifest.json
OUT=$L/outcomes_v$V

if [ "$ENGINE" = auto ]; then
  ENGINE=$(.venv/Scripts/python.exe -c "
import json
s = json.load(open('$SPEC/studyspec.json', encoding='utf-8'))
esc = any(r['kind'] == 'dose_escalation' for r in s.get('decision_rules') or [])
tte = any(e['role'] == 'primary' and e.get('type') == 'time_to_event' for e in s['endpoints']) and len(s['arms']) > 1
print('escalation' if esc else 'tte' if tte else 'binary')")
  echo "engine chosen from the StudySpec: $ENGINE"
fi
unresolved_results() {   # the engine could not run: an UNRESOLVED result with its reason, and the chain goes on
  mkdir -p "$T/results"; .venv/Scripts/python.exe -c "
import json, sys; json.dump({'status': 'UNRESOLVED', 'engine': '$ENGINE', 'reason': open('$T/results.log', encoding='utf-8', errors='replace').read()[-600:]},
open('$T/results/unresolved_results.json', 'w'), indent=1)"; }
if ! locked "$L/results_v$V"; then
case "$ENGINE" in
  tte)
    $P run-trials --studyspec "$SPEC" --population "$L/population_v$V" --eligibility "$L/eligibility_v$V" --cohorts "$L/cohorts_v$V" \
      --outcomes "$OUT" --out "$T/results" > "$T/results.log" 2>&1 || unresolved_results
    lock "$T/results" "$L/results_v$V" results --input studyspec=$SPEC/lock.json --input population=$L/population_v$V/lock.json \
      --input eligibility=$L/eligibility_v$V/lock.json --input cohorts=$L/cohorts_v$V/lock.json --input outcomes=$OUT/lock.json ;;
  binary)
    $P run-binary --studyspec "$SPEC" --facts "$FACTS_LOCK" --out "$T/results" > "$T/results.log" 2>&1 || unresolved_results
    lock "$T/results" "$L/results_v$V" results --input studyspec=$SPEC/lock.json --input facts=$FACTS_LOCK/lock.json \
      --input cohorts=$L/cohorts_v$V/lock.json ;;
  escalation)
    $P run-escalation --studyspec "$SPEC" --out "$T/results" > "$T/results.log" 2>&1 || unresolved_results
    lock "$T/results" "$L/results_v$V" results --input studyspec=$SPEC/lock.json ;;
esac
fi

$P build-planning-report --studyspec "$SPEC" --cohorts "$L/cohorts_v$V" --eligibility "$L/eligibility_v$V" --results "$L/results_v$V" \
  --outcomes "$OUT" --accrual-asset "$ASSET" --out "$T/planning" $([ -z "$NCT" ] && echo --blind) > /dev/null
lock "$T/planning" "$L/planning_v$V" planning --input studyspec=$SPEC/lock.json --input cohorts=$L/cohorts_v$V/lock.json \
  --input eligibility=$L/eligibility_v$V/lock.json --input results=$L/results_v$V/lock.json --input outcomes=$OUT/lock.json \
  --input accrual_asset=$ASSET_LOCK
$P run-safety --outcomes "$OUT" --cohorts "$L/cohorts_v$V" --out "$T/safety" --safety-asset "$SAFETY" > /dev/null
lock "$T/safety" "$L/safety_v$V" safety --input outcomes=$OUT/lock.json --input cohorts=$L/cohorts_v$V/lock.json \
  --input safety_asset=$SAFETY/lock.json

$P build-trial-outputs --studyspec "$SPEC" --eligibility "$L/eligibility_v$V" --cohorts "$L/cohorts_v$V" --outcomes "$OUT"   --safety "$L/safety_v$V" --planning "$L/planning_v$V" --results "$L/results_v$V" --accrual-asset "$ASSET" --out "$T/outputs" > /dev/null
lock "$T/outputs" "$L/outputs_v$V" outputs --input studyspec=$SPEC/lock.json --input eligibility=$L/eligibility_v$V/lock.json   --input cohorts=$L/cohorts_v$V/lock.json --input outcomes=$OUT/lock.json --input safety=$L/safety_v$V/lock.json   --input planning=$L/planning_v$V/lock.json --input results=$L/results_v$V/lock.json

[ -z "$NCT" ] && { echo "predictions locked; no registry comparison (blind)"; exit 0; }
REG=data/holdout_comparison/$NCT.json
case "$ENGINE" in
  tte) $P compare-registry --results "$L/results_v$V" --population "$L/population_v$V" --cohorts "$L/cohorts_v$V" --outcomes "$OUT" \
         --registry "$REG" --fetched-at "$FETCHED" --out "$T/comparison" > /dev/null ;;
  binary) $P compare-registry-binary --results "$L/results_v$V" --registry "$REG" --fetched-at "$FETCHED" --out "$T/comparison" > /dev/null ;;
  escalation) $P compare-registry-escalation --results "$L/results_v$V" --registry "$REG" --fetched-at "$FETCHED" --out "$T/comparison" > /dev/null ;;
esac
lock "$T/comparison" "$L/registry_comparison_v$V" registry_comparison --input results=$L/results_v$V/lock.json --input registry_$NCT=$REG
$P compare-registry-planning --planning "$L/planning_v$V" --registry "$REG" --fetched-at "$FETCHED" --out "$T/planning_comparison" > /dev/null
lock "$T/planning_comparison" "$L/planning_comparison_v$V" planning_comparison --input planning=$L/planning_v$V/lock.json --input registry_$NCT=$REG
$P compare-registry-safety --results "$L/safety_v$V" --registry "$REG" --fetched-at "$FETCHED" --out "$T/safety_comparison" > /dev/null
lock "$T/safety_comparison" "$L/safety_comparison_v$V" safety_comparison --input safety=$L/safety_v$V/lock.json --input registry_$NCT=$REG
LOCKED_AT=$(.venv/Scripts/python.exe -c "import json;print(json.load(open('$L/outputs_v$V/lock.json'))['locked_at'])")
$P compare-registry-baseline --studyspec "$SPEC" --registry "$REG" --fetched-at "$FETCHED" --locked-at "$LOCKED_AT" --out "$T/baseline_comparison" > /dev/null
lock "$T/baseline_comparison" "$L/baseline_comparison_v$V" baseline_comparison --input studyspec=$SPEC/lock.json --input registry_$NCT=$REG
echo "done $ID v$V"
