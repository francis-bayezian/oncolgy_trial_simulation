"""Planning asset 1: historical accrual evidence and an accrual model.

Source: the registry records of the completed trials in the evidence build (holdout trials are never read).

Date quality. The interval from study start to (primary) completion contains follow-up after enrollment
closed, so it overstates the recruitment period and understates the recruitment rate. Every trial is classified:

* ACCRUAL_DIRECT: the registry's recruitment details state the enrollment window (first to last enrollment). The
  window is extracted by a model as verbatim date quotes, parsed deterministically, checked against the registry
  dates, and judged by independent verifier votes (majority);
* ACCRUAL_INTERVAL_CENSORED: no verified window; enrollment closed no later than primary completion, so the rate
  is AT LEAST enrolled / (primary completion - start). It enters the model only as that lower bound;
* ACCRUAL_UNUSABLE: dates or enrollment missing, or the interval is not positive.

Model. log(patients per month) = x'beta + u(disease family) + e, e ~ N(0, sigma^2), with u ~ N(0, tau^2) shrinking
disease families towards the overall mean. DIRECT trials contribute the density, censored trials the probability
of exceeding their bound (Tobit). tau is chosen by cross-validated predictive likelihood on the DIRECT trials; the
same cross-validation gives the calibration (coverage of 50/80/95% intervals).
"""

import datetime as dt
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
from scipy import optimize, stats

from ..protocol import schemas as psc
from ..protocol.compiler import _majority

ACCRUAL_VERSION = "accrual-1.0.0"
MONTH = 30.4375
TEXT = {"type": "string"}
WINDOWS = psc.obj({"windows": {"type": "array", "items": psc.obj({
    "nct_id": TEXT, "window_kind": psc.enum("enrollment_period", "study_conduct_period", "other", "none"),
    "start_quote": TEXT, "end_quote": TEXT, "site_count_quote": TEXT, "reason": TEXT})}})
WINDOWS_INSTRUCTIONS = (
    "Each record is the 'recruitment details' text of a completed clinical trial. For every record return one entry: "
    "window_kind 'enrollment_period' only when the text states when patients were ENROLLED or RECRUITED (first to last "
    "patient enrolled, accrual opened and closed, participants recruited between X and Y); 'study_conduct_period' when "
    "the dates describe the whole study, data collection, follow-up or a data cut-off; 'other' or 'none' otherwise. "
    "start_quote and end_quote are the two dates copied verbatim from the text (only for an enrollment period); "
    "site_count_quote the number of sites, centres or institutions as written ('27 cancer centres'), or ''. reason: one "
    "short sentence."
)
WINDOW_VERIFY = (
    " Here each item states the ENROLLMENT window of a trial read from its recruitment details. Judge FAITHFUL only if "
    "the text states that patients were enrolled or recruited between exactly these dates; INCORRECT if the dates "
    "describe the study, follow-up, a data cut-off, only the first enrollment, or other dates."
)
MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


# ----------------------------------------------------------------------------- dates


def parse_date(text: str | None) -> tuple[dt.date, str] | None:
    """A date as written in free text -> (date, precision 'day' | 'month' | 'year'). Month precision uses the 15th."""
    if not text:
        return None
    t = text.strip().replace(",", " ")
    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t)
    if m:
        return _mk(int(m.group(1)), int(m.group(2)), int(m.group(3)), "day")
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", t)
    if m:
        y = int(m.group(3)) + (2000 if len(m.group(3)) == 2 else 0)
        return _mk(y, int(m.group(1)), int(m.group(2)), "day")
    m = re.search(r"\b(\d{1,2})\s*[-\s]?\s*([A-Za-z]{3,9})\.?\s*[-\s]?\s*((?:19|20)\d{2})\b", t)
    if m and m.group(2)[:3].casefold() in MONTHS:
        return _mk(int(m.group(3)), MONTHS[m.group(2)[:3].casefold()], int(m.group(1)), "day")
    m = re.search(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})?\s*((?:19|20)\d{2})\b", t)
    if m and m.group(1)[:3].casefold() in MONTHS:
        if m.group(2):
            return _mk(int(m.group(3)), MONTHS[m.group(1)[:3].casefold()], int(m.group(2)), "day")
        return _mk(int(m.group(3)), MONTHS[m.group(1)[:3].casefold()], 15, "month")
    m = re.search(r"\b(\d{1,2})/((?:19|20)\d{2})\b", t)
    if m:
        return _mk(int(m.group(2)), int(m.group(1)), 15, "month")
    m = re.fullmatch(r"\s*((?:19|20)\d{2})\s*", t)
    if m:
        return _mk(int(m.group(1)), 7, 1, "year")
    return None


def _mk(y: int, mo: int, d: int, precision: str):
    try:
        return dt.date(y, mo, d), precision
    except ValueError:
        return None


def registry_date(struct: dict | None) -> dt.date | None:
    if not struct or not struct.get("date"):
        return None
    parts = struct["date"].split("-")
    return dt.date(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 15)


# ----------------------------------------------------------------------------- features


def trial_features(record: dict, family_of: dict[str, str]) -> dict:
    ps = record["protocolSection"]
    st, de = ps.get("statusModule", {}), ps.get("designModule", {})
    locs = (ps.get("contactsLocationsModule") or {}).get("locations", [])
    ages = ps.get("eligibilityModule", {}).get("stdAges", [])
    phases = de.get("phases") or []
    info = de.get("designInfo") or {}
    start = registry_date(st.get("startDateStruct"))
    return {
        "nct_id": ps["identificationModule"]["nctId"],
        "enrolled": (de.get("enrollmentInfo") or {}).get("count"),
        "start": start, "primary_completion": registry_date(st.get("primaryCompletionDateStruct")),
        "completion": registry_date(st.get("completionDateStruct")),
        "phase": "+".join(sorted(phases)) or "unknown",
        "randomized": info.get("allocation") == "RANDOMIZED",
        "arms": len(ps.get("armsInterventionsModule", {}).get("armGroups", [])),
        "pediatric": "CHILD" in ages and "OLDER_ADULT" not in ages,
        "listed_sites": len(locs), "countries": len({x.get("country") for x in locs if x.get("country")}),
        "sponsor_class": ps.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("class", "unknown"),
        "disease_family": family_of.get(ps["identificationModule"]["nctId"], "other"),
        "start_year": start.year if start else None,
        "recruitment_details": ((record.get("resultsSection") or {}).get("participantFlowModule") or {}).get("recruitmentDetails"),
    }


def trial_families(family_map_file: Path, database: Path = Path("data/clinical_asset.sqlite")) -> dict[str, str]:
    """Each trial's disease family: the disease recorded for it in the clinical evidence database, mapped through the
    Simulation Parameter Asset's disease-family map (confidence >= 0.7)."""
    import sqlite3
    from collections import Counter

    import pyarrow.parquet as pq

    family = {r["disease"]: r["disease_family"] for r in pq.read_table(family_map_file).to_pylist() if (r.get("confidence") or 0) >= 0.7}
    diseases: dict[str, Counter] = {}
    with sqlite3.connect(database) as con:
        for nct, disease in con.execute("select source_nct, disease from clinical_evidence_profile"):
            if disease in family:
                diseases.setdefault(nct, Counter())[family[disease]] += 1
    return {nct: c.most_common(1)[0][0] for nct, c in diseases.items()}


# ----------------------------------------------------------------------------- window extraction and verification


def extract_windows(model: Any, trials: list[dict], batch: int = 12, votes: int = 3, workers: int = 6) -> dict[str, dict]:
    todo = [t for t in trials if t["recruitment_details"]]
    batches = [todo[i:i + batch] for i in range(0, len(todo), batch)]

    def ask(group):
        payload = {"instructions": WINDOWS_INSTRUCTIONS,
                   "records": [{"nct_id": t["nct_id"], "recruitment_details": t["recruitment_details"]} for t in group]}
        try:
            return model.extract("planning_accrual_windows", WINDOWS, payload).get("windows", [])
        except Exception:  # noqa: BLE001 - a failed batch leaves its trials without a direct window
            return []
    with ThreadPoolExecutor(workers) as pool:
        found = [w for ws in pool.map(ask, batches) for w in ws]
    by_id = {t["nct_id"]: t for t in todo}
    windows = {}
    for w in found:
        t = by_id.get(w["nct_id"])
        if t is None or w["window_kind"] != "enrollment_period":
            continue
        windows[w["nct_id"]] = {**w, **check_window(w, t)}
    _verify(model, windows, by_id, votes, workers)
    return windows


def check_window(w: dict, t: dict) -> dict:
    text = " ".join((t["recruitment_details"] or "").split()).casefold()
    issues = [f"{k} not in the text" for k in ("start_quote", "end_quote") if not w[k] or " ".join(w[k].split()).casefold() not in text]
    a, b = parse_date(w["start_quote"]), parse_date(w["end_quote"])
    if a is None or b is None:
        issues.append("a date could not be parsed")
    else:
        if b[0] <= a[0]:
            issues.append("the window does not end after it starts")
        if t["start"] and a[0] < t["start"] - dt.timedelta(days=365):
            issues.append("the window starts more than a year before the registry start date")
        bound = t["completion"] or t["primary_completion"]
        if bound and b[0] > bound + dt.timedelta(days=31):
            issues.append("the window ends after the study completion date")
    sites = [int(x) for x in re.findall(r"\d+", w.get("site_count_quote") or "")]
    return {"start": a[0].isoformat() if a else None, "end": b[0].isoformat() if b else None,
            "precision": [a[1] if a else None, b[1] if b else None], "site_count": max(sites) if sites else None, "issues": issues}


def _verify(model, windows, by_id, votes, workers, batch: int = 10) -> None:
    ids = sorted(windows)
    jobs = [(ids[i:i + batch], v) for i in range(0, len(ids), batch) for v in range(votes)]

    def run(job):
        group, vote = job
        payload = {"instructions": psc.VERIFY_INSTRUCTIONS + WINDOW_VERIFY, "text": "(each item's evidence is its recruitment details)",
                   "items": [{"item_id": i, "rendering": f"patients were enrolled from {windows[i]['start_quote']!r} to {windows[i]['end_quote']!r}",
                              "evidence": by_id[i]["recruitment_details"], "related": []} for i in group]}
        if vote:
            payload["independent_review"] = f"review {vote + 1} of {votes}: judge from scratch"
        try:
            return model.extract("protocol_verify", psc.VERIFY, payload).get("verdicts", [])
        except Exception:  # noqa: BLE001 - a failed vote counts as no vote
            return []
    with ThreadPoolExecutor(workers) as pool:
        results = [v for vs in pool.map(run, jobs) for v in vs]
    cast: dict[str, list] = {}
    for v in results:
        if v.get("item_id") in windows and v.get("verdict") in {"FAITHFUL", "INCOMPLETE", "INCORRECT", "NOT_A_RULE"}:
            cast.setdefault(v["item_id"], []).append(v)
    for i, w in windows.items():
        m = _majority(cast.get(i, []), votes)
        w["verification"] = {"votes": [x["verdict"] for x in cast.get(i, [])], "reviewer_note": m["reviewer_note"] if m else None}
        w["status"] = "USABLE" if m and m["verdict"] == "FAITHFUL" and not w["issues"] else "REVIEW_REQUIRED"


def classify(t: dict, window: dict | None) -> dict:
    """The accrual observation of one trial and its date quality."""
    n = t["enrolled"]
    if window and window.get("status") == "USABLE" and n:
        months = (dt.date.fromisoformat(window["end"]) - dt.date.fromisoformat(window["start"])).days / MONTH
        if months > 0:
            return {"quality": "ACCRUAL_DIRECT", "months": months, "log_rate": math.log(n / months), "site_count": window.get("site_count")}
    if n and t["start"] and t["primary_completion"]:
        months = (t["primary_completion"] - t["start"]).days / MONTH
        if months > 0:
            return {"quality": "ACCRUAL_INTERVAL_CENSORED", "months_upper": months, "log_rate_lower": math.log(n / months), "site_count": None}
    return {"quality": "ACCRUAL_UNUSABLE"}


# ----------------------------------------------------------------------------- model


def design_matrix(rows: list[dict], levels: dict | None = None, drop: tuple[str, ...] = ()) -> tuple[np.ndarray, list[str], dict]:
    if levels is None:
        levels = {"phase": sorted({r["phase"] for r in rows}), "drop": list(drop)}
    cols = ["intercept", "randomized", "pediatric", "log_sites", "year_centred", "log_enrolled"] + [f"phase={p}" for p in levels["phase"][1:]]
    X = []
    for r in rows:
        sites = r.get("site_count") or r["listed_sites"] or 1
        X.append([1.0, float(r["randomized"]), float(r["pediatric"]), math.log(max(1, sites)), ((r["start_year"] or 2010) - 2010) / 10,
                  math.log(max(1, r["enrolled"] or 1))] + [float(r["phase"] == p) for p in levels["phase"][1:]])
    keep = [i for i, c in enumerate(cols) if c not in levels.get("drop", [])]
    return np.array(X)[:, keep], [cols[i] for i in keep], levels


def fit(rows: list[dict], tau: float, drop: tuple[str, ...] = ()) -> dict:
    X, cols, levels = design_matrix(rows, drop=drop)
    fams = sorted({r["disease_family"] for r in rows})
    fi = np.array([fams.index(r["disease_family"]) for r in rows])
    direct = np.array([r["quality"] == "ACCRUAL_DIRECT" for r in rows])
    y = np.array([r["log_rate"] if r["quality"] == "ACCRUAL_DIRECT" else r["log_rate_lower"] for r in rows])
    k, f = X.shape[1], len(fams)

    def nll(theta):
        beta, u, log_sigma = theta[:k], theta[k:k + f], theta[-1]
        sigma = math.exp(log_sigma)
        mu = X @ beta + u[fi]
        z = (y - mu) / sigma
        ll = np.sum(stats.norm.logpdf(z[direct]) - log_sigma) + np.sum(stats.norm.logsf(z[~direct]))
        prior = -0.5 * np.sum(u ** 2) / tau ** 2 - 0.5 * np.sum(beta[1:] ** 2) / 10.0 ** 2
        return -(ll + prior)
    theta0 = np.zeros(k + f + 1)
    theta0[0] = float(np.mean(y))
    res = optimize.minimize(nll, theta0, method="L-BFGS-B")
    cov = np.linalg.pinv(_hessian(nll, res.x))       # curvature at the optimum (the optimiser's own approximation is poorly scaled)
    return {"beta": res.x[:k].tolist(), "cols": cols, "levels": levels, "families": fams, "u": res.x[k:k + f].tolist(),
            "sigma": float(math.exp(res.x[-1])), "tau": tau, "cov": cov.tolist(), "converged": bool(res.success)}


def _hessian(func, x: np.ndarray, h: float = 1e-4) -> np.ndarray:
    """Central finite-difference Hessian."""
    n = len(x)
    out = np.zeros((n, n))
    for i in range(n):
        for j in range(i, n):
            e_i, e_j = np.eye(n)[i] * h, np.eye(n)[j] * h
            value = (func(x + e_i + e_j) - func(x + e_i - e_j) - func(x - e_i + e_j) + func(x - e_i - e_j)) / (4 * h * h)
            out[i, j] = out[j, i] = value
    return out


def predict(model: dict, row: dict, draws: int = 4000, seed: int = 0) -> dict:
    """Predictive distribution of log(patients/month) for a new trial: parameter uncertainty, disease-family effect
    (or a new-family deviation when the family was not in the data) and the between-trial residual."""
    rng = np.random.default_rng(seed)
    X, _, _ = design_matrix([row], model["levels"])
    k = len(model["beta"])
    mean = np.array(model["beta"] + model["u"] + [math.log(model["sigma"])])
    cov = np.array(model["cov"])
    theta = rng.multivariate_normal(mean, (cov + cov.T) / 2 + 1e-9 * np.eye(len(mean)), size=draws, method="eigh")
    beta = theta[:, :k]
    fam = row["disease_family"]
    u = theta[:, k + model["families"].index(fam)] if fam in model["families"] else rng.normal(0, model["tau"], draws)
    sigma = np.exp(theta[:, -1])
    return {"log_rate": (beta @ X[0]) + u + rng.normal(0, 1, draws) * sigma, "family_known": fam in model["families"]}


def cross_validate(rows: list[dict], tau: float, folds: int = 10, seed: int = 0, drop: tuple[str, ...] = ()) -> dict:
    """Out-of-fold predictive checks on the DIRECT trials: log predictive density and interval coverage."""
    rng = np.random.default_rng(seed)
    idx = [i for i, r in enumerate(rows) if r["quality"] == "ACCRUAL_DIRECT"]
    order = rng.permutation(idx)
    lpd, cover, errs = [], {0.5: [], 0.8: [], 0.95: []}, []
    for f in range(folds):
        test = set(order[f::folds].tolist())
        model = fit([r for i, r in enumerate(rows) if i not in test], tau, drop)
        for i in test:
            d = predict(model, rows[i], draws=2000, seed=i)["log_rate"]
            obs = rows[i]["log_rate"]
            lpd.append(float(stats.norm.logpdf(obs, d.mean(), d.std())))
            errs.append(abs(math.exp(float(np.median(d))) - math.exp(obs)) / math.exp(obs))
            for level, hits in cover.items():
                lo, hi = np.quantile(d, [(1 - level) / 2, 1 - (1 - level) / 2])
                hits.append(lo <= obs <= hi)
    return {"tau": tau, "direct_trials": len(idx), "mean_log_predictive_density": float(np.mean(lpd)),
            "coverage": {str(k): float(np.mean(v)) for k, v in cover.items()}, "median_relative_error_rate": float(np.median(errs))}


# ----------------------------------------------------------------------------- build


def build(model_client: Any, raw_dir: Path, holdout_file: Path, family_map_file: Path, out_dir: Path, created: str) -> dict:
    import pyarrow as pa
    import pyarrow.parquet as pq

    holdout = set(json.loads(Path(holdout_file).read_text(encoding="utf-8"))["nct_ids"])
    family_of = trial_families(family_map_file)
    trials = []
    for f in sorted(Path(raw_dir).glob("*.json")):
        if f.stem in holdout:
            continue
        trials.append(trial_features(json.loads(f.read_text(encoding="utf-8")), family_of))
    windows = extract_windows(model_client, trials)
    rows = []
    for t in trials:
        obs = classify(t, windows.get(t["nct_id"]))
        rows.append({**{k: v for k, v in t.items() if k != "recruitment_details"}, **obs})
    usable = [r for r in rows if r["quality"] != "ACCRUAL_UNUSABLE"]
    direct_rows = [r for r in usable if r["quality"] == "ACCRUAL_DIRECT"]
    censored_rows = [r for r in usable if r["quality"] == "ACCRUAL_INTERVAL_CENSORED"]
    # The predictive model uses the DIRECT trials only: pooling the censored trials under a shared distribution biased the
    # predictions for direct trials (checked below). The censored bounds are a consistency check on the direct model.
    cv = [cross_validate(direct_rows, tau) for tau in (0.1, 0.25, 0.5, 1.0)]
    best = max(cv, key=lambda c: c["mean_log_predictive_density"])
    model = fit(direct_rows, best["tau"])
    pooled = fit(usable, best["tau"])
    pooled_bias = float(np.mean([r["log_rate"] - np.median(predict(pooled, r, draws=400, seed=1)["log_rate"]) for r in direct_rows]))
    bound_quantiles = np.array([np.mean(predict(model, r, draws=400, seed=i)["log_rate"] <= r["log_rate_lower"]) for i, r in enumerate(censored_rows)])
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    keys = list(dict.fromkeys(k for r in rows for k in r))          # every row gets every column (direct and censored differ)
    table = [{k: (r.get(k).isoformat() if isinstance(r.get(k), dt.date) else r.get(k)) for k in keys} for r in rows]
    pq.write_table(pa.Table.from_pylist(table), out_dir / "study_level_rates.parquet")
    (out_dir / "windows.json").write_text(json.dumps(windows, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    counts = {q: sum(r["quality"] == q for r in rows) for q in ("ACCRUAL_DIRECT", "ACCRUAL_INTERVAL_CENSORED", "ACCRUAL_UNUSABLE")}
    direct = [r for r in rows if r["quality"] == "ACCRUAL_DIRECT"]
    naive_vs_direct = [math.exp(r["log_rate"]) / (r["enrolled"] / ((r["primary_completion"] - r["start"]).days / MONTH))
                       for r in direct if r["start"] and r["primary_completion"] and (r["primary_completion"] - r["start"]).days > 0]
    manifest = {"accrual_version": ACCRUAL_VERSION, "created": created, "trials": len(rows), "holdout_excluded": len(holdout),
                "quality_counts": counts, "windows_extracted": len(windows), "windows_usable": sum(w["status"] == "USABLE" for w in windows.values()),
                "naive_rate_underestimate_factor_median": float(np.median(naive_vs_direct)) if naive_vs_direct else None,
                "cross_validation": cv, "selected_tau": best["tau"], "fitted_on": "ACCRUAL_DIRECT trials only",
                "censored_consistency_check": {"trials": len(censored_rows), "mean_predictive_quantile_of_lower_bound": float(bound_quantiles.mean()),
                                               "share_of_bounds_above_predictive_median": float(np.mean(bound_quantiles > 0.5)),
                                               "share_of_bounds_above_predictive_90th": float(np.mean(bound_quantiles > 0.9)),
                                               "interpretation": "a lower bound lies below the true rate: most bounds should fall below the predictive median"},
                "pooled_censored_model_rejected": {"mean_log_residual_on_direct_trials": pooled_bias,
                                                   "reason": "pooling censored trials under one distribution shifted predictions for direct trials"},
                "model": {k: model[k] for k in ("cols", "beta", "families", "u", "sigma", "tau", "converged")}}
    (out_dir / "accrual_model.json").write_text(json.dumps({**model, "manifest": manifest}, indent=1), encoding="utf-8")
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest
