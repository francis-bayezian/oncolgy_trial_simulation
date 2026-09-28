"""Safety results and their registry comparison (synthetic fixtures; no trial-specific content)."""

import numpy as np
from scipy import stats

from clinical_asset.trial import safety as sa


def test_rate_distribution_matches_the_asset_interval_and_point_rates():
    d = sa.rate_distribution({"rate": 0.2, "q025": 0.1, "q975": 0.35})
    p = sa.draw_rates(d, np.random.default_rng(0), 200_000)
    assert abs(np.median(p) - 0.2) < 0.005 and abs(np.quantile(p, 0.025) - 0.1) < 0.01 and abs(np.quantile(p, 0.975) - 0.35) < 0.015
    point = sa.count_distribution(sa.rate_distribution({"rate": 0.3}), 10)
    assert np.allclose(point["pmf"], stats.binom.pmf(np.arange(11), 10, 0.3), atol=1e-9)


def _registry(events, groups):
    return {"protocolSection": {"identificationModule": {"nctId": "NCT0"}},
            "resultsSection": {"adverseEventsModule": {"eventGroups": groups, "otherEvents": events, "seriousEvents": []}}}


def test_comparison_uses_the_registry_number_at_risk_and_flags_unlisted_terms():
    results = {"arms": [{"arm_id": "ARM1", "events": [
        {"term": "Fatigue", "seriousness": "non-serious", "source": "asset:x", "logit_mu": sa._logit(0.5), "logit_sigma": 0.0, "rate_median": 0.5},
        {"term": "Nausea", "seriousness": "non-serious", "source": "asset:x", "logit_mu": sa._logit(0.3), "logit_sigma": 0.0, "rate_median": 0.3}]}]}
    reg = _registry([{"term": "fatigue", "stats": [{"numAffected": 2, "numAtRisk": 4}]},
                     {"term": "Rash", "stats": [{"numAffected": 1, "numAtRisk": 4}]}], [{"otherNumAtRisk": 4}])
    c = sa.compare_safety(results, reg)
    fat, nau = c["rows"]
    assert fat["at_risk"] == 4 and fat["observed"] == 2 and fat["observed_listed"] and fat["inside_90"]
    assert nau["observed"] == 0 and not nau["observed_listed"] and c["unlisted_predicted_terms"] == 1
    assert [v["term"] for v in c["unpredicted_registry_terms"]] == ["Rash"] and c["registry_at_risk"] == 4


def test_any_event_bound_and_a_zero_threshold_make_unlisted_terms_zero():
    results = {"arms": [{"arm_id": "ARM1", "events": [
        {"term": "Fatigue", "seriousness": "non_serious", "source": "asset:x", "logit_mu": sa._logit(0.5), "logit_sigma": 0.0, "rate_median": 0.5},
        {"term": "Nausea", "seriousness": "non_serious", "source": "asset:x", "logit_mu": sa._logit(0.3), "logit_sigma": 0.0, "rate_median": 0.3}]}]}
    reg = _registry([], [{"otherNumAffected": 0, "otherNumAtRisk": 3, "seriousNumAffected": 0, "seriousNumAtRisk": 3}])
    reg["resultsSection"]["adverseEventsModule"]["frequencyThreshold"] = "0"
    c = sa.compare_safety(results, reg)
    assert c["unlisted_terms_are_zero"] and all(r["unlisted_meaning"].startswith("reported absent") for r in c["rows"])
    g = c["aggregate"]["other"]
    assert g["bounding_event"] == "Fatigue" and abs(g["p_at_most_observed_upper_bound"] - 0.125) < 1e-9     # 0.5 ** 3
    assert c["aggregate"]["serious"]["status"] == "UNRESOLVED"


def test_arms_are_pooled_by_enrolment_before_comparing_with_pooled_registry_tables():
    ev = lambda r: {"term": "Nausea", "seriousness": "non_serious", "source": "s", "rate_median": r, "logit_mu": sa._logit(r), "logit_sigma": 0.2}
    pooled = sa.pooled_arms([{"arm_id": "A", "enrolled": 30, "events": [ev(0.1)]}, {"arm_id": "B", "enrolled": 10, "events": [ev(0.5)]}])
    assert len(pooled) == 1 and abs(pooled[0]["events"][0]["rate_median"] - 0.2) < 1e-12 and pooled[0]["enrolled"] == 40
