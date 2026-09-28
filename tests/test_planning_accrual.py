"""Planning asset 1: accrual evidence (synthetic fixtures; no trial-specific content)."""

import datetime as dt
import math

import numpy as np

from clinical_asset.planning import accrual as ac


def test_dates_in_the_formats_registries_use():
    assert ac.parse_date("August 10, 2016") == (dt.date(2016, 8, 10), "day")
    assert ac.parse_date("14Dec 2004") == (dt.date(2004, 12, 14), "day")
    assert ac.parse_date("8/25/2005") == (dt.date(2005, 8, 25), "day")
    assert ac.parse_date("Sep 2004") == (dt.date(2004, 9, 15), "month")
    assert ac.parse_date("05-July-2019") == (dt.date(2019, 7, 5), "day")
    assert ac.parse_date("2016-10-12") == (dt.date(2016, 10, 12), "day")
    assert ac.parse_date("no date here") is None


def _trial(**kw):
    base = {"nct_id": "NCT0", "enrolled": 180, "start": dt.date(2016, 10, 12), "primary_completion": dt.date(2018, 10, 18),
            "completion": dt.date(2022, 6, 7), "phase": "PHASE2", "randomized": True, "arms": 2, "pediatric": False, "listed_sites": 25,
            "countries": 1, "sponsor_class": "NETWORK", "disease_family": "lung", "start_year": 2016,
            "recruitment_details": "From August 10, 2016 to June 29, 2017 in 27 cancer centres in Canada"}
    return {**base, **kw}


def test_a_verified_window_gives_a_direct_rate_and_otherwise_only_a_lower_bound():
    t = _trial()
    w = {"start_quote": "August 10, 2016", "end_quote": "June 29, 2017", "site_count_quote": "27 cancer centres"}
    checked = ac.check_window(w, t)
    assert checked["issues"] == [] and checked["site_count"] == 27
    direct = ac.classify(t, {**w, **checked, "status": "USABLE"})
    assert direct["quality"] == "ACCRUAL_DIRECT" and abs(math.exp(direct["log_rate"]) - 180 / (323 / ac.MONTH)) < 1e-9
    censored = ac.classify(t, None)
    assert censored["quality"] == "ACCRUAL_INTERVAL_CENSORED" and censored["log_rate_lower"] < direct["log_rate"]
    assert ac.classify({**t, "enrolled": None}, None)["quality"] == "ACCRUAL_UNUSABLE"


def test_window_checks_reject_misread_or_misplaced_dates():
    t = _trial()
    assert "a date could not be parsed" in ac.check_window({"start_quote": "August 10, 2016", "end_quote": "later", "site_count_quote": ""}, t)["issues"]
    late = ac.check_window({"start_quote": "August 10, 2016", "end_quote": "June 29, 2017", "site_count_quote": ""},
                           {**t, "completion": dt.date(2017, 1, 1), "primary_completion": dt.date(2017, 1, 1)})
    assert any("after the study completion" in i for i in late["issues"])
    invented = ac.check_window({"start_quote": "March 3, 2016", "end_quote": "June 29, 2017", "site_count_quote": ""}, t)
    assert any("not in the text" in i for i in invented["issues"])


def test_censored_regression_recovers_the_truth_that_naive_rates_would_miss():
    rng = np.random.default_rng(0)
    rows = []
    for i in range(400):
        sites = int(rng.integers(1, 60))
        true = 0.5 + 0.6 * math.log(sites) + rng.normal(0, 0.4)
        r = {**_trial(nct_id=f"T{i}", listed_sites=sites, enrolled=100, randomized=bool(i % 2), start_year=2010,
                      disease_family=["a", "b", "c"][i % 3]), "site_count": None}
        if i % 4 == 0:
            r.update(quality="ACCRUAL_DIRECT", log_rate=true)
        else:                                     # only a lower bound: accrual took at most 1.5x as long
            r.update(quality="ACCRUAL_INTERVAL_CENSORED", log_rate_lower=true - math.log(1 + 0.5 * rng.random()))
        rows.append(r)
    model = ac.fit(rows, tau=0.25)
    b = dict(zip(model["cols"], model["beta"], strict=True))
    assert abs(b["log_sites"] - 0.6) < 0.1 and abs(model["sigma"] - 0.4) < 0.08
    pred = ac.predict(model, {**rows[0], "listed_sites": 20}, draws=4000)["log_rate"]
    assert abs(np.median(pred) - (0.5 + 0.6 * math.log(20))) < 0.15
    cv = ac.cross_validate(rows, 0.25, folds=5)
    assert 0.7 < cv["coverage"]["0.8"] < 0.9
