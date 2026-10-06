"""Asset profiles: which evidence corpus and which built assets a run reads (and a build writes).

Set CLINICAL_ASSET_PROFILE to choose (default v1, the assets every earlier run used):

* v1: the 1,000-trial evidence corpus and the assets built from it (frozen);
* v2: the 5,000-trial corpus of trials started before 2023 (data/corpus_v2) and the assets built from it.

Every builder and reader asks path(key) instead of naming a directory, so the same protocols can be run on either
profile and compared. An evidence cut-off (clinical_asset.cutoff) still applies on top of either profile.
"""

import os
from pathlib import Path

ENV = "CLINICAL_ASSET_PROFILE"
PROFILES = {
    "v1": {"raw_ctgov": "data/raw/ctgov", "asset": "data/asset_v1", "params_v1": "data/simulation_parameters_v1",
           "params_v2": "data/simulation_parameters_v2", "params_v3": "data/simulation_parameters_v3",
           "safety": "data/locked/safety_asset/v3.1.0", "safety_build": "data/safety_asset_v3",
           "operational": "data/planning_asset_v2_2/operational", "spa_work": "data/spa_work"},
    "v2": {"raw_ctgov": "data/corpus_v2/raw/ctgov", "asset": "data/corpus_v2/asset_v2", "params_v1": "data/corpus_v2/simulation_parameters_v1",
           "params_v2": "data/corpus_v2/simulation_parameters_v2", "params_v3": "data/corpus_v2/simulation_parameters_v3",
           "safety": "data/corpus_v2/safety_asset", "safety_build": "data/corpus_v2/safety_asset",
           "operational": "data/corpus_v2/operational", "spa_work": "data/spa_work"},
}


def profile() -> str:
    name = os.environ.get(ENV, "v1")
    if name not in PROFILES:
        raise ValueError(f"unknown asset profile {name!r}; known: {sorted(PROFILES)}")
    return name


def path(key: str) -> Path:
    return Path(PROFILES[profile()][key])


def family_map() -> Path:
    """The disease-family map of the profile's parameter build (V2 hierarchy)."""
    return path("params_v2") / "hierarchy" / "disease_family_map.parquet"
