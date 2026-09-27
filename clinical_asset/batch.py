"""Build the clinical asset for a manifest of trials, excluding the test holdout.

Resources (UMLS index, medspaCy, model client) load once. Trials run in parallel threads,
the run resumes where it stopped, a failing trial is logged and skipped, and a holdout trial
is never processed.
"""

import json
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .terminology import UmlsTerminology


class _LockedMentions:
    """spaCy pipelines are not thread-safe; serialise the (fast) NLP step."""

    def __init__(self, inner) -> None:
        self._inner = inner
        self._lock = threading.Lock()

    def __call__(self, text: str) -> list:
        with self._lock:
            return self._inner(text)


def load_ids(manifest: Path, holdout: Path) -> tuple[list[str], set[str]]:
    trials = [t["nct_id"] for t in json.loads(manifest.read_text(encoding="utf-8"))["trials"]]
    held = set(json.loads(holdout.read_text(encoding="utf-8"))["nct_ids"])
    return [t for t in trials if t not in held], held


def build(
    manifest: Path,
    holdout: Path,
    data_dir: Path = Path("data"),
    workers: int = 4,
    limit: int | None = None,
    force: bool = False,
    only: set[str] | None = None,
    offline_registry: bool = False,
) -> dict:
    from .cli import _LazyNLP, process_trial
    from .llm import LunaClient

    ids, held = load_ids(manifest, holdout)
    if only is not None:
        ids = [nct for nct in ids if nct in only]
    if limit:
        ids = ids[:limit]
    log_dir = data_dir / "build"
    log_dir.mkdir(parents=True, exist_ok=True)
    done = {
        nct for nct in ids
        if not force and (data_dir / "clinical-asset" / f"{nct}.json").exists()
        and (data_dir / "audit" / f"{nct}.audit.json").exists()
    }
    todo = [nct for nct in ids if nct not in done]
    terminology = UmlsTerminology(cache_path=data_dir / "cache" / "umls_links.json")
    mentions = _LockedMentions(_LazyNLP(terminology, False))
    model = LunaClient(cache_dir=data_dir / "cache" / "llm", max_calls=40 * max(len(todo), 1))
    write_lock = threading.Lock()
    counts = {"built": 0, "excluded": 0, "failed": 0, "skipped_existing": len(done)}
    start = time.perf_counter()

    def one(nct: str) -> dict:
        assert nct not in held, "holdout trial reached the build"
        try:
            return process_trial(nct, data_dir, None, True, terminology, model, mentions, offline_registry)
        except Exception as error:  # noqa: BLE001
            return {"nct_id": nct, "failed": f"{type(error).__name__}: {error}", "trace": traceback.format_exc(limit=3)}

    with ThreadPoolExecutor(max_workers=workers) as pool, open(
        log_dir / "progress.jsonl", "a", encoding="utf-8"
    ) as progress:
        futures = {pool.submit(one, nct): nct for nct in todo}
        for index, future in enumerate(as_completed(futures), 1):
            result = future.result()
            status = "failed" if "failed" in result else "excluded" if "excluded" in result else "built"
            counts[status] += 1
            with write_lock:
                progress.write(json.dumps({"status": status, **{k: v for k, v in result.items() if k != "trace"}}) + "\n")
                progress.flush()
                if status == "failed":
                    with open(log_dir / "failures.jsonl", "a", encoding="utf-8") as failures:
                        failures.write(json.dumps(result) + "\n")
                if index % 25 == 0:
                    terminology.save()
                    elapsed = time.perf_counter() - start
                    print(json.dumps({"done": index, "of": len(todo), **counts, "elapsed_min": round(elapsed / 60, 1),
                                      "eta_min": round(elapsed / index * (len(todo) - index) / 60, 1)}), flush=True)
    terminology.save()
    summary = {
        "trials_in_manifest": len(ids) + len(held & set(ids)),
        "holdout_excluded": len(held),
        **counts,
        "model_calls": model.calls,
        "input_tokens": model.input_tokens,
        "output_tokens": model.output_tokens,
        "minutes": round((time.perf_counter() - start) / 60, 1),
    }
    (log_dir / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return summary
