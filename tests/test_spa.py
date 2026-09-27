"""Simulation Parameter Asset milestone 1: canonicalisation, evidence rules and models."""

import hashlib
import json
import math
import shutil
from pathlib import Path

import numpy as np
import pytest

from clinical_asset.spa.canonical import canonical_outcome, parse_times, statistic_family
from clinical_asset.spa.evidence import atomize, load_frozen_profiles
from clinical_asset.spa.fit import normalise_comparison
from clinical_asset.spa.models import BetaBinomial, DirichletMultinomial, NormalRandomEffects


def test_outcome_names_map_to_one_variable_but_keep_their_statistic_and_time() -> None:
    assert canonical_outcome("Progression Free Survival (PFS)")["variable"] == "progression_free_survival"
    assert canonical_outcome("Median PFS")["variable"] == "progression_free_survival"
    five_year = canonical_outcome("5 Year Overall Survival")
    assert five_year["variable"] == "overall_survival"
    assert statistic_family(five_year, {"statistic": "percentage", "unit": "percent"}) == "survival_probability"
    assert statistic_family(five_year, {"statistic": "median", "unit": "month"}) == "median_time"
    assert parse_times("5 Year Overall Survival") == [(5.0, "year")]
    # Distinct endpoints are never merged.
    assert canonical_outcome("Event-free Survival")["variable"] == "event_free_survival"
    assert canonical_outcome("Number of Participants With Objective Response by BICR")["variable"] == "objective_response_rate"
    # Safety wording is not an efficacy outcome.
    assert canonical_outcome("Number of Participants With Treatment-related AEs") is None


def _profile(efficacy: dict) -> dict:
    return {"profile_id": "NCT1-00", "profile_type": "study_arm", "source": {"nct": "NCT1", "registry_group": "A"},
            "cancer": {}, "treatment": {"regimen": "drug a"}, "efficacy": efficacy}


def test_mortality_is_never_read_as_survival_probability() -> None:
    rows, _ = atomize([_profile({"x": [{"statistic": "percentage", "value": 12.0, "rate": 0.12, "N": 100, "unit": "percent",
                                         "measure": "Percentage of Participants Who Died (Overall Survival)"}]})])
    [row] = rows
    assert row["variable"] == "all_cause_death" and row["domain"] == "mortality"


def test_marginals_never_become_joint_evidence() -> None:
    efficacy = {"orr": [{"statistic": "count", "value": 10, "N": 40, "rate": 0.25, "unit": "participants",
                         "measure": "Objective Response Rate"}]}
    profile = {**_profile(efficacy), "patient_profile": {"n": 40, "age": {"mean": 60, "sd": 8}, "sex": {"female": 20, "male": 20}}}
    rows, _ = atomize([profile])
    assert {r["evidence_type"] for r in rows} == {"MARGINAL"}


def test_log_hazard_ratio_is_exponentiated_exactly_once() -> None:
    row = {"statistic": "Hazard Ratio, log", "value": math.log(0.66), "ci_lower": math.log(0.5), "ci_upper": math.log(0.86)}
    once = normalise_comparison(row)
    twice = normalise_comparison(once)
    assert once["statistic_family"] == "hazard_ratio"
    assert round(once["value"], 6) == 0.66 and twice["value"] == once["value"]


def test_frozen_asset_is_refused_if_changed(tmp_path: Path) -> None:
    source = Path("data/asset_v1")
    if not source.exists():
        pytest.skip("Asset V1 not built in this checkout")
    copy = tmp_path / "asset"
    copy.mkdir()
    lines = (source / "profiles.jsonl").read_text(encoding="utf-8").splitlines()[:3]
    (copy / "profiles.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    digest = hashlib.sha256((copy / "profiles.jsonl").read_bytes()).hexdigest()
    (copy / "manifest.json").write_text(json.dumps({"files": {"profiles.jsonl": digest}}), encoding="utf-8")
    assert len(load_frozen_profiles(copy)) == 3
    (copy / "profiles.jsonl").write_text("\n".join(lines[:2]) + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError):
        load_frozen_profiles(copy)
    shutil.rmtree(copy)


def test_models_recover_known_parameters() -> None:
    rng = np.random.default_rng(11)
    n = rng.integers(60, 400, 10)
    y = rng.binomial(n, rng.beta(0.35 * 40, 0.65 * 40, 10))
    fit = BetaBinomial().fit(y, n)
    assert fit.posterior["q025"] < 0.35 < fit.posterior["q975"]
    assert fit.diagnostics["grid_edge_mass"] < 0.01

    se = np.full(8, 0.12)
    obs = rng.normal(np.log(0.7), np.sqrt(se**2 + 0.1**2))
    fit = NormalRandomEffects(0.0, 1.0, 0.5, log_scale=True).fit(obs, se)
    assert fit.posterior["q025"] < 0.7 < fit.posterior["q975"]

    counts = np.array([rng.multinomial(500, rng.dirichlet(np.array([0.5, 0.3, 0.2]) * 30)) for _ in range(8)])
    fit = DirichletMultinomial().fit(counts)
    assert fit.diagnostics["importance_ess"] >= 200
    assert all(c["q025"] < t < c["q975"] for c, t in zip(fit.posterior["composition"], (0.5, 0.3, 0.2), strict=True))
