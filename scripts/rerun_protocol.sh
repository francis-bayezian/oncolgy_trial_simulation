#!/usr/bin/env bash
# The whole pipeline for one protocol, every stage locked at one version, stopping at the first failure:
# StudySpec -> (facts) -> population -> eligibility -> cohorts -> outcome model -> science engine -> planning report
# -> simulated safety; then, only when a registry record is given, the registry comparisons.
# usage: scripts/rerun_protocol.sh ID PDF SPEC_DIR ENGINE(tte|binary|escalation) VERSION FACTS(existing version | new) OUT_ROOT [NCT FETCHED_AT]
set -euo pipefail
ID=$1; PDF=$2; SPEC_DIR=$3; ENGINE=$4; V=$5; FACTS=$6; OUT_ROOT=$7; NCT=${8:-}; FETCHED=${9:-}
export PYTHONPATH=. PYTHONIOENCODING=utf-8
P=".venv/Scripts/python.exe -m clinical_asset.cli"; L=data/locked/$ID; T=$OUT_ROOT/$ID/v$V
# asset paths come from the asset profile (CLINICAL_ASSET_PROFILE: v1 default, v2 = the 5,000-trial corpus), unless set
profile_path() { .venv/Scripts/python.exe -c "from clinical_asset import assets; print(assets.path('$1').as_posix())"; }
ASSET=${OPERATIONAL_ASSET:-$(profile_path operational)}
ASSET_LOCK=${OPERATIONAL_ASSET_LOCK:-$( [ -f "$ASSET/../lock.json" ] && echo "$ASSET/../lock.json" || ( [ -f "$ASSET/lock.json" ] && echo "$ASSET/lock.json" ) || echo data/locked/planning_asset/operational_v2.2.0/lock.json)}
V3_DIR=${V3_DIR:-$(profile_path params_v3)}   # an as-of-T0 build under CLINICAL_EVIDENCE_CUTOFF
SAFETY=${SAFETY_ASSET:-$(profile_path safety)}
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
if ! locked "$L/population_v$V"; then     # demographics (V3), then evidence-based baseline variables (ECOG, weight, height)
  $P build-population --studyspec "$SPEC" --facts "$FACTS_LOCK" --out "$T/population_base" --n 10000 --seed 20260927 > /dev/null
  $P augment-population --population "$T/population_base" --studyspec "$SPEC" --condition-family "$T/condition_family.json" --out "$T/population" > /dev/null
fi
lock "$T/population" "$L/population_v$V" population --input studyspec=$SPEC/lock.json --input facts=$FACTS_LOCK/lock.json \
  --input simulation_parameters_v3=$V3_DIR/manifest.json
locked "$L/eligibility_v$V" || $P build-eligibility --studyspec "$SPEC" --population "$L/population_v$V" --out "$T/eligibility" > /dev/null
lock "$T/eligibility" "$L/eligibility_v$V" eligibility --input studyspec=$SPEC/lock.json --input population=$L/population_v$V/lock.json
locked "$L/cohorts_v$V" || $P build-cohorts --studyspec "$SPEC" --population "$L/population_v$V" --eligibility "$L/eligibility_v$V" --out "$T/cohorts" --seed 20260927 > /dev/null
lock "$T/cohorts" "$L/cohorts_v$V" cohorts --input studyspec=$SPEC/lock.json --input population=$L/population_v$V/lock.json \
  --input eligibility=$L/eligibility_v$V/lock.json
locked "$L/outcomes_v$V" || $P build-outcome-model --studyspec "$SPEC" --facts "$FACTS_LOCK" --out "$T/outcomes" > "$T/outcomes.log"
lock "$T/outcomes" "$L/outcomes_v$V" outcomes --input studyspec=$SPEC/lock.json --input facts=$FACTS_LOCK/lock.json \
  --input simulation_parameters_v3=$V3_DIR/manifest.json --input simulation_parameters_v2=data/simulation_parameters_v2/manifest.json
OUT=$L/outcomes_v$V

if [ "$ENGINE" = auto ]; then
  ENGINE=$(.venv/Scripts/python.exe -m clinical_asset.trial.engine_choice "$SPEC/studyspec.json")
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
  ni)
    $P run-ni-binary --studyspec "$SPEC" --facts "$FACTS_LOCK" --out "$T/results" > "$T/results.log" 2>&1 || unresolved_results
    lock "$T/results" "$L/results_v$V" results --input studyspec=$SPEC/lock.json --input facts=$FACTS_LOCK/lock.json ;;
  continuous)
    $P run-continuous --studyspec "$SPEC" --out "$T/results" > "$T/results.log" 2>&1 || unresolved_results
    lock "$T/results" "$L/results_v$V" results --input studyspec=$SPEC/lock.json ;;
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

locked "$L/journey_v$V" || $P run-journey --studyspec "$SPEC" --protocol "$PDF" --cohorts "$L/cohorts_v$V" --eligibility "$L/eligibility_v$V"   --outputs "$L/outputs_v$V" --safety "$L/safety_v$V" --outcomes "$OUT" --facts "$FACTS_LOCK" --out "$T/journey" > "$T/journey.log" 2>&1
lock "$T/journey" "$L/journey_v$V" journey --input studyspec=$SPEC/lock.json --input cohorts=$L/cohorts_v$V/lock.json   --input outputs=$L/outputs_v$V/lock.json --input safety=$L/safety_v$V/lock.json --input outcomes=$OUT/lock.json --input facts=$FACTS_LOCK/lock.json

locked "$L/endpoints_v$V" || $P run-endpoints --studyspec "$SPEC" --journey "$L/journey_v$V" --safety "$L/safety_v$V" --facts "$FACTS_LOCK" \
  --out "$T/endpoints" > "$T/endpoints.log" 2>&1
lock "$T/endpoints" "$L/endpoints_v$V" endpoints --input studyspec=$SPEC/lock.json --input journey=$L/journey_v$V/lock.json \
  --input safety=$L/safety_v$V/lock.json --input facts=$FACTS_LOCK/lock.json

locked "$L/analysis_v$V" || $P build-analysis-results --studyspec "$SPEC" --journey "$L/journey_v$V" --safety "$L/safety_v$V"   --eligibility "$L/eligibility_v$V" --outcomes "$OUT" --facts "$FACTS_LOCK" --out "$T/analysis" > "$T/analysis.log" 2>&1
lock "$T/analysis" "$L/analysis_v$V" analysis --input studyspec=$SPEC/lock.json --input journey=$L/journey_v$V/lock.json   --input safety=$L/safety_v$V/lock.json --input eligibility=$L/eligibility_v$V/lock.json --input outcomes=$OUT/lock.json

[ -z "$NCT" ] && { echo "predictions locked; no registry comparison"; exit 0; }
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
