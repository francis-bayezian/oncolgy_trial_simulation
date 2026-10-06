"""Subgroup reporting: factors resolved by meaning, protocol age cut points, honest drivers (synthetic fixtures only)."""

from clinical_asset.trial import subgroup_report as sr


def _spec():
    return {"arms": [{"arm_id": "A", "label": {"text": "Drug X"}}, {"arm_id": "B", "label": {"text": "Control"}}],
            "eligibility": [{"criterion_id": "EL1", "label": {"text": "ECOG 0-1"},
                             "logic": {"node": "LEAF", "variable": "var:ecog_performance_status", "subject": "ECOG"}},
                            {"criterion_id": "EL2", "label": {"text": "Residual disease"},
                             "logic": {"node": "LEAF", "variable": "umls:C000", "subject": "residual tumour"}}],
            "stratification": {"factors": [], "strata": []},
            "subgroups": [{"subgroup": {"text": "age (< 65, >= 65)"}}, {"subgroup": {"text": "number of prior therapies"}}]}


def _base(age, sex, ecog, resid):
    return {"demographic:age": {"value": age}, "demographic:sex": sex, "demographic:race": "white",
            "demographic:ethnicity": "not_hispanic_or_latino", "var:ecog_performance_status": {"value": ecog},
            "umls:C000": {"interval": [1.5, None], "lower_inclusive": True, "unit": "cm2"} if resid else
                         {"interval": [None, 1.5], "upper_inclusive": False, "unit": "cm2"},
            "var:weight": {"value": 70.3 + age / 7}}


def test_factors_use_protocol_cut_points_and_readable_names():
    bases = [_base(40 + i, "male" if i % 2 else "female", i % 3, i % 2) for i in range(40)]
    fs = {f["factor"]: f for f in sr.factors(_spec(), bases, {})}
    age = fs["Age (protocol cut points)"]
    assert age["source"].startswith("protocol subgroup")
    assert {age["level"](b, {}) for b in bases} == {"< 65 years", ">= 65 years"}
    assert "Residual tumour" in fs                                   # coded variable reported by the protocol's name
    assert not any("eight" in k for k in fs)                         # continuous anthropometrics are not subgroups
    assert fs["ECOG"]["feasibility_driver"] == "protocol criteria"           # named as the protocol's rule names it
    assert fs["ECOG"]["level"](_base(50, "male", 3, 0), {}) == "2 or more"
    assert fs["number of prior therapies"]["level"] is None          # no patient variable: reported as not generated


def test_report_labels_mix_only_and_compares_within_levels():
    bases = [_base(50 + i, "male" if i % 2 else "female", i % 2, 1) for i in range(24)]
    cohort = [{"subject_id": f"S{i:03d}", "patient_id": f"P{i:03d}", "baseline": b} for i, b in enumerate(bases)]
    adsl = [{"USUBJID": f"S{i:03d}", "ARMCD": "A" if i % 3 else "B", "EOTREAS": "disease progression", "DTHFL": "N"} for i in range(24)]
    adrs = [{"USUBJID": r["USUBJID"], "PARAMCD": "BOR", "AVALC": "PR" if i % 4 == 0 else "SD"} for i, r in enumerate(adsl)]
    adtte = [{"USUBJID": r["USUBJID"], "ARMCD": r["ARMCD"], "PARAMCD": "PFS", "AVAL": 30.0 + 7 * i, "CNSR": i % 5 == 0, "EVNTDESC": "x"}
             for i, r in enumerate(adsl)]
    for x in adtte:
        x["CNSR"] = int(x["CNSR"])
    doc = sr.report(_spec(), adsl, [], adrs, adtte, ["A", "B"], "B", cohort, [], [])
    sex = next(f for f in doc["factors"] if f["factor"] == "Sex")
    assert sex["outcome_driver"].startswith("mix only")
    rows = [r for r in doc["rows"] if r["factor"] == "Sex"]
    assert {r["level"] for r in rows} == {"male", "female"} and sum(r["n"] for r in rows) == 24
    comp = [c for c in doc["comparisons"] if c["factor"] == "Sex"]
    assert comp and all("orr_difference" in c for c in comp)
    doc2 = sr.report(_spec(), adsl, [], adrs, adtte, ["A", "B"], "B", cohort, [], [],
                     {"demographic:sex": {"source": "registry subgroup results"}})
    assert next(f for f in doc2["factors"] if f["factor"] == "Sex")["outcome_driver"].startswith("evidence-driven")


def test_forest_plot_is_svg_with_null_line():
    pts = [{"factor": "Sex", "level": "male", "n": 10, "n_control": 9, "PFS_hazard_ratio": {"hr": 0.7, "ci95": [0.4, 1.2]}}]
    s = sr.forest(pts, "PFS_hazard_ratio", "PFS HR", True)
    assert s.startswith("<svg") and "stroke-dasharray" in s and "0.70" in s
