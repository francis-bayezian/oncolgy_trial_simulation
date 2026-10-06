#!/usr/bin/env bash
# The whole pipeline for ANY protocol PDF, with nothing protocol-specific:
#   protocol extraction (compile + facts) -> patient generation -> screening and eligibility -> cohort -> outcome model
#   -> primary engine (chosen from the StudySpec) -> planning -> safety -> outputs -> patient journey -> endpoint results
# every stage locked at one version, then a completeness audit (exit 3 when anything is undetermined or unresolved).
# usage: scripts/run_pipeline.sh ID PROTOCOL_PDF [VERSION=4.0.0] [SAP_PDF]
set -euo pipefail
ID=$1; PDF=$2; V=${3:-4.0.0}; SAP=${4:-}
export PYTHONPATH=. PYTHONIOENCODING=utf-8
P=".venv/Scripts/python.exe -m clinical_asset.cli"
SPEC_DIR=data/protocol_specs/$ID
OUT_ROOT=data/trial/runs
mkdir -p "$OUT_ROOT/$ID/v$V"
if [ ! -f "$SPEC_DIR/studyspec.json" ]; then
  echo "compiling $PDF"
  $P compile-protocol --protocol "$PDF" $([ -n "$SAP" ] && echo --sap "$SAP") --out "$SPEC_DIR" > "$OUT_ROOT/$ID/v$V/compile.log" 2>&1
fi
# targeted, agentic resolution of the items the compile still gets wrong (only those items), then the accuracy report
$P resolve-protocol --spec "$SPEC_DIR" --protocol "$PDF" > "$OUT_ROOT/$ID/v$V/resolve.log" 2>&1
.venv/Scripts/python.exe -c "
from pathlib import Path
from clinical_asset.protocol.accuracy import write
d = write(Path('$SPEC_DIR'), Path('$OUT_ROOT/$ID/v$V/extraction'))
print(f\"extraction: {d['faithful']} of {d['items_scored']} rule items faithful; target 100%: {'MET' if d['target_met'] else 'NOT MET'}\")"
scripts/rerun_protocol.sh "$ID" "$PDF" "$SPEC_DIR" auto "$V" new "$OUT_ROOT"
$P audit-run --id "$ID" --version "$V" --out "$OUT_ROOT/$ID/v$V/audit"
