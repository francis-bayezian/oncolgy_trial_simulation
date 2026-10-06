"""Build evidence corpus v2 (5,000 completed oncology trials started before 2023) into data/corpus_v2, isolated from the
frozen v1 asset. The model-call cache of the v1 build is copied first, so the 1,000 v1 trials cost no new calls.
Resumable: trials already built are skipped. Never processes a trial in data/manifest/corpus_v2_holdout.json.

Usage: .venv/Scripts/python.exe scripts/run_corpus_v2_build.py [--workers 6] [--limit N]
"""

import argparse
import json
import shutil
from pathlib import Path

ROOT = Path("data/corpus_v2")


def main() -> None:
    from clinical_asset.batch import build

    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    (ROOT / "cache").mkdir(parents=True, exist_ok=True)
    if not (ROOT / "cache" / "llm").exists():
        shutil.copytree(Path("data/cache/llm"), ROOT / "cache" / "llm")
    if Path("data/cache/umls_links.json").exists() and not (ROOT / "cache" / "umls_links.json").exists():
        shutil.copy2(Path("data/cache/umls_links.json"), ROOT / "cache" / "umls_links.json")
    summary = build(Path("data/manifest/corpus_v2_5000.json"), Path("data/manifest/corpus_v2_holdout.json"), data_dir=ROOT,
                    workers=a.workers, limit=a.limit)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
