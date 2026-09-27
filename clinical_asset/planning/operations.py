"""Registry participant-flow evidence for screening and retention planning."""

import json
import re
from collections import Counter
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

REASONS = (
    ("progression", r"progress|lack of efficacy|relapse"),
    ("toxicity", r"adverse|toxicit"),
    ("withdrawal", r"withdraw|refus|patient.?s choice|subject.?s choice"),
    ("loss_to_followup", r"lost to follow"),
    ("physician_decision", r"physician decision"),
    ("death", r"death|died"),
    ("protocol_violation", r"protocol violation|non.compliance"),
    ("alternative_treatment", r"alternative (therapy|treatment)"),
)
SCREENED = re.compile(r"\b(\d[\d,]*)\s+(?:patients|participants|subjects|potential candidates)\b.{0,110}?\b(?:were\s+)?screened\b", re.IGNORECASE)
ENROLLED = re.compile(r"\b(\d[\d,]*)\s+(?:patients|participants|subjects)\s+(?:were\s+|finally\s+)?enrolled\b", re.IGNORECASE)
RANDOMIZED = re.compile(r"\b(\d[\d,]*)\s+(?:patients|participants|subjects)\s+(?:were\s+)?randomi[sz]ed\b", re.IGNORECASE)
SCREEN_FAILURE = re.compile(r"\b(\d[\d,]*)\s+screen(?:ing)? failures?\b", re.IGNORECASE)


def _count(value):
    try:
        return int(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return None


def _totals(entries, key):
    totals = {}
    for item in entries:
        for achievement in item.get(key) or []:
            group, n = achievement.get("groupId"), _count(achievement.get("numSubjects"))
            if group and n is not None:
                totals[group] = totals.get(group, 0) + n
    return totals


def _reason(label):
    for canonical, pattern in REASONS:
        if re.search(pattern, label, re.IGNORECASE):
            return canonical
    return "other"


def extract(study):
    p = study.get("protocolSection") or {}
    nct = (p.get("identificationModule") or {}).get("nctId")
    flow = (study.get("resultsSection") or {}).get("participantFlowModule") or {}
    details = " ".join((flow.get("recruitmentDetails") or "").split())
    screened = SCREENED.search(details)
    enrolled = ENROLLED.search(details)
    randomized = RANDOMIZED.search(details)
    failure = SCREEN_FAILURE.search(details)
    screen_n = _count(screened.group(1)) if screened else None
    enrolled_n = _count(enrolled.group(1)) if enrolled else None
    randomized_n = _count(randomized.group(1)) if randomized else None
    failure_n = _count(failure.group(1)) if failure else None
    screening = {"nct_id": nct, "screened": screen_n, "enrolled": enrolled_n,
                 "randomized": randomized_n,
                 "screen_failures": failure_n, "conversion": None, "quality": "UNRESOLVED",
                 "evidence": details[:600] if (screened or failure) else None}
    if screen_n and enrolled_n is not None and 0 <= enrolled_n <= screen_n:
        screening["conversion"] = enrolled_n / screen_n
        screening["quality"] = "DIRECT"
    elif screen_n and randomized_n is not None and 0 <= randomized_n <= screen_n:
        screening["conversion"] = randomized_n / screen_n
        screening["quality"] = "DIRECT_RANDOMIZED"
    elif failure_n is not None and enrolled_n is not None:
        screening["quality"] = "LOWER_BOUND"
        screening["screened_lower_bound"] = enrolled_n + failure_n
    retention = []
    periods = flow.get("periods") or []
    if periods:
        period = next((x for x in periods if (x.get("title") or "").lower() == "overall study"), periods[0])
        milestones = {x.get("type", "").upper(): _totals([x], "achievements") for x in period.get("milestones") or []}
        started = milestones.get("STARTED") or {}
        completed = milestones.get("COMPLETED") or {}
        reasons = {}
        for item in period.get("dropWithdraws") or []:
            for group, n in _totals([item], "reasons").items():
                key = (group, _reason(item.get("type") or ""))
                reasons[key] = reasons.get(key, 0) + n
        for group, n in started.items():
            done = completed.get(group)
            if n <= 0 or done is None or done > n:
                continue
            retention.append({"nct_id": nct, "period": period.get("title"), "group_id": group,
                              "started": n, "completed": done, "completion_fraction": done / n,
                              "not_completed": n - done, "quality": "DIRECT_CUMULATIVE",
                              "time_to_dropout": None,
                              "reasons": json.dumps({k: v for (g, k), v in reasons.items() if g == group}, sort_keys=True)})
    return screening, retention


def build(manifest: Path, holdout: Path, raw_dir: Path, out_dir: Path):
    source = json.loads(manifest.read_text(encoding="utf-8"))
    excluded = set(json.loads(holdout.read_text(encoding="utf-8"))["nct_ids"])
    screens, retention = [], []
    for item in source["trials"]:
        nct = item["nct_id"]
        if nct in excluded or not (raw_dir / f"{nct}.json").exists():
            continue
        study = json.loads((raw_dir / f"{nct}.json").read_text(encoding="utf-8"))
        screen, groups = extract(study)
        screens.append(screen)
        retention.extend(groups)
    out_dir.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(screens), out_dir / "screening.parquet")
    pq.write_table(pa.Table.from_pylist(retention), out_dir / "retention.parquet")
    fractions = np.array([x["completion_fraction"] for x in retention], dtype=float)
    result = {"trials": len(screens), "screening_quality_counts": dict(Counter(x["quality"] for x in screens)),
              "retention_groups": len(retention), "retention_trials": len({x["nct_id"] for x in retention}),
              "holdout_excluded": len(excluded),
              "completion_benchmark": {"status": "UNADJUSTED_CONTEXT_ONLY", "median": float(np.median(fractions)),
                                       "p10_p90": [float(x) for x in np.quantile(fractions, [.1, .9])],
                                       "meaning": "fraction completing first or overall participant-flow period; not endpoint evaluability or time to dropout"}}
    (out_dir / "manifest.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
