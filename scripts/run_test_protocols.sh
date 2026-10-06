#!/usr/bin/env bash
# The pipeline on every test protocol in data/manifest/protocols.json (named by NCT), each locked at one version, then
# audited. Facts reuse the latest locked facts of each protocol (else new). Extra environment (e.g. V3_DIR, SAFETY_ASSET,
# OPERATIONAL_ASSET) selects the asset versions, so the same protocols can be run on the v1 and the v2 assets.
# usage: scripts/run_test_protocols.sh VERSION
V=${1:?version}
export PYTHONPATH=. PYTHONIOENCODING=utf-8
P=".venv/Scripts/python.exe -m clinical_asset.cli"
.venv/Scripts/python.exe -c "
import json
from pathlib import Path
for p in json.load(open('data/manifest/protocols.json', encoding='utf-8'))['protocols']:
    facts = sorted(Path(p['locked']).glob('protocol_facts_v*'), key=lambda d: tuple(int(x) for x in d.name.rsplit('_v', 1)[1].split('.')))
    print('|'.join([p['nct_id'], p['pdf'], p['spec_dir'], facts[-1].name.rsplit('_v', 1)[1] if facts else 'new']))
" | while IFS='|' read -r ID PDF SPEC FACTS; do
  FACTS=${FACTS%$'\r'}                       # Windows Python prints CRLF: '1.0.0\r' is no lock directory
  echo "===== $ID $(date +%T)"
  mkdir -p data/trial/runs/$ID/v$V
  bash scripts/rerun_protocol.sh "$ID" "$PDF" "$SPEC" auto "$V" "$FACTS" data/trial/runs > data/trial/runs/$ID/v$V/chain.log 2>&1 || echo "chain stopped: $(tail -1 data/trial/runs/$ID/v$V/chain.log)"
  $P audit-run --id "$ID" --version "$V" --out data/trial/runs/$ID/v$V/audit > /dev/null 2>&1
  grep -m1 "COMPLETE\|INCOMPLETE" data/trial/runs/$ID/v$V/audit/completeness.md
done
echo "===== done $(date +%T)"
