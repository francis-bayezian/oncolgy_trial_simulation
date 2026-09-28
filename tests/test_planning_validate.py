"""Blind planning comparison with a registry timeline (synthetic fixtures; no trial-specific content)."""

import numpy as np
from scipy import stats

from clinical_asset.planning import validate as va


def test_registry_timeline_reads_dates_months_and_the_window():
    reg = {"protocolSection": {"statusModule": {"overallStatus": "TERMINATED", "whyStopped": "slow",
                                                "startDateStruct": {"date": "2017-07", "type": "ACTUAL"},
                                                "primaryCompletionDateStruct": {"date": "2018-07-15", "type": "ACTUAL"}},
                               "designModule": {"enrollmentInfo": {"count": 3, "type": "ACTUAL"}}}}
    t = va.registry_timeline(reg)
    assert t["enrolled"] == 3 and abs(t["window_years"] - 365 / 365.25) < 1e-9


def test_score_matches_the_poisson_mixture_and_the_log_normal_percentile():
    q = {"median": 10.0, "q10": 10.0 * np.exp(-0.5 * va.Z90), "q90": 10.0 * np.exp(0.5 * va.Z90)}   # sigma 0.5
    s = va.score(q, target=20, enrolled=5, window_years=1.0)
    assert abs(s["reconstruction"]["sigma"] - 0.5) < 1e-9
    assert abs(s["observed_rate_percentile_in_prediction"] - stats.norm.cdf(np.log(0.5) / 0.5)) < 1e-9 and not s["inside_80_interval"]
    lam = np.exp(np.random.default_rng(1).normal(np.log(10), 0.5, 200_000))
    assert abs(s["p_at_most_actual_enrollment_in_window"] - stats.poisson.cdf(5, lam).mean()) < 0.01
    assert abs(s["p_target_reached_in_window"] - stats.poisson.sf(19, lam).mean()) < 0.01


def test_a_point_rate_scores_without_spread_and_the_headline_follows_the_outcome():
    s = va.score({"median": 12.0, "q10": 12.0, "q90": 12.0}, target=10, enrolled=10, window_years=1.0)
    assert s["target_reached"] and abs(s["headline"]["predicted_probability"] - stats.poisson.sf(9, 12.0)) < 1e-9
    short = va.score({"median": 12.0, "q10": 12.0, "q90": 12.0}, target=10, enrolled=4, window_years=1.0)
    assert not short["target_reached"] and abs(short["headline"]["predicted_probability"] - stats.poisson.cdf(4, 12.0)) < 1e-9
