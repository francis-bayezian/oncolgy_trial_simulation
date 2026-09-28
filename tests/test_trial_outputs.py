"""Trial outputs from simulated patients (synthetic fixtures; no trial-specific content)."""

import numpy as np
from scipy import stats

from clinical_asset import safety3 as s3
from clinical_asset.trial import outputs as out


def test_copula_matches_the_any_event_target_and_keeps_marginals():
    p = np.array([0.3, 0.2, 0.1, 0.05])
    assert abs(out.p_any(p, 0.0) - (1 - np.prod(1 - p))) < 1e-12
    rho, how = out.copula_rho(p, 0.40)
    assert how == "matched" and abs(out.p_any(p, rho) - 0.40) < 1e-3
    rng = np.random.default_rng(0)
    z = rng.standard_normal(200000)
    latent = np.sqrt(rho) * z[:, None] + np.sqrt(1 - rho) * rng.standard_normal((200000, 4))
    hit = latent < stats.norm.ppf(p)[None, :]
    assert np.allclose(hit.mean(axis=0), p, atol=0.005) and abs(hit.any(axis=1).mean() - 0.40) < 0.005
    assert out.copula_rho(p, 0.25)[1].startswith("the single most frequent")          # max(p) = 0.3 > 0.25: inconsistent


def test_events_without_support_in_the_arm_context_are_not_predicted():
    asset = {"support": {"fatigue|non_serious": {"family": {"lung": 5}, "signature": {"platinum": 1}},
                         "rash|non_serious": {"family": {"breast": 4}, "signature": {"taxane": 3}}}}
    arm = {"disease_family": "lung", "classes": ["platinum"]}
    assert s3.supported(asset, "fatigue", "non_serious", arm)
    assert not s3.supported(asset, "rash", "non_serious", arm) and not s3.supported(asset, "nausea", "non_serious", arm)
    assert s3.supported({"support": None}, "rash", "non_serious", arm)                    # an asset without the table: no filter


def test_random_effects_pooling_is_exact_without_heterogeneity_and_widens_with_it():
    from clinical_asset.trial import subgroups as sg

    same = [{"study": f"s{i}", "count": 20, "n": 100} for i in range(5)]
    p = sg.pooled(same)
    assert abs(p["estimate"] - (20.5 / 100.5) / (1 - 20.5 / 100.5 + 20.5 / 100.5) ) < 0.01 and p["between_study_tau_logit"] == 0.0
    spread = [{"study": f"s{i}", "count": c, "n": 100} for i, c in enumerate((5, 15, 30, 45, 60))]
    q = sg.pooled(spread)
    assert q["between_study_tau_logit"] > 0.5 and q["ci95"][1] - q["ci95"][0] > p["ci95"][1] - p["ci95"][0]


def test_arms_of_unstated_status_enroll_when_none_is_stated_open():
    from clinical_asset.trial.recruitment import randomization_plan

    spec = {"arms": [{"arm_id": "A", "label": "a", "status": "unclear"}, {"arm_id": "B", "label": "b", "status": "closed"}],
            "randomization": {}, "stratification": {"strata": []}}
    plan = randomization_plan(spec)
    assert [a["arm_id"] for a in plan["arms"]] == ["A"] and "assumed to enroll" in plan["arm_status_note"]
