"""The evidence cut-off in force for a run.

Set CLINICAL_EVIDENCE_CUTOFF to an evidence-cutoff manifest (scripts/build_evidence_cutoff.py) to run the pipeline as
of its date T0: every evidence reader drops the trials the manifest lists, and the parameter, safety and operational
assets are read from their as-of-T0 builds (paths in the manifest's "assets", else the defaults below).
Without the variable, the pipeline reads the full evidence, as before.
"""

import json
import os
from functools import lru_cache
from pathlib import Path

ENV = "CLINICAL_EVIDENCE_CUTOFF"
DEFAULT_ASSETS = {"v3": "data/simulation_parameters_v3", "safety": "data/locked/safety_asset/v3.1.0",
                  "operational": "data/planning_asset_v2_2/operational"}
T0_ASSETS = {"v3": "data/simulation_parameters_v3_t0", "safety": "data/safety_asset_t0", "operational": "data/planning_asset_t0/operational"}


@lru_cache(maxsize=1)
def manifest() -> dict | None:
    path = os.environ.get(ENV)
    return json.loads(Path(path).read_text(encoding="utf-8")) if path else None


@lru_cache(maxsize=1)
def evaluated_trials() -> frozenset:
    """Trials the pipeline is evaluated on (development protocols, holdouts, the temporal showcase): never evidence."""
    ids = set()
    for f, key in (("data/manifest/development_protocols.json", "protocols"), ("data/manifest/holdout_test_trials.json", "nct_ids"),
                   ("data/manifest/temporal_showcase_v2.json", "chosen"),
                   ("data/manifest/excluded_start2023.json", "nct_ids"),       # every trial started in 2023 or later (hold-out)
                   ("data/manifest/protocols.json", "protocols"),              # every test protocol (named by NCT)
                   ("data/manifest/holdout_start2023.json", "nct_ids")):
        p = Path(f)
        if not p.exists():
            continue
        v = json.loads(p.read_text(encoding="utf-8"))[key]
        ids |= {x["nct_id"] if isinstance(x, dict) else x for x in (v if isinstance(v, list) else [v])} if v else set()
    return frozenset(ids)


def excluded() -> frozenset:
    """Trials no evidence reader may use: every evaluated trial, and under a cut-off every trial after T0."""
    m = manifest()
    return evaluated_trials() | (frozenset(m["nct_ids"]) if m else frozenset())


def asset(name: str) -> Path:
    m = manifest()
    if not m:                                   # the asset profile in force (clinical_asset.assets): v1 unless chosen
        from .assets import path

        return path({"v3": "params_v3", "safety": "safety", "operational": "operational"}[name])
    return Path((m.get("assets") or {}).get(name) or T0_ASSETS[name])


def describe() -> dict:
    m = manifest()
    return {"cutoff": None} if not m else {"cutoff": m["t0"], "excluded_trials": len(m["nct_ids"]), "manifest": os.environ.get(ENV)}
