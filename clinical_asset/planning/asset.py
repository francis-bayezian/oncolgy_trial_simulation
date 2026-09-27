"""Classify historical recruitment evidence without confusing follow-up with accrual."""

import hashlib
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

VERSION = "planning-asset-1.0.0"
MONTHS = {name.lower(): i for i, name in enumerate(("January", "February", "March", "April", "May", "June",
                                                    "July", "August", "September", "October", "November", "December"), 1)}
DATE_WORD = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
DATE_TOKEN = re.compile(rf"\b(?:\d{{1,2}}\s+)?{DATE_WORD}\s*,?\s*(?:\d{{1,2}},?\s*)?\d{{4}}\b", re.IGNORECASE)
MONTH_ALIASES = {name[:3].lower(): number for name, number in MONTHS.items()}


def _date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value if len(value) == 10 else value + "-01")
    except ValueError:
        return None


def _text_date(value):
    parts = re.sub(r",", "", value).split()
    day_first = parts[0].isdigit()
    month = MONTH_ALIASES.get(parts[1 if day_first else 0][:3].lower())
    if not month:
        return None
    try:
        day = int(parts[0]) if day_first else (int(parts[1]) if len(parts) == 3 else 1)
        return date(int(parts[-1]), month, day)
    except ValueError:
        return None


def _recruitment_period(details: str):
    """Only accept a pair of dates explicitly tied to recruitment or enrollment."""
    clean = " ".join(details.split())
    if re.search(r"actual enrollment|data cut.off|temporarily closed", clean, re.IGNORECASE):
        return None
    starts = re.finditer(r"\b(?:recruitment|enrollment|enrolled|accrual|accrued|first patient)\b", clean, re.IGNORECASE)
    for marker in starts:
        segment = clean[marker.start():marker.start() + 260]
        dates = list(DATE_TOKEN.finditer(segment))
        if len(dates) < 2:
            continue
        if dates[0].start() > 125 or dates[1].start() - dates[0].end() > 110:
            continue
        bridge = segment[dates[0].end():dates[1].start()].lower()
        prefix = segment[:dates[0].start()].lower()
        if re.search(r"\b(arm [a-z]|cohort [a-z]|stratum|interim|data was collected|study ended|study was conducted)\b", segment[:dates[1].end()], re.IGNORECASE):
            continue
        if not re.search(r"\b(from|between|began|period|first patient|open|enrolled|accrued)\b", prefix):
            continue
        if not re.search(r"\b(to|through|until|and ended|closed|ended|between)\b|[-–]", bridge):
            continue
        first, last = _text_date(dates[0].group()), _text_date(dates[1].group())
        if not first or not last or last <= first:
            continue
        if "first patient" in prefix or "patients were enrolled" in prefix or "enrollment from" in prefix:
            quality = "ACCRUAL_DIRECT"
        elif "open to accrual" in prefix or "opened to accrual" in prefix:
            quality = "ACCRUAL_APPROXIMATE"
        else:
            quality = "ACCRUAL_DERIVED"
        precision = "DAY" if all(len(re.sub(r",", "", x.group()).split()) == 3 for x in dates[:2]) else "MONTH"
        return first, last, quality, segment[:dates[1].end()], precision
    return None


def classify(study: dict) -> dict:
    p = study.get("protocolSection") or {}
    status = p.get("statusModule") or {}
    design = p.get("designModule") or {}
    locations = (p.get("contactsLocationsModule") or {}).get("locations") or []
    enrollment = design.get("enrollmentInfo") or {}
    conditions = (p.get("conditionsModule") or {}).get("conditions") or []
    details = ((study.get("resultsSection") or {}).get("participantFlowModule") or {}).get("recruitmentDetails") or ""
    start = _date((status.get("startDateStruct") or {}).get("date"))
    primary = _date((status.get("primaryCompletionDateStruct") or {}).get("date"))
    completion = _date((status.get("completionDateStruct") or {}).get("date"))
    count = enrollment.get("count") if enrollment.get("type") == "ACTUAL" else None
    sites = len({(x.get("facility"), x.get("city"), x.get("country")) for x in locations})
    row = {
        "nct_id": (p.get("identificationModule") or {}).get("nctId"),
        "phase": ",".join(design.get("phases") or []),
        "design": (design.get("designInfo") or {}).get("interventionModel"),
        "conditions": conditions,
        "enrollment_actual": count,
        "site_count_listed": sites or None,
        "country_count_listed": len({x.get("country") for x in locations if x.get("country")}) or None,
        "start_date": start.isoformat() if start else None,
        "primary_completion_date": primary.isoformat() if primary else None,
        "study_completion_date": completion.isoformat() if completion else None,
        "accrual_close_date": None,
        "accrual_duration_months": None,
        "duration_upper_bound_months": None,
        "patients_per_site_month": None,
        "patients_per_study_month": None,
        "quality": "ACCRUAL_UNUSABLE",
        "reason": "No actual enrollment close date or explicit accrual duration is available",
        "recruitment_evidence": None,
        "date_precision": None,
    }
    explicit = _recruitment_period(details)
    if count and explicit:
        first, last, quality, excerpt, precision = explicit
        # Reject date pairs incompatible with the recorded study period. Some
        # narratives mention earlier studies or later follow-up dates.
        if (not start or first >= date(start.year - 1, 1, 1)) and (not completion or last <= date(completion.year + 1, 12, 31)):
            months = (last - first).days / 30.4375
            row.update({"quality": quality, "accrual_close_date": last.isoformat(),
                        "accrual_duration_months": months,
                        "patients_per_study_month": count / months,
                        "patients_per_site_month": count / months / sites if sites else None,
                        "recruitment_evidence": excerpt,
                        "date_precision": precision,
                        "reason": "Recruitment or enrollment dates stated in participant-flow narrative"})
            return row
    # Registry completion is an endpoint milestone. It can bound recruitment, but
    # dividing enrollment by that interval would create a false accrual observation.
    if count and start and primary and primary > start:
        row["quality"] = "ACCRUAL_INTERVAL_CENSORED"
        row["duration_upper_bound_months"] = (primary - start).days / 30.4375
        row["reason"] = "Primary completion bounds recruitment but includes endpoint follow-up"
    elif count and start and completion and completion > start:
        row["quality"] = "ACCRUAL_INTERVAL_CENSORED"
        row["duration_upper_bound_months"] = (completion - start).days / 30.4375
        row["reason"] = "Study completion bounds recruitment but includes follow-up"
    else:
        row["duration_upper_bound_months"] = None
    return row


def build(manifest: Path, holdout: Path, raw_dir: Path, out_dir: Path) -> dict:
    source = json.loads(manifest.read_text(encoding="utf-8"))
    excluded = set(json.loads(holdout.read_text(encoding="utf-8"))["nct_ids"])
    rows, missing = [], []
    for item in source["trials"]:
        nct = item["nct_id"]
        if nct in excluded:
            continue
        path = raw_dir / f"{nct}.json"
        if not path.exists():
            missing.append(nct)
            continue
        row = classify(json.loads(path.read_text(encoding="utf-8")))
        if row["nct_id"] != nct:
            raise ValueError(f"Registry ID mismatch in {path}")
        rows.append(row)
    out_dir.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), out_dir / "accrual_evidence.parquet")
    site_rows = [{"nct_id": r["nct_id"], "listed_sites": r["site_count_listed"],
                  "listed_countries": r["country_count_listed"], "patients_per_listed_site_month": r["patients_per_site_month"],
                  "quality": r["quality"], "site_activation_known": False,
                  "site_dropout_known": False, "country_mix_known": bool(r["country_count_listed"])}
                 for r in rows if r["patients_per_site_month"] is not None]
    pq.write_table(pa.Table.from_pylist(site_rows), out_dir / "site_productivity.parquet")
    usable = [r for r in rows if r["quality"] in {"ACCRUAL_DIRECT", "ACCRUAL_DERIVED"}]
    if usable:
        import numpy as np
        rates = np.array([r["patients_per_study_month"] for r in usable], dtype=float)
        benchmark = {"n": len(rates), "median": float(np.median(rates)),
                     "pi80": [float(x) for x in np.quantile(rates, [.1, .9])],
                     "pi95": [float(x) for x in np.quantile(rates, [.025, .975])],
                     "unit": "patients per study month", "source_quality": "explicit registry participant-flow narrative"}
    else:
        benchmark = None
    model = {"status": "BENCHMARK_ONLY" if usable else "UNRESOLVED",
             "reason": "Historical rates are not yet matched by disease, site activation, and phase; no calibrated trial-specific prediction" if usable else
                       "No observed enrollment durations in the available registry records",
             "unadjusted_benchmark": benchmark}
    (out_dir / "accrual_model.json").write_text(json.dumps(model, indent=2), encoding="utf-8")
    summary = {"version": VERSION, "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
               "holdout_sha256": hashlib.sha256(holdout.read_bytes()).hexdigest(),
               "raw_dir": str(raw_dir), "records": len(rows), "missing_raw": missing,
               "excluded_holdout_count": len(excluded), "quality_counts": dict(Counter(r["quality"] for r in rows)),
               "site_rate_candidate_count": len(site_rows),
               "site_rate_caveat": "Listed locations are not verified active sites throughout recruitment; no site-level model fitted",
               "model": model}
    (out_dir / "manifest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
