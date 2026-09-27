"""Clinical contexts: which observations may inform the same parameter.

Context dimensions stay separate fields (never one concatenated key as the scientific model).
Observations are pooled only when disease concept, setting, biomarker, treatment, subgroup
definition, variable, statistic family, event class, timepoint and category all match. A missing
setting or biomarker is its own value ("unspecified"), so it is never pooled with a stated one.
"""

import hashlib
import json
from collections import defaultdict

PROPORTION_DOMAINS = {"response", "survival", "progression", "biomarker", "patient_reported", "safety", "mortality",
                      "treatment_course", "safety_other"}
CONTEXT_FIELDS = ("disease_cui", "setting", "biomarker", "regimen", "comparator", "subgroup_definition")
TARGET_FIELDS = ("domain", "variable", "statistic_family", "event_class", "time", "time_unit", "category")


def _norm(value):
    return "unspecified" if value in (None, "") else value


def parameter_id(context: dict, target: dict) -> str:
    return hashlib.sha1(json.dumps([context, target], sort_keys=True, default=str).encode()).hexdigest()[:16]


def route(row: dict) -> str | None:
    """Which model family a row belongs to, or None (deferred / not modelled in milestone 1)."""
    family = row["statistic_family"]
    if not row["canonical"] and row["domain"] not in {"safety", "baseline", "study_disposition", "mortality", "treatment_course"}:
        return None
    if family in {"hazard_ratio", "odds_ratio", "risk_ratio"}:
        return "relative_effect"
    if family == "categorical" or (row.get("response_category") and family == "proportion"):
        return "categorical"
    if family in {"proportion", "survival_probability"} and row["domain"] in PROPORTION_DOMAINS | {"efficacy_other"}:
        return "binomial"
    if family == "continuous_mean":
        return "continuous"
    return None


def build_contexts(rows: list[dict]) -> tuple[dict, dict]:
    """Group rows into (model, context, target) → observations. Returns groups and skip counts."""
    groups: dict[tuple, dict] = {}
    skipped: dict[str, int] = defaultdict(int)
    for row in rows:
        model = route(row)
        if model is None:
            reason = (
                "deferred_to_survival_stage" if row["statistic_family"].endswith("_time")
                else "non_canonical_outcome" if not row["canonical"] else f"not_modelled_{row['statistic_family']}"
            )
            skipped[reason] += 1
            continue
        context = {f: _norm(row.get(f)) for f in CONTEXT_FIELDS}
        context["disease"] = row.get("disease")
        if row["domain"] in {"baseline"}:
            # Baseline characteristics describe the population, not the treatment.
            context.update(regimen="any", comparator="unspecified")
        target = {f: row.get(f) for f in TARGET_FIELDS}
        if model == "categorical":
            target["category"] = None
            if row.get("response_category"):
                target["variable"] = f"{row['variable']}_categories"
        if model == "relative_effect":
            target["time"] = target["time_unit"] = None
        key = (model, json.dumps(context, sort_keys=True, default=str), json.dumps(target, sort_keys=True, default=str))
        group = groups.setdefault(key, {"model": model, "context": context, "target": target, "rows": []})
        group["rows"].append(row)
    return groups, dict(skipped)
