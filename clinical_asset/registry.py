"""Conservative deterministic extraction from posted registry results."""

import re
import unicodedata
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from typing import Any

from .ctgov import eligibility, linked_result_references
from .source_text import (
    NEGATED_METASTATIC,
    eligibility_phenotype,
    grouping_basis,
    outcome_assessment,
    population_label,
    regimen,
)
from .types import AuditItem, ClinicalProfile, ParsedStudy

NUMBER = re.compile(r"^-?(?:\d+(?:\.\d*)?|\.\d+)$")
CLINICAL_SUBGROUP = re.compile(
    r"\b(?:subgroup|subset)\b.*\b(?:biomarker|mutation|metastas(?:is|es)|"
    r"female|male|age|ecog|stage)\b|\b(?:biomarker|mutation|metastas(?:is|es)|"
    r"female|male|age|ecog|stage)\b.*\b(?:subgroup|subset)\b|"
    r"\b(?:female|male) (?:participants|patients)\b|"
    r"\b(?:with|without) liver metastases\b",
    re.IGNORECASE,
)
OVERALL_ANALYSIS = re.compile(
    r"\b(?:all randomi[sz]ed (?:participants|patients|subjects)|full analysis|"
    r"intent(?:ion)?[- ]to[- ]treat|m?ITT\b|all (?:enrolled|treated) (?:participants|patients|subjects)|"
    r"all (?:participants|patients|subjects)\b|safety (?:population|analysis set|set)|per[- ]protocol)",
    re.IGNORECASE,
)
ARM_PREFIX = re.compile(r"^\s*(?:arm|group|cohort|part)?\s*[A-Z0-9]{1,3}\s*[:.)\-]\s+", re.IGNORECASE)
SEQUENCE_GROUP = re.compile(
    r"^(?P<first>.+?),?\s+then\s+(?:switched|crossed over)\s+to\s+(?P<second>.+)$",
    re.IGNORECASE,
)


def numeric(value: Any) -> int | float | None:
    """Return only an exactly represented scalar reported by the source."""
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().replace(",", "")
    if not NUMBER.fullmatch(text):
        return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    return int(number) if number == number.to_integral_value() else float(number)


def _group_lookup(groups: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(group["id"]): group for group in groups if group.get("id")}


def _denominators(denoms: Iterable[dict[str, Any]]) -> dict[str, int]:
    values: dict[str, int] = {}
    for denom in denoms:
        if str(denom.get("units", "")).lower() not in {"participants", "subjects", "patients"}:
            continue
        for count in denom.get("counts", []):
            number = numeric(count.get("value"))
            if isinstance(number, int) and number >= 0:
                values[str(count.get("groupId"))] = number
    return values


def _measurements(measure: dict[str, Any]) -> Iterable[tuple[int, int, int, dict[str, Any]]]:
    for class_index, group_class in enumerate(measure.get("classes", [])):
        for category_index, category in enumerate(group_class.get("categories", [])):
            for measurement_index, item in enumerate(category.get("measurements", [])):
                yield (
                    class_index,
                    category_index,
                    measurement_index,
                    {
                        "class_title": group_class.get("title"),
                        "category_title": category.get("title"),
                        "measurement": item,
                    },
                )


def _payload(
    measure: dict[str, Any],
    item: dict[str, Any],
    denominator: int | None,
) -> dict[str, Any] | None:
    reported = item["measurement"]
    value = numeric(reported.get("value"))
    if value is None:
        return None
    if measure.get("paramType") == "COUNT_OF_PARTICIPANTS" and (
        not isinstance(value, int) or value < 0 or (denominator is not None and value > denominator)
    ):
        return None
    result: dict[str, Any] = {
        "measure": measure.get("title", ""),
        "value": value,
    }
    for source, target in (
        ("paramType", "statistic"),
        ("unitOfMeasure", "unit"),
        ("timeFrame", "time_frame"),
    ):
        if measure.get(source):
            result[target] = measure[source]
    for source, target in (
        ("class_title", "class"),
        ("category_title", "category"),
    ):
        if item.get(source):
            result[target] = item[source]
    for source, target in (
        ("spread", "spread"),
        ("lowerLimit", "lower_limit"),
        ("upperLimit", "upper_limit"),
    ):
        if reported.get(source) is not None:
            parsed = numeric(reported[source])
            if parsed is not None:
                result[target] = parsed
            else:
                result[f"{target}_reported"] = str(reported[source])
    if measure.get("dispersionType"):
        result["dispersion"] = measure["dispersionType"]
    if denominator is not None:
        result["denominator"] = denominator
    return result


def _outcome_section(outcome: dict[str, Any]) -> str | None:
    """Classify by the reported statistic and unit, not by endpoint names.

    A time-valued summary (months, weeks, days, years) is a time-to-event result; a
    count or percentage of participants is a response-type rate.
    """
    unit = str(outcome.get("unitOfMeasure") or "").casefold()
    if re.search(r"\b(?:months?|weeks?|days?|years?)\b", unit):
        return "survival"
    if re.search(r"participants?|patients?|subjects?|percent|%|proportion", unit):
        return "response"
    return None


def parse_study(study: dict[str, Any]) -> ParsedStudy:
    protocol = study.get("protocolSection", {})
    identity = protocol.get("identificationModule", {})
    nct_id = str(identity.get("nctId") or "")
    parsed = ParsedStudy(
        nct_id=nct_id,
        study_title=str(identity.get("briefTitle") or identity.get("officialTitle") or ""),
        study_url=f"https://clinicaltrials.gov/study/{nct_id}",
        eligible=False,
        exclusion_reason=None,
    )
    parsed.eligible, parsed.exclusion_reason = eligibility(study)
    parsed.allocation = protocol.get("designModule", {}).get("designInfo", {}).get("allocation")
    if not parsed.eligible:
        parsed.audit.append(AuditItem("excluded", "$", {"reason": parsed.exclusion_reason}))
        return parsed

    parsed.result_references = linked_result_references(study)
    conditions = protocol.get("conditionsModule", {}).get("conditions", [])
    disease = conditions[0] if len(conditions) == 1 else None
    reported_condition = str(disease or "")
    # Disease, histology and biomarkers are resolved later through UMLS (see enrich.py).
    histology = None
    eligibility_limits = eligibility_phenotype(protocol.get("eligibilityModule", {}))
    setting = eligibility_limits.get("disease_extent") or (
        "metastatic"
        if re.search(r"\bmetastatic\b", reported_condition, re.IGNORECASE)
        and not NEGATED_METASTATIC.search(reported_condition)
        else None
    )
    primary_biomarker = None
    arm_groups = protocol.get("armsInterventionsModule", {}).get("armGroups", [])
    arm_by_title = {str(arm.get("label", "")).casefold(): arm for arm in arm_groups}
    interventions = protocol.get("armsInterventionsModule", {}).get("interventions", [])
    profiles: dict[tuple[str, str], ClinicalProfile] = {}
    reported_denominators: dict[tuple[str, str], set[int]] = {}

    def _norm(value: str) -> str:
        value = unicodedata.normalize("NFKC", value).casefold().replace("+", " plus ")
        return re.sub(r"[^\w]+", " ", value).strip()

    def _strip_prefix(value: str) -> str:
        return _norm(ARM_PREFIX.sub("", value))

    def _tokens(value: str) -> set[str]:
        return set(_norm(value).split())

    arm_by_norm: dict[str, list[dict]] = {}
    for arm in arm_groups:
        for key in {_norm(str(arm.get("label", ""))), _strip_prefix(str(arm.get("label", "")))}:
            arm_by_norm.setdefault(key, []).append(arm)

    drug_types = {"DRUG", "BIOLOGICAL", "COMBINATION_PRODUCT"}
    intervention_type = {str(i.get("name", "")): str(i.get("type") or "") for i in interventions}

    def _name_parts(name: str) -> set[str]:
        """'ZD6474 (Vandetanib)' -> {'zd6474 (vandetanib)', 'zd6474', 'vandetanib'};
        a drug's base name too: 'pemetrexed disodium' -> 'pemetrexed'."""
        parts = {name.casefold().strip()}
        parts |= {x.strip().casefold() for x in re.split(r"[()/,]", name) if len(x.strip()) >= 4}
        first = name.split()[0] if name.split() else ""
        if intervention_type.get(name) in drug_types and len(name.split()) > 1 and len(first) >= 5:
            parts.add(first.casefold())
        return {x for x in parts if x}

    # Intervention names that belong to exactly one arm identify that arm.
    owners: dict[str, set[str]] = {}
    for item in interventions:
        for part in _name_parts(str(item.get("name", ""))):
            for label in item.get("armGroupLabels", []):
                owners.setdefault(part, set()).add(label)
    shared_by_all = [
        str(item["name"])
        for item in interventions
        if item.get("name") and arm_groups
        and {str(a.get("label")) for a in arm_groups} <= set(item.get("armGroupLabels", []))
    ]
    virtual_arms: dict[str, list[str]] = {}
    claimed: dict[tuple[str, str, str | None], str] = {}

    def _mentions(name_owner: dict[str, set[str]], text: str) -> set[str]:
        lowered = unicodedata.normalize("NFKC", text).casefold()
        return {
            next(iter(labels))
            for name, labels in name_owner.items()
            if name and len(labels) == 1 and re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", lowered)
        }

    def _by_overlap(title: str) -> dict | None:
        scored = []
        for arm in arm_groups:
            a, b = _tokens(title), _tokens(str(arm.get("label", "")))
            if a and b:
                scored.append((len(a & b) / len(a | b), arm))
        scored.sort(key=lambda item: -item[0])
        if scored and scored[0][0] >= 0.8 and (len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.15):
            return scored[0][1]
        return None

    def resolve_group(
        title: str, allow_subgroup: bool, group: dict | None = None
    ) -> tuple[str, str | None] | None:
        arm = arm_by_title.get(title.casefold())
        if arm is None and allow_subgroup:
            # "<arm>: Female" is a reported subgroup of that arm; check before looser matching.
            for separator in (": ", " | ", " - "):
                if separator in title:
                    arm_label, criterion = title.split(separator, 1)
                    subgroup_arm = arm_by_title.get(arm_label.casefold())
                    if subgroup_arm is not None and criterion.casefold() in {"female", "male"}:
                        return str(subgroup_arm["label"]), criterion.title()
        if re.fullmatch(r"\s*total\s*", title, re.IGNORECASE):
            return None
        how = "exact"
        if arm is None:
            candidates = arm_by_norm.get(_norm(title)) or arm_by_norm.get(_strip_prefix(title)) or []
            arm, how = (candidates[0], "normalised_label") if len(candidates) == 1 else (None, how)
        if arm is None and len(arm_groups) > 1:
            hits = _mentions(owners, title)
            if len(hits) == 1:
                arm, how = arm_by_title.get(next(iter(hits)).casefold()), "unique_intervention_name"
        if arm is None and re.search(r"\bplacebo\b", title, re.IGNORECASE) and not re.search(r"\bplus\b|\+|/", title):
            placebo = [a for a in arm_groups if a.get("type") == "PLACEBO_COMPARATOR"] or [
                a for a in arm_groups if not any(str(a.get("label")) in i.get("armGroupLabels", []) for i in interventions)
            ]
            if len(placebo) == 1:
                virtual_arms.setdefault(str(placebo[0]["label"]), ["placebo"])
                arm, how = placebo[0], "placebo_comparator_arm"
        if arm is None and len(arm_groups) > 1:
            arm = _by_overlap(title)
            how = "label_word_overlap" if arm is not None else how
        if arm is None and len(arm_groups) == 1:
            arm, how = arm_groups[0], "single_arm"
        if arm is not None:
            if how != "exact":
                parsed.audit.append(AuditItem("group_matched_to_arm", title, {"arm": arm["label"], "via": how}))
            return str(arm["label"]), None
        return virtual_group(title, group)

    def _named(text: str) -> list[str]:
        lowered = unicodedata.normalize("NFKC", text).casefold()
        return [
            str(item["name"])
            for item in interventions
            if item.get("name") and any(
                re.search(rf"(?<![\w-]){re.escape(part)}(?![\w-])", lowered) for part in _name_parts(str(item["name"]))
            )
        ]

    def virtual_group(title: str, group: dict | None) -> tuple[str, None] | None:
        """A result group that is its own population. Its treatment is what its title names;
        a placebo group is placebo; a description is used only when it does not mention placebo;
        otherwise what every arm received."""
        description = str((group or {}).get("description") or "")
        placebo = bool(re.search(r"\bplacebo\b", title, re.IGNORECASE))
        drugs = _named(title)
        if placebo:
            drugs = ["placebo", *drugs]
        elif not drugs and not re.search(r"\bplacebo\b", description, re.IGNORECASE):
            drugs = _named(description)
        drugs = drugs or shared_by_all
        if not drugs:
            return None
        label = f"result group: {title.strip()}"
        virtual_arms.setdefault(label, sorted(set(drugs), key=drugs.index))
        parsed.audit.append(AuditItem("result_group_profile", title, {"treatment": virtual_arms[label]}))
        return label, None

    def record_denominator(profile: ClinicalProfile, denominator: int | None) -> None:
        if denominator is not None:
            key = (profile.source_arm.casefold(), profile.source_population)
            reported_denominators.setdefault(key, set()).add(denominator)

    def arm_drugs(arm_label: str) -> list[str]:
        if arm_label in virtual_arms:
            return list(virtual_arms[arm_label])
        return [
            item["name"]
            for item in interventions
            if arm_label in item.get("armGroupLabels", []) and item.get("name")
        ]

    def describe_drug(arm_label: str) -> dict[str, Any]:
        names = arm_drugs(arm_label)
        arm = arm_by_title.get(arm_label.casefold())
        arm_type = {"arm_type": str(arm["type"]).casefold()} if arm is not None and arm.get("type") else {}
        if len(names) != 1:
            return {"reported_arm": arm_label, **arm_type, **({"interventions": names} if names else {})}
        return {"reported_name": names[0], "drug": names[0], **arm_type}

    def base_patient_group() -> dict[str, Any]:
        return {
            **({"eligibility": dict(eligibility_limits)} if eligibility_limits else {}),
        }

    def sequence_profile(group: dict[str, Any], title: str) -> ClinicalProfile | None:
        """A reported group of patients who received one arm and then another."""
        match = SEQUENCE_GROUP.match(title)
        if not match:
            return None
        first = arm_by_title.get(match.group("first").strip().casefold())
        second = arm_by_title.get(match.group("second").strip().casefold())
        if first is None or second is None or first is second:
            return None
        key = (title.casefold(), "treatment_arm_aggregate")
        if key in profiles:
            return profiles[key]
        description = str(group.get("description") or "")
        step_two = describe_drug(str(second["label"]))
        switch: dict[str, Any] = {
            "randomized_to": describe_drug(str(first["label"])).get("drug", first["label"]),
            "switched_to": step_two.get("drug", second["label"]),
        }
        if re.search(r"\bprogress", description, re.IGNORECASE):
            switch["switch_trigger"] = "disease_progression"
            if re.search(r"independent central", description, re.IGNORECASE):
                switch["progression_confirmation"] = "independent_central_review"
        if re.search(r"early efficacy|data monitoring committee", description, re.IGNORECASE):
            switch["alternative_trigger"] = "data_monitoring_committee_early_efficacy"
        profile = ClinicalProfile(
            source_nct=nct_id,
            source_arm=title,
            source_population="treatment_arm_aggregate",
            disease=disease,
            histology=histology,
            setting=setting,
            primary_biomarker=primary_biomarker,
            primary_drug=step_two.get("drug"),
            drug_class=step_two.get("drug_class"),
            patient_group={**base_patient_group(), "treatment_history_in_trial": switch},
            treatment={**step_two, "line_context": "after_progression_on_comparator_arm"},
            source={"nct_id": nct_id, "publication_ids": []},
        )
        profiles[key] = profile
        return profile

    def profile_for(
        group: dict[str, Any],
        population: str,
        path: str,
        *,
        allow_subgroup: bool = False,
        allow_sequence: bool = False,
    ) -> ClinicalProfile | None:
        title = str(group.get("title") or "").strip()
        if not title:
            parsed.audit.append(AuditItem("review_required", path, {"reason": "arm_missing"}))
            return None
        if allow_sequence and arm_by_title.get(title.casefold()) is None:
            # Crossover groups ("X, then switched to Y") are checked before looser matching.
            sequence = sequence_profile(group, title)
            if sequence is not None:
                return sequence
        resolved = resolve_group(title, allow_subgroup, group)
        if resolved is not None and not resolved[0].startswith("result group: "):
            module = re.sub(
                r"\.(?:classes|categories|measurements|milestones|achievements|dropWithdraws|reasons|analyses)\[\d+\].*$",
                "", path,
            )
            module = re.sub(r"\.eventGroups\[\d+\]$", "", module)
            claim_key = (module, resolved[0], resolved[1])
            owner = claimed.setdefault(claim_key, title)
            if owner != title:
                parsed.audit.append(
                    AuditItem("second_group_for_same_arm", path, {"arm": resolved[0], "first": owner, "second": title})
                )
                resolved = virtual_group(title, group)
        if resolved is None:
            parsed.audit.append(
                AuditItem("review_required", path, {"reason": "arm_not_matched", "group": title})
            )
            return None
        arm_label, explicit_sex = resolved
        subgroup = allow_subgroup and (
            explicit_sex is not None or bool(CLINICAL_SUBGROUP.search(population))
        )
        if allow_subgroup and not subgroup and not OVERALL_ANALYSIS.search(population):
            # An analysis subset (for example "with measurable disease"): the values stay on the
            # arm with their own denominator and the population wording, never the arm's n.
            parsed.audit.append(
                AuditItem("analysis_subset_population", path, {"population": population[:200]})
            )
        profile_population = (
            (title if explicit_sex else population.strip())
            if subgroup
            else "treatment_arm_aggregate"
        )
        key = (arm_label.casefold(), profile_population)
        if key not in profiles:
            sex = explicit_sex
            if sex is None and re.fullmatch(
                r"(?:female|male) (?:participants|patients)", population.strip(), re.IGNORECASE
            ):
                sex = population.split()[0].title()
            profile = ClinicalProfile(
                source_nct=nct_id,
                source_arm=arm_label,
                source_population=profile_population,
                disease=disease,
                histology=histology,
                setting=setting,
                primary_biomarker=primary_biomarker,
                cancer={
                    "reported_conditions": conditions,
                    **({"histology": histology} if histology else {}),
                    **({"setting": setting} if setting else {}),
                },
                patient_group={
                    "scope": "reported_clinical_subgroup"
                    if subgroup
                    else "treatment_arm_aggregate",
                    **(
                        {"definition": title if explicit_sex else population.strip()}
                        if subgroup
                        else {}
                    ),
                    **({"sex": sex} if sex else {}),
                    **base_patient_group(),
                },
                treatment=describe_drug(arm_label),
                source={"nct_id": nct_id, "publication_ids": []},
            )
            profile.primary_drug = profile.treatment.get("drug")
            profile.drug_class = profile.treatment.get("drug_class")
            profiles[key] = profile
        profile = profiles[key]
        names = arm_drugs(arm_label)
        if "dose" not in profile.treatment and len(names) == 1:
            profile.treatment.update(regimen(str(group.get("description") or ""), names))
        return profile

    def add_context(payload: dict[str, Any], population: str) -> None:
        if population.strip():
            payload["analysis_population"] = population.strip()

    results = study["resultsSection"]
    baseline = results.get("baselineCharacteristicsModule", {})
    baseline_groups = _group_lookup(baseline.get("groups", []))
    baseline_denoms = _denominators(baseline.get("denoms", []))
    for measure_index, measure in enumerate(baseline.get("measures", [])):
        population = str(baseline.get("populationDescription") or "")
        for ci, ca, mi, item in _measurements(measure):
            reported = item["measurement"]
            group_id = str(reported.get("groupId") or "")
            path = (
                "$.resultsSection.baselineCharacteristicsModule.measures"
                f"[{measure_index}].classes[{ci}].categories[{ca}].measurements[{mi}]"
            )
            group = baseline_groups.get(group_id)
            if group is None:
                parsed.audit.append(
                    AuditItem("review_required", path, {"reason": "group_not_found"})
                )
                continue
            profile = profile_for(group, population, path)
            if profile is None:
                continue
            payload = _payload(measure, item, baseline_denoms.get(group_id))
            if payload is None:
                parsed.audit.append(
                    AuditItem("unparsed_value", path, {"value": reported.get("value")})
                )
                continue
            add_context(payload, population)
            profile.baseline.setdefault("measures", []).append(payload)
            record_denominator(profile, baseline_denoms.get(group_id))
            if measure.get("title") == "Age, Continuous" and measure.get("paramType") == "MEAN":
                age = {
                    "mean": payload["value"],
                    "unit": payload.get("unit"),
                    "denominator": payload.get("denominator"),
                    "analysis_population": population,
                }
                if measure.get("dispersionType") == "STANDARD_DEVIATION" and "spread" in payload:
                    age["standard_deviation"] = payload["spread"]
                profile.patient_group["age"] = age
            if (
                str(measure.get("title", "")).startswith("Sex:")
                and payload.get("statistic") == "COUNT_OF_PARTICIPANTS"
                and payload.get("category") in {"Female", "Male"}
            ):
                profile.patient_group.setdefault("sex", {})[payload["category"]] = {
                    "n": payload["value"],
                    "denominator": payload.get("denominator"),
                    "analysis_population": population,
                }
            for source_title, target in (
                ("Race (NIH/OMB)", "race"),
                ("Ethnicity (NIH/OMB)", "ethnicity"),
            ):
                if (
                    measure.get("title") == source_title
                    and payload.get("statistic") == "COUNT_OF_PARTICIPANTS"
                    and payload.get("category")
                ):
                    profile.patient_group.setdefault(target, {})[payload["category"]] = {
                        "n": payload["value"],
                        "denominator": payload.get("denominator"),
                    }
            parsed.audit.append(AuditItem("extracted_baseline", path, {"arm": profile.source_arm}))

    outcomes = results.get("outcomeMeasuresModule", {}).get("outcomeMeasures", [])
    for outcome_index, outcome in enumerate(outcomes):
        group_map = _group_lookup(outcome.get("groups", []))
        denoms = _denominators(outcome.get("denoms", []))
        population = str(outcome.get("populationDescription") or "")
        section = _outcome_section(outcome)
        for ci, ca, mi, item in _measurements(outcome):
            reported = item["measurement"]
            group_id = str(reported.get("groupId") or "")
            path = (
                f"$.resultsSection.outcomeMeasuresModule.outcomeMeasures[{outcome_index}]"
                f".classes[{ci}].categories[{ca}].measurements[{mi}]"
            )
            group = group_map.get(group_id)
            if group is None:
                parsed.audit.append(
                    AuditItem("review_required", path, {"reason": "group_not_found"})
                )
                continue
            profile = profile_for(group, population, path, allow_subgroup=True)
            if profile is None:
                continue
            payload = _payload(outcome, item, denoms.get(group_id))
            if payload is None:
                parsed.audit.append(
                    AuditItem("unparsed_value", path, {"value": reported.get("value")})
                )
                continue
            add_context(payload, population)
            if population.strip() and not OVERALL_ANALYSIS.search(population) and not CLINICAL_SUBGROUP.search(population):
                payload["population_scope"] = "analysis_subset"
            payload["reported_result_group"] = group["title"]
            if assessment := outcome_assessment(str(outcome.get("description") or "")):
                payload["assessment"] = assessment
            if section:
                getattr(profile, section).setdefault("outcomes", []).append(payload)
            else:
                parsed.audit.append(AuditItem("unclassified_outcome", path, payload))
            if profile.source_population != "treatment_arm_aggregate":
                record_denominator(profile, denoms.get(group_id))
            parsed.audit.append(AuditItem("extracted_outcome", path, {"arm": profile.source_arm}))

        for analysis_index, analysis in enumerate(outcome.get("analyses", [])):
            path = (
                f"$.resultsSection.outcomeMeasuresModule.outcomeMeasures[{outcome_index}]"
                f".analyses[{analysis_index}]"
            )
            ids = analysis.get("groupIds", [])
            if len(ids) != 2 or not all(group_id in group_map for group_id in ids):
                parsed.audit.append(
                    AuditItem("review_required", path, {"reason": "comparison_group_ambiguity"})
                )
                continue
            first, second = (group_map[group_id] for group_id in ids)
            profile = profile_for(first, population, path, allow_subgroup=True)
            second_resolved = resolve_group(str(second.get("title") or ""), True)
            first_resolved = resolve_group(str(first.get("title") or ""), True)
            if (
                profile is None
                or second_resolved is None
                or first_resolved is None
                or first_resolved[1] != second_resolved[1]
            ):
                parsed.audit.append(
                    AuditItem("review_required", path, {"reason": "comparison_arm_ambiguity"})
                )
                continue
            value = numeric(analysis.get("paramValue"))
            if value is None:
                parsed.audit.append(
                    AuditItem("unparsed_value", path, {"value": analysis.get("paramValue")})
                )
                continue
            effect: dict[str, Any] = {
                "treatment": first_resolved[0],
                "comparator": second_resolved[0],
                "outcome": outcome.get("title"),
                "measure": analysis.get("paramType"),
                "value": value,
                "reported_group_order": [first["title"], second["title"]],
            }
            add_context(effect, population)
            lower = numeric(analysis.get("ciLowerLimit"))
            upper = numeric(analysis.get("ciUpperLimit"))
            if lower is not None and upper is not None:
                effect["confidence_interval"] = {
                    "percent": numeric(analysis.get("ciPctValue")),
                    "lower": lower,
                    "upper": upper,
                }
            if analysis.get("pValue") is not None:
                effect["p_value_reported"] = str(analysis["pValue"])
            if analysis.get("statisticalMethod"):
                effect["method"] = analysis["statisticalMethod"]
            profile.comparative_effects.append(effect)
            parsed.audit.append(
                AuditItem("extracted_comparison", path, {"arm": profile.source_arm})
            )

    safety = results.get("adverseEventsModule", {})
    safety_description = str(safety.get("description") or "")
    time_frame = str(safety.get("timeFrame") or "")
    windows = re.split(r"\bMortality\s*:", time_frame, maxsplit=1, flags=re.IGNORECASE)
    first_sentence = re.split(r"(?<=\.)\s+", safety_description)[0] if safety_description else ""
    ae_window = re.sub(r"^Adverse events\s*:\s*", "", windows[0].strip(), flags=re.IGNORECASE)
    parsed.safety_reporting = {
        key: value
        for key, value in {
            "adverse_event_population": population_label(first_sentence),
            "grouping": grouping_basis(safety_description),
            "adverse_event_window": ae_window or None,
            "mortality_window": windows[1].strip() if len(windows) > 1 else None,
            "mortality_population": "all_randomized"
            if re.search(
                r"mortality is reported for all randomi[sz]ed", safety_description, re.IGNORECASE
            )
            else None,
            "non_serious_reporting_threshold_percent": numeric(safety.get("frequencyThreshold")),
            "grade_reported": False,
            "causality_reported": False,
        }.items()
        if value is not None
    }
    event_profiles: dict[str, ClinicalProfile] = {}
    for index, group in enumerate(safety.get("eventGroups", [])):
        path = f"$.resultsSection.adverseEventsModule.eventGroups[{index}]"
        population = str(group.get("description") or "")
        profile = profile_for(group, population, path, allow_sequence=True)
        if profile is None:
            continue
        event_profiles[str(group.get("id"))] = profile
        for prefix in ("serious", "other", "deaths"):
            affected = group.get(f"{prefix}NumAffected")
            at_risk = group.get(f"{prefix}NumAtRisk")
            if not (
                isinstance(affected, int)
                and isinstance(at_risk, int)
                and 0 <= affected <= at_risk
                and at_risk > 0
            ):
                if affected is not None or at_risk is not None:
                    parsed.audit.append(
                        AuditItem(
                            "review_required",
                            path,
                            {"reason": "invalid_event_numerator_or_denominator", "field": prefix},
                        )
                    )
                continue
            if prefix == "deaths":
                # Counted per reporting group only. No rate: reporting groups can
                # overlap, e.g. a crossover group inside a randomised arm.
                profile.survival["all_cause_deaths_reported"] = {"n": affected, "at_risk": at_risk}
            else:
                name = (
                    "serious_adverse_events_any_cause"
                    if prefix == "serious"
                    else "non_serious_adverse_events_above_threshold"
                )
                profile.toxicity[name] = {"n": affected, "N": at_risk, "rate": affected / at_risk}
        if (
            profile.source_arm.casefold() not in arm_by_title
            and "serious_adverse_events_any_cause" in profile.toxicity
        ):
            profile.patient_group.setdefault(
                "n", profile.toxicity["serious_adverse_events_any_cause"]["N"]
            )
            profile.patient_group.setdefault("n_basis", "safety_at_risk")
        parsed.audit.append(AuditItem("safety_summary", path, {"arm": profile.source_arm}))

    # Every term is kept on the internal profile; the asset builder selects key events.
    for table, target in (("seriousEvents", "serious_terms"), ("otherEvents", "non_serious_terms")):
        for event in safety.get(table, []):
            stats = {
                str(stat.get("groupId")): stat
                for stat in event.get("stats", [])
                if isinstance(stat.get("numAffected"), int)
                and isinstance(stat.get("numAtRisk"), int)
                and 0 <= stat["numAffected"] <= stat["numAtRisk"]
                and stat["numAtRisk"] > 0
                and str(stat.get("groupId")) in event_profiles
            }
            for group_id, stat in stats.items():
                event_profiles[group_id].toxicity.setdefault(target, []).append(
                    {
                        "term": event.get("term"),
                        "organ_system": event.get("organSystem"),
                        "n": stat["numAffected"],
                        "N": stat["numAtRisk"],
                        "rate": stat["numAffected"] / stat["numAtRisk"],
                    }
                )
        if safety.get(table):
            parsed.audit.append(
                AuditItem(
                    "safety_terms_collected",
                    f"$.resultsSection.adverseEventsModule.{table}",
                    {"reported_terms": len(safety[table])},
                )
            )
        vocabularies = {
            e.get("sourceVocabulary") for e in safety.get(table, []) if e.get("sourceVocabulary")
        }
        if len(vocabularies) == 1:
            parsed.safety_reporting["vocabulary"] = vocabularies.pop()

    flow = results.get("participantFlowModule", {})
    flow_groups = _group_lookup(flow.get("groups", []))
    for period_index, period in enumerate(flow.get("periods", [])):
        period_title = str(period.get("title") or "")
        for milestone_index, milestone in enumerate(period.get("milestones", [])):
            for achievement_index, achievement in enumerate(milestone.get("achievements", [])):
                group_id = str(achievement.get("groupId") or "")
                group = flow_groups.get(group_id)
                path = (
                    f"$.resultsSection.participantFlowModule.periods[{period_index}]"
                    f".milestones[{milestone_index}].achievements[{achievement_index}]"
                )
                if group is None:
                    parsed.audit.append(
                        AuditItem("review_required", path, {"reason": "flow_group_missing"})
                    )
                    continue
                profile = profile_for(group, str(group.get("description") or ""), path)
                count = numeric(achievement.get("numSubjects"))
                if profile is None or not isinstance(count, int) or count < 0:
                    parsed.audit.append(
                        AuditItem("unparsed_value", path, {"value": achievement.get("numSubjects")})
                    )
                    continue
                profile.treatment_course.setdefault("participant_flow", []).append(
                    {
                        "period": period_title,
                        "milestone": milestone.get("type"),
                        "n": count,
                    }
                )
                parsed.audit.append(AuditItem("extracted_flow", path, {"arm": profile.source_arm}))
        for reason_index, reason in enumerate(period.get("dropWithdraws", [])):
            for count_index, count_item in enumerate(reason.get("reasons", [])):
                group_id = str(count_item.get("groupId") or "")
                group = flow_groups.get(group_id)
                path = (
                    f"$.resultsSection.participantFlowModule.periods[{period_index}]"
                    f".dropWithdraws[{reason_index}].reasons[{count_index}]"
                )
                if group is None:
                    parsed.audit.append(
                        AuditItem("review_required", path, {"reason": "flow_group_missing"})
                    )
                    continue
                profile = profile_for(group, str(group.get("description") or ""), path)
                count = numeric(count_item.get("numSubjects"))
                if profile is None or not isinstance(count, int) or count < 0:
                    parsed.audit.append(
                        AuditItem("unparsed_value", path, {"value": count_item.get("numSubjects")})
                    )
                    continue
                profile.treatment_course.setdefault("withdrawal_reasons", []).append(
                    {
                        "period": period_title,
                        "reason": reason.get("type"),
                        "n": count,
                    }
                )
                parsed.audit.append(AuditItem("extracted_flow", path, {"arm": profile.source_arm}))

    flow_deaths: dict[str, int] = {}
    for period in flow.get("periods", []):
        for reason in period.get("dropWithdraws", []):
            if str(reason.get("type", "")).casefold() != "death":
                continue
            for item in reason.get("reasons", []):
                group = flow_groups.get(str(item.get("groupId") or ""))
                count = numeric(item.get("numSubjects"))
                if group is not None and isinstance(count, int):
                    arm = str(group.get("title") or "").casefold()
                    flow_deaths[arm] = flow_deaths.get(arm, 0) + count
    for arm_key, flow_count in flow_deaths.items():
        arm_profile = profiles.get((arm_key, "treatment_arm_aggregate"))
        if arm_profile is None or "all_cause_deaths_reported" not in arm_profile.survival:
            continue
        own = arm_profile.survival["all_cause_deaths_reported"]["n"]
        followers = [
            candidate
            for candidate in profiles.values()
            if (match := SEQUENCE_GROUP.match(candidate.source_arm))
            and match.group("first").strip().casefold() == arm_key
            and "all_cause_deaths_reported" in candidate.survival
        ]
        follower_deaths = sum(f.survival["all_cause_deaths_reported"]["n"] for f in followers)
        if flow_count not in {own, own + follower_deaths}:
            parsed.source_conflicts.append(
                {
                    "topic": "all_cause_deaths",
                    "randomized_arm": arm_profile.source_arm,
                    "adverse_events_module_deaths": own,
                    **(
                        {
                            "switched_group": [f.source_arm for f in followers],
                            "adverse_events_module_deaths_in_switched_group": follower_deaths,
                        }
                        if followers
                        else {}
                    ),
                    "participant_flow_deaths": flow_count,
                    "consequence": "arm-level mortality is not stated as a rate until reconciled",
                }
            )

    for key, profile in profiles.items():
        denominators = reported_denominators.get(key, set())
        if len(denominators) == 1:
            profile.patient_group["n"] = next(iter(denominators))
            profile.patient_group["n_basis"] = (
                "reported_outcome_subgroup"
                if key[1] != "treatment_arm_aggregate"
                else "reported_baseline"
            )
        elif len(denominators) > 1:
            parsed.audit.append(
                AuditItem(
                    "review_required",
                    "$.resultsSection",
                    {
                        "reason": "population_denominators_differ_by_measure",
                        "arm": profile.source_arm,
                        "population": profile.source_population,
                        "reported_denominators": sorted(denominators),
                    },
                )
            )

    parsed.profiles = [
        profile
        for profile in profiles.values()
        if profile.baseline
        or profile.response
        or profile.survival
        or profile.toxicity
        or profile.comparative_effects
        or profile.treatment_course
    ]
    if not parsed.profiles:
        parsed.audit.append(
            AuditItem("review_required", "$.resultsSection", {"reason": "no_safe_profile"})
        )
    return parsed
