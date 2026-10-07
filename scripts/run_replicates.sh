#!/usr/bin/env bash
# N replicate simulations of one protocol from its locked extraction: each replicate draws new patients and a new trial
# (population, eligibility, cohort, safety, datasets, journey, endpoints, analysis) with its own seeds; the StudySpec,
# protocol facts, outcome model, engine results and planning report are the base run's locks (unchanged).
# Every replicate stage is locked under data/trial/runs/<ID>/v<BASE>/replicates/locked/<stage>_v<BASE>-r<NNN>.
# usage: scripts/run_replicates.sh ID BASE_VERSION N [WORKERS=4]   then: scripts/summarise_replicates.py ID BASE_VERSION
set -uo pipefail
ID=$1; V=$2; N=$3; W=${4:-4}
export PYTHONPATH=. PYTHONIOENCODING=utf-8
L=data/locked/$ID; ROOT=data/trial/runs/$ID/v$V/replicates
mkdir -p "$ROOT/locked"
FACTS=$(ls -d $L/protocol_facts_v* | sort -V | tail -1)
[ -f "data/trial/runs/$ID/v$V/condition_family.json" ] || { echo "no condition_family.json in the base run"; exit 1; }

one() {   # replicate number
  local r=$1 tag; tag=$(printf "%s-r%03d" "$V" "$r")
  local P=".venv/Scripts/python.exe -m clinical_asset.cli" S=$((20270000 + 97 * r)) T="$ROOT/r$(printf %03d "$r")" K="$ROOT/locked"
  local SPEC=$L/studyspec_v$V OUT=$L/outcomes_v$V PDF=protocols/$ID.pdf
  local SAFETY ASSET; SAFETY=$(.venv/Scripts/python.exe -c "from clinical_asset import assets; print(assets.path('safety').as_posix())")
  ASSET=$(.venv/Scripts/python.exe -c "from clinical_asset import assets; print(assets.path('operational').as_posix())")
  [ -d "$K/analysis_v$tag" ] && { echo "r$r exists"; return 0; }
  mkdir -p "$T"
  lk() { [ -d "$K/$2_v$tag" ] || $P lock-stage --stage "$1" --out "$K/$2_v$tag" --kind "$2" --version "$tag" "${@:3}" --code clinical_asset > /dev/null; }
  sk() { [ -d "$K/$1_v$tag" ] && return 0; shift; "$@"; }   # a stage already locked (e.g. reused unchanged) is skipped
  {
    sk population $P build-population --studyspec "$SPEC" --facts "$FACTS" --out "$T/population_base" --n 10000 --seed $S &&
    sk population $P augment-population --population "$T/population_base" --studyspec "$SPEC" --condition-family "data/trial/runs/$ID/v$V/condition_family.json" --out "$T/population" &&
    lk "$T/population" population --input studyspec=$SPEC/lock.json &&
    sk eligibility $P build-eligibility --studyspec "$SPEC" --population "$K/population_v$tag" --out "$T/eligibility" --seed $((S + 7)) &&
    lk "$T/eligibility" eligibility --input population=$K/population_v$tag/lock.json &&
    sk cohorts $P build-cohorts --studyspec "$SPEC" --population "$K/population_v$tag" --eligibility "$K/eligibility_v$tag" --out "$T/cohorts" --seed $((S + 1)) &&
    lk "$T/cohorts" cohorts --input eligibility=$K/eligibility_v$tag/lock.json &&
    sk safety $P run-safety --outcomes "$OUT" --cohorts "$K/cohorts_v$tag" --out "$T/safety" --safety-asset "$SAFETY" --seed $((S + 2)) &&
    lk "$T/safety" safety --input cohorts=$K/cohorts_v$tag/lock.json &&
    sk outputs $P build-trial-outputs --studyspec "$SPEC" --eligibility "$K/eligibility_v$tag" --cohorts "$K/cohorts_v$tag" --outcomes "$OUT" \
      --safety "$K/safety_v$tag" --planning "$L/planning_v$V" --results "$L/results_v$V" --accrual-asset "$ASSET" --out "$T/outputs" --seed $((S + 3)) &&
    lk "$T/outputs" outputs --input safety=$K/safety_v$tag/lock.json &&
    sk journey $P run-journey --studyspec "$SPEC" --protocol "$PDF" --cohorts "$K/cohorts_v$tag" --eligibility "$K/eligibility_v$tag" --outputs "$K/outputs_v$tag" \
      --safety "$K/safety_v$tag" --outcomes "$OUT" --facts "$FACTS" --out "$T/journey" --seed $((S + 4)) &&
    lk "$T/journey" journey --input outputs=$K/outputs_v$tag/lock.json &&
    sk endpoints $P run-endpoints --studyspec "$SPEC" --journey "$K/journey_v$tag" --safety "$K/safety_v$tag" --facts "$FACTS" --out "$T/endpoints" --seed $((S + 5)) &&
    lk "$T/endpoints" endpoints --input journey=$K/journey_v$tag/lock.json &&
    sk analysis $P build-analysis-results --studyspec "$SPEC" --journey "$K/journey_v$tag" --safety "$K/safety_v$tag" --eligibility "$K/eligibility_v$tag" \
      --outcomes "$OUT" --facts "$FACTS" --out "$T/analysis" --seed $((S + 6)) &&
    lk "$T/analysis" analysis --input journey=$K/journey_v$tag/lock.json
  } > "$T/replicate.log" 2>&1 && echo "r$r done $(date +%T)" || echo "r$r FAILED: $(tail -1 "$T/replicate.log")"
}
export -f one; export ID V L ROOT FACTS
seq 1 "$N" | xargs -P "$W" -I{} bash -c 'one {}'
echo "===== replicates done $(date +%T)"
