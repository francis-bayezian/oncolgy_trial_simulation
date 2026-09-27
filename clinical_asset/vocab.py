"""Canonical vocabularies built from the corpus itself.

Each entry carries its canonical key, UMLS concept when known, how many trials and profiles use
it, and the source wordings that map to it. Nothing is added that the corpus does not contain.
"""

from collections import Counter, defaultdict
from typing import Any


def _entry(store: dict, key: str, nct: str, **fields: Any) -> dict:
    entry = store.setdefault(key, {"key": key, "trials": set(), "profiles": 0, "reported": Counter()})
    entry["trials"].add(nct)
    entry["profiles"] += 1
    for name, value in fields.items():
        if value is None:
            continue
        if name == "reported":
            entry["reported"][str(value)[:200]] += 1
        elif name.endswith("_set"):
            entry.setdefault(name[:-4], set()).add(value)
        else:
            entry.setdefault(name, value)
    return entry


def build_vocabularies(profiles: list[dict]) -> dict[str, list[dict]]:
    cancers: dict = {}
    regimens: dict = {}
    drugs: dict = {}
    biomarkers: dict = {}
    outcomes: dict = {}
    toxicities: dict = {}
    course: dict = {}
    units: Counter = Counter()
    statistics: Counter = Counter()
    for profile in profiles:
        nct = profile["profile_id"].split("-")[0]
        cancer = profile.get("cancer", {})
        if disease := cancer.get("disease"):
            _entry(cancers, disease["umls_cui"], nct, name=disease["name"], umls_cui=disease["umls_cui"],
                   settings_set=cancer.get("setting"))
        for marker in cancer.get("biomarkers", []):
            _entry(biomarkers, marker["umls_cui"], nct, name=f"{marker['gene']} {marker['variant']}",
                   gene=marker["gene"], variant=marker["variant"], umls_cui=marker["umls_cui"])
        treatment = profile.get("treatment", {})
        ontology = profile.get("treatment_ontology", {})
        if regimen := treatment.get("regimen"):
            _entry(regimens, regimen, nct, reported=treatment.get("reported_name") or profile["source"].get("registry_group"),
                   components=tuple(treatment.get("interventions") or [treatment.get("drug")]))
        for name in treatment.get("interventions") or ([treatment["drug"]] if treatment.get("drug") else []):
            entry = _entry(drugs, name, nct, reported=treatment.get("reported_name"))
            if treatment.get("drug") == name:
                for field in ("umls_cui", "mesh_id", "drug_class"):
                    if ontology.get(field):
                        entry.setdefault(field, ontology[field])
                if isinstance(ontology.get("target"), dict) and ontology["target"].get("umls_cui"):
                    entry.setdefault("target", ontology["target"])
        for key, observations in profile.get("efficacy", {}).items():
            for obs in observations:
                _entry(outcomes, key, nct, umls_cui=obs.get("umls_cui"), reported=obs.get("measure") or key,
                       statistics_set=obs.get("statistic"), units_set=obs.get("unit"))
                statistics[obs.get("statistic")] += 1
                units[obs.get("unit")] += 1
        toxicity = profile.get("toxicity", {})
        for section, seriousness in (("key_events", "non_serious"), ("key_serious_events", "serious")):
            for key, event in toxicity.get(section, {}).items():
                _entry(toxicities, key, nct, umls_cui=event.get("umls_cui"), seriousness_set=seriousness)
        for key in toxicity:
            if key.startswith("key_grade_3"):
                for event_key, event in toxicity[key].get("events", {}).items():
                    _entry(toxicities, event_key, nct, umls_cui=event.get("umls_cui"), seriousness_set="grade_3_plus")
        for reason in profile.get("treatment_course", {}).get("study_status_at_data_cutoff", {}):
            _entry(course, reason, nct)

    def finish(store: dict) -> list[dict]:
        rows = []
        for entry in store.values():
            if not isinstance(entry, dict) or "trials" not in entry:
                continue
            row = {k: (sorted(v) if isinstance(v, set) else v) for k, v in entry.items() if k not in {"trials", "reported"}}
            row["trials"] = len(entry["trials"])
            if entry["reported"]:
                row["reported_as"] = [text for text, _ in entry["reported"].most_common(10)]
            rows.append(row)
        return sorted(rows, key=lambda r: (-r["trials"], str(r["key"])))

    return {
        "cancers": finish(cancers),
        "regimens": finish(regimens),
        "drugs": finish(drugs),
        "biomarkers": finish(biomarkers),
        "outcomes": finish(outcomes),
        "toxicities": finish(toxicities),
        "treatment_course_reasons": finish(course),
        "units": [{"key": k, "observations": n} for k, n in units.most_common() if k],
        "statistics": [{"key": k, "observations": n} for k, n in statistics.most_common() if k],
    }


def group_counts(profiles: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for profile in profiles:
        counts[profile.get("profile_type", "unknown")] += 1
    return dict(counts)
