#!/usr/bin/env bash
# One protocol, with self-review (L059): run every stage, audit, review; when the review applied corrections from
# evidence, run again as the next version and review again, up to MAX_ROUNDS; then stop with the open questions.
# usage: scripts/run_with_review.sh ID PDF SPEC_DIR FIRST_VERSION [MAX_ROUNDS=3]
# e.g.   scripts/run_with_review.sh NCT05722015 protocols/presentation/NCT05722015.pdf data/protocol_specs/NCT05722015 1.0.3
set -uo pipefail
ID=$1; PDF=$2; SPEC=$3; V=$4; MAX=${5:-3}
export PYTHONPATH=. PYTHONIOENCODING=utf-8
P=".venv/Scripts/python.exe -m clinical_asset.cli"
next() { local a b c; IFS=. read -r a b c <<< "$1"; echo "$a.$b.$((c + 1))"; }
for ((round = 1; round <= MAX; round++)); do
  R=data/trial/runs/$ID/v$V
  mkdir -p "$R"
  echo "$(date +%T) round $round: run v$V"
  bash scripts/rerun_protocol.sh "$ID" "$PDF" "$SPEC" auto "$V" new data/trial/runs > "$R/simulation.log" 2>&1 \
    || { echo "$(date +%T) stages FAILED at v$V: $(tail -2 "$R/simulation.log")"; exit 1; }
  $P audit-run --id "$ID" --version "$V" --out "$R/audit" > "$R/audit.log" 2>&1
  echo "$(date +%T) round $round: review v$V"
  $P review-run --id "$ID" --version "$V" > "$R/review.log" 2>&1
  code=$?
  tail -n 12 "$R/review.log"
  if [ "$code" -ne 10 ]; then
    echo "$(date +%T) no further corrections from evidence; final version v$V; open questions: $R/review/OPEN_QUESTIONS.md"
    exit 0
  fi
  V=$(next "$V")
done
echo "$(date +%T) stopped after $MAX rounds; last version reviewed: see data/trial/runs/$ID/"
