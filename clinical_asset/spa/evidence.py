"""Layer B: the long-format statistical evidence table built from frozen Asset V1 profiles.

One row per statistical observation. Every row inherits its profile's clinical context and
carries an evidence type: MARGINAL, SUBGROUP, COMPARATIVE or LONGITUDINAL. JOINT evidence is
only assigned when a source reports characteristics jointly; Asset V1 contains none.
"""

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .. import assets as _assets
from .canonical import (
    canonical_outcome,
    disposition_category,
    entry_for,
    parse_times,
    response_category,
    safety_like,
    statistic_family,
)

ASSET = _assets.path("asset")
MORTALITY = re.compile(r"mortality|\bdeaths?\b|\bdied\b|deceased", re.IGNORECASE)


def load_frozen_profiles(asset_dir: Path = ASSET) -> list[dict]:
    """Read profiles.jsonl only if its checksum matches the frozen manifest."""
    manifest = json.loads((asset_dir / "manifest.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256((asset_dir / "profiles.jsonl").read_bytes()).hexdigest()
    if digest != manifest["files"]["profiles.jsonl"]:
        raise RuntimeError("profiles.jsonl does not match the frozen Asset V1 manifest.")
    with open(asset_dir / "profiles.jsonl", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def _context(profile: dict) -> dict[str, Any]:
    cancer, treatment, ontology = profile.get("cancer", {}), profile.get("treatment", {}), profile.get("treatment_ontology", {})
    markers = cancer.get("biomarkers") or []
    subgroup = profile.get("patient_profile", {}).get("subgroup")
    return {
        "profile_id": profile["profile_id"],
        "nct_id": profile["source"]["nct"],
        "profile_type": profile["profile_type"],
        "registry_group": profile["source"].get("registry_group"),
        "disease": cancer.get("disease", {}).get("name"),
        "disease_cui": cancer.get("disease", {}).get("umls_cui"),
        "setting": cancer.get("setting"),
        "biomarker": f"{markers[0]['gene']} {markers[0]['variant']}" if markers else None,
        "biomarker_cui": markers[0]["umls_cui"] if markers else None,
        "regimen": treatment.get("regimen"),
        "drug": treatment.get("drug"),
        "drug_cui": ontology.get("umls_cui"),
        "drug_class": ontology.get("drug_class"),
        "arm_type": treatment.get("arm_type"),
        "subgroup_definition": subgroup.get("definition") if subgroup else profile.get("definition"),
    }


def _row(context: dict, **fields: Any) -> dict:
    return {**context, **fields}


def _efficacy_rows(profile: dict, context: dict, domain_hint: str, model_map: dict) -> list[dict]:
    rows = []
    source = profile.get("efficacy", {}) if domain_hint == "efficacy" else profile.get("toxicity", {}).get("registry_safety_outcomes", {})
    for key, observations in source.items():
        for obs in observations:
            measure = obs.get("measure") or key
            entry = canonical_outcome(measure) if domain_hint == "efficacy" else None
            method = "rule" if entry else None
            if entry is None and domain_hint == "efficacy":
                mapped = model_map.get(measure)
                if mapped and mapped["confidence"] >= 0.8 and mapped["canonical_variable"] not in {"other", "not_an_outcome"}:
                    entry, method = entry_for(mapped["canonical_variable"]), "model"
            if entry and str(entry.get("variable", "")).endswith("_survival") and MORTALITY.search(measure):
                # A count or rate of deaths is mortality, never a survival probability (direction).
                entry = {"variable": "all_cause_death", "domain": "mortality", "value_type": "binary"}
            if key == "follow_up":
                entry, method = {"variable": "follow_up", "domain": "follow_up", "value_type": "time_to_event"}, "rule"
            times = parse_times(measure, obs.get("class"), obs.get("category"), obs.get("time_frame"))
            family = statistic_family(entry, obs)
            landmark = times[-1] if times and (family == "survival_probability" or (entry and entry.get("value_type") == "binary")) else None
            numerator = obs["value"] if obs.get("statistic") == "count" and isinstance(obs.get("value"), int) else obs.get("n")
            if numerator is None and obs.get("rate") is not None and obs.get("N"):
                numerator = round(obs["rate"] * obs["N"])
            if entry is None and domain_hint == "efficacy" and safety_like(measure):
                domain_hint_row = "safety_other"
            else:
                domain_hint_row = domain_hint if domain_hint != "efficacy" else "efficacy_other"
            rows.append(_row(
                context,
                domain=(entry or {}).get("domain", domain_hint_row),
                variable=(entry or {}).get("variable", key),
                canonical=entry is not None,
                mapping_method=method or "raw_key",
                raw_key=key, raw_measure=measure,
                statistic=obs.get("statistic"), statistic_family=family,
                value=obs.get("value") if isinstance(obs.get("value"), (int, float)) else None,
                unit=obs.get("unit"), rate=obs.get("rate"), numerator=numerator, denominator=obs.get("N"),
                sd=obs.get("sd"), se=obs.get("se"),
                ci_lower=(obs.get("ci") or [None, None])[0], ci_upper=(obs.get("ci") or [None, None])[1],
                ci_level=obs.get("ci_level"),
                category=obs.get("category"), response_category=response_category(obs.get("category")),
                obs_class=obs.get("class"),
                time=landmark[0] if landmark else None, time_unit=landmark[1] if landmark else None,
                population=obs.get("population"), population_scope=obs.get("population_scope"),
                event_class=None, comparator=None, comparator_group=None,
                sources=json.dumps(obs.get("sources") or ([obs["source"]] if obs.get("source") else ["registry"])),
            ))
    return rows


def _toxicity_rows(profile: dict, context: dict) -> list[dict]:
    rows = []
    tox = profile.get("toxicity", {})
    group_n = tox.get("N")
    base = {"domain": "safety", "canonical": True, "mapping_method": "umls_or_grammar", "statistic": "count", "statistic_family": "proportion",
                "unit": "participants", "sd": None, "se": None, "ci_lower": None, "ci_upper": None, "ci_level": None, "category": None,
                "response_category": None, "obs_class": None, "time": None, "time_unit": None, "comparator": None, "comparator_group": None,
                "population": tox.get("population"), "population_scope": None}
    if serious := tox.get("any_serious_AE"):
        rows.append(_row(context, **base, variable="serious_adverse_event", raw_key="any_serious_AE", raw_measure="any serious adverse event",
                         value=serious["n"], rate=serious["rate"], numerator=serious["n"], denominator=group_n,
                         event_class="serious_any_cause", sources=json.dumps(["registry"])))
    for section, event_class in (("key_events", "non_serious_any_grade"), ("key_serious_events", "serious_any_cause")):
        for key, event in tox.get(section, {}).items():
            rows.append(_row(context, **base, variable=key, raw_key=key, raw_measure=key, value=event["n"], rate=event["rate"],
                             numerator=event["n"], denominator=event.get("N") or group_n, event_class=event_class,
                             sources=json.dumps(["registry"]), reporting_filtered=True))
    for key, block in tox.items():
        if key.endswith("_AE") and isinstance(block, dict) and "n" in block:
            rows.append(_row(context, **{**base, "population": "treated_safety_population"}, variable=key.casefold(), raw_key=key,
                             raw_measure=key, value=block["n"], rate=block["rate"], numerator=block["n"], denominator=block.get("N"),
                             event_class=key.casefold(), sources=json.dumps([block.get("source", "registry")])))
        if key.startswith("key_grade_3") and isinstance(block, dict):
            for event_key, event in block.get("events", {}).items():
                rows.append(_row(context, **base, variable=event_key, raw_key=event_key, raw_measure=event_key, value=event["n"],
                                 rate=event["rate"], numerator=event["n"], denominator=block.get("N"),
                                 event_class="grade_3_plus_treatment_related", sources=json.dumps([block.get("source")]),
                                 reporting_filtered=True))
    return rows


def _baseline_rows(profile: dict, context: dict) -> list[dict]:
    rows = []
    patient = profile.get("patient_profile", {})
    base = {"domain": "baseline", "canonical": True, "mapping_method": "registry_structure", "unit": None, "rate": None, "se": None,
                "ci_lower": None, "ci_upper": None, "ci_level": None, "response_category": None, "obs_class": None, "time": None, "time_unit": None,
                "event_class": None, "comparator": None, "comparator_group": None, "population": patient.get("population"),
                "population_scope": None, "sources": json.dumps(["registry"])}
    if age := patient.get("age"):
        rows.append(_row(context, **{**base, "unit": "year"}, variable="age", raw_key="age", raw_measure="age",
                         statistic="mean", statistic_family="continuous_mean", value=age["mean"], sd=age.get("sd"),
                         numerator=None, denominator=patient.get("n"), category=None))
    for variable in ("sex", "race", "ethnicity"):
        values = patient.get(variable)
        if isinstance(values, dict) and all(isinstance(v, int) for v in values.values()):
            for category, count in values.items():
                rows.append(_row(context, **base, variable=variable, raw_key=variable, raw_measure=variable, statistic="count",
                                 statistic_family="categorical", value=count, sd=None, numerator=count,
                                 denominator=patient.get("n"), category=category))
    return rows


def _course_rows(profile: dict, context: dict) -> list[dict]:
    rows = []
    course = profile.get("treatment_course", {})
    n = profile.get("patient_profile", {}).get("n")
    base = {"domain": "study_disposition", "canonical": True, "mapping_method": "rule", "unit": "participants", "rate": None, "sd": None, "se": None,
                "ci_lower": None, "ci_upper": None, "ci_level": None, "response_category": None, "obs_class": None, "time": None, "time_unit": None,
                "event_class": None, "comparator": None, "comparator_group": None, "population": None, "population_scope": None,
                "sources": json.dumps(["registry"])}
    for reason, count in course.get("study_status_at_data_cutoff", {}).items():
        # Study disposition at data cut-off: not the same thing as treatment discontinuation.
        rows.append(_row(context, **base, variable="study_disposition", raw_key=reason, raw_measure=reason, statistic="count",
                         statistic_family="categorical", value=count, numerator=count, denominator=n,
                         category=disposition_category(reason)))
    if switched := course.get("switched_to_other_arm"):
        rows.append(_row(context, **{**base, "domain": "treatment_course"}, variable="switched_to_other_arm", raw_key="switched_to_other_arm",
                         raw_measure="switched to other arm", statistic="count", statistic_family="proportion", value=switched,
                         numerator=switched, denominator=n, category=None))
    if deaths := profile.get("mortality_observations"):
        rows.append(_row(context, **{**base, "domain": "mortality", "population": deaths.get("population")}, variable="all_cause_death",
                         raw_key="all_cause_deaths", raw_measure="all-cause deaths", statistic="count", statistic_family="proportion",
                         value=deaths["all_cause_deaths"], numerator=deaths["all_cause_deaths"], denominator=deaths["at_risk"],
                         category=None))
    return rows


def _comparison_rows(profile: dict, context: dict) -> list[dict]:
    rows = []
    for c in profile.get("comparisons", []):
        measure = str(c.get("measure") or "")
        entry = canonical_outcome(str(c.get("outcome") or "").replace("_", " "))
        interval = c.get("ci95") or c.get("ci") or [None, None]
        level = 95.0 if c.get("ci95") else c.get("ci_percent")
        family = measure if measure in {"hazard_ratio", "odds_ratio", "risk_ratio"} else f"difference_{measure}" if measure else "descriptive"
        rows.append(_row(
            context, domain="comparative", variable=(entry or {}).get("variable", c.get("outcome")), canonical=entry is not None,
            mapping_method="rule" if entry else "raw_key", raw_key=c.get("outcome"), raw_measure=c.get("outcome"),
            statistic=measure, statistic_family=family, value=c.get("value"), unit=None, rate=None, numerator=None,
            denominator=None, sd=None, se=None, ci_lower=interval[0], ci_upper=interval[1], ci_level=level,
            category=None, response_category=None, obs_class=None, time=None, time_unit=None,
            population=c.get("population"), population_scope=None, event_class=None,
            comparator=c.get("comparator"), comparator_group=c.get("comparator_group"),
            sources=json.dumps(c.get("sources") or ([c["source"]] if c.get("source") else ["registry"])),
        ))
    return rows


def _observation_id(row: dict) -> str:
    fields = [row.get(k) for k in ("nct_id", "regimen", "registry_group", "domain", "variable", "statistic_family", "event_class",
                                    "category", "obs_class", "time", "value", "denominator", "population", "comparator_group",
                                    "subgroup_definition")]
    return hashlib.sha1(json.dumps(fields, default=str).encode()).hexdigest()[:16]


def atomize(profiles: list[dict], model_map: dict | None = None) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    for profile in profiles:
        context = _context(profile)
        rows += _baseline_rows(profile, context)
        rows += _efficacy_rows(profile, context, "efficacy", model_map or {})
        rows += _efficacy_rows(profile, context, "safety", {})
        rows += _toxicity_rows(profile, context)
        rows += _course_rows(profile, context)
        rows += _comparison_rows(profile, context)
    # Evidence type
    times: dict[tuple, set] = defaultdict(set)
    for row in rows:
        if row.get("time") is not None:
            times[(row["profile_id"], row["variable"], row["statistic_family"])].add((row["time"], row["time_unit"]))
    for row in rows:
        row.setdefault("reporting_filtered", False)
        if row["domain"] == "comparative":
            row["evidence_type"] = "COMPARATIVE"
        elif row["profile_type"] == "reported_subgroup":
            row["evidence_type"] = "SUBGROUP"
        elif len(times.get((row["profile_id"], row["variable"], row["statistic_family"]), ())) > 1:
            row["evidence_type"] = "LONGITUDINAL"
        else:
            row["evidence_type"] = "MARGINAL"
        row["scientific_observation_id"] = _observation_id(row)
    # Deduplicate: one scientific observation enters once, whatever its sources.
    unique, seen = [], set()
    for row in rows:
        if row["scientific_observation_id"] in seen:
            continue
        seen.add(row["scientific_observation_id"])
        unique.append(row)
    return unique, {"rows_before_dedup": len(rows), "rows": len(unique), "duplicates_removed": len(rows) - len(unique)}
