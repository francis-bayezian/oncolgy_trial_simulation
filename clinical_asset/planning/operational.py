"""Planning asset 1, version 2: operational trial evidence including stopped trials.

V1 was built from completed trials with results and a results publication. Those are the trials that recruited: the
rate model was optimistic, and it had no notion of a trial failing to recruit. V2 adds, under the same base criteria
(interventional, neoplasm condition, treatment purpose, phase 2 or 3), the trials that stopped:

Corpus. ClinicalTrials.gov API v2, light fields only, statuses COMPLETED, TERMINATED, WITHDRAWN and SUSPENDED.
Holdout trials (the holdout manifest, the sealed blind-test trials and every trial whose registry record the pipeline
compares against) are dropped before anything is computed. Disease family: each MeSH condition term is mapped by the
evidence build's disease mapper (the taxonomy that built the disease-family map).

Failure model. Outcome of a trial, from its registry status and stated reason for stopping:
  completed | terminated_accrual | terminated_other | withdrawn
(SUSPENDED is not final and is excluded). The reason is classed as accrual-related by an explicit pattern over the
registry's own free text (accrual, enrollment, recruitment, too few patients); the pattern and a sample of both
classes are written to the manifest. Covariates are only those known when a trial is planned: phase, randomization,
paediatric population, start year, lead-sponsor class, number of arms, disease family. Enrollment and site counts are
excluded: the registry reports what happened (a withdrawn trial lists no sites and enrolls nobody). Multinomial
logistic regression with a Gaussian prior (ridge) on every non-intercept coefficient; calibration by cross-validation.

Rate model. As V1 (log patients/month, verified enrollment windows from the recruitment details, fitted on the
ACCRUAL_DIRECT trials, disease-family shrinkage), now also on terminated trials that report results. The planned
enrollment of a stopped trial is not in the registry record (only the actual count), so log(enrolled) is dropped as
a covariate: it would be the planned size for completed trials and the shortfall for stopped ones.
"""

import datetime as dt
import json
import math
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from scipy import optimize

from . import accrual as ac

OPERATIONAL_VERSION = "operational-2.0.0"
API = "https://clinicaltrials.gov/api/v2/studies"
BASE_QUERY = ("AREA[StudyType]INTERVENTIONAL AND (AREA[ConditionMeshTerm]Neoplasms OR AREA[ConditionAncestorTerm]Neoplasms) "
              "AND AREA[DesignPrimaryPurpose]TREATMENT AND (AREA[Phase]PHASE2 OR AREA[Phase]PHASE3)")
STATUSES = ("COMPLETED", "TERMINATED", "WITHDRAWN", "SUSPENDED")
FIELDS = ("NCTId,OverallStatus,WhyStopped,StartDate,PrimaryCompletionDate,CompletionDate,EnrollmentCount,EnrollmentType,Phase,"
          "DesignAllocation,StdAge,LocationCountry,LeadSponsorClass,Condition,ConditionMeshTerm,HasResults,FlowRecruitmentDetails,"
          "ArmGroupLabel,ReferenceType")
OUTCOMES = ("completed", "terminated_accrual", "terminated_other", "withdrawn")
# accrual-related reasons for stopping, as registries word them (operational words, no medical vocabulary)
ACCRUAL_REASON = re.compile(
    r"accru|enrol|recruit|"
    r"\b(lack|shortage|insufficient|inadequate|low|poor|slow|limited|few|no)\b\W+(?:\w+\W+){0,3}?(patients?|participants?|subjects?|eligible|volunteers?)\b",
    re.IGNORECASE)
# standard phrases that report THAT enrollment stopped, not WHY (removed before the reason is classed)
STOPPED_PHRASE = re.compile(r"clos\w*\s+(?:\w+\s+){0,2}?to\s+(?:new\s+|further\s+)?(?:patient\s+)?(?:enrol\w*|accrual|recruitment|entry)"
                            r"|(?:enrol\w*|accrual|recruitment)\s+(?:was\s+|is\s+|has\s+been\s+)?(?:completed?|finished|ended|stopped|halted|closed)"
                            r"|(?:stop\w*|halt\w*|suspend\w*|end\w*)\s+(?:\w+\s+){0,2}?(?:enrol\w*|accrual|recruitment)", re.IGNORECASE)


# ----------------------------------------------------------------------------- corpus


def fetch_corpus(out_dir: Path, retrieved: str, page_size: int = 1000) -> dict:
    import requests

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": "ClinicalEvidenceAsset/0.1 (research)"})
    counts = {}
    with open(out_dir / "corpus.jsonl", "w", encoding="utf-8") as fh:
        for status in STATUSES:
            token, n = None, 0
            while True:
                params = {"query.term": f"{BASE_QUERY} AND AREA[OverallStatus]{status}", "fields": FIELDS, "pageSize": page_size}
                if token:
                    params["pageToken"] = token
                for attempt in range(4):
                    r = session.get(API, params=params, timeout=120)
                    if r.status_code == 200:
                        break
                    time.sleep(2 ** attempt)
                r.raise_for_status()
                page = r.json()
                for s in page.get("studies", []):
                    fh.write(json.dumps(s, ensure_ascii=False) + "\n")
                    n += 1
                token = page.get("nextPageToken")
                if not token:
                    break
            counts[status] = n
    manifest = {"retrieved": retrieved, "query": BASE_QUERY, "statuses": counts, "fields": FIELDS.split(",")}
    (out_dir / "corpus_manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


BLIND_HOLDOUT = Path("data/manifest/blind_holdout.json")


def holdout_ids(holdout_file: Path, compared_dir: Path = Path("data/holdout_comparison"), blind_file: Path = BLIND_HOLDOUT) -> set[str]:
    """Trials never read by an asset: the holdout manifest, every trial the pipeline compares against, and the sealed
    blind-test trials."""
    ids = set(json.loads(Path(holdout_file).read_text(encoding="utf-8"))["nct_ids"])
    blind = set(json.loads(Path(blind_file).read_text(encoding="utf-8"))["nct_ids"]) if Path(blind_file).exists() else set()
    return ids | blind | {p.stem for p in Path(compared_dir).glob("NCT*.json")}


FUNCTION_WORDS = frozenset(["with", "without", "from", "that", "this", "than", "into", "onto", "over", "under", "upon", "other", "others", "such", "their", "there", "these", "those", "were", "been", "being", "have", "having", "what", "when", "where", "which", "while", "whom", "whose", "will", "would", "also", "only", "both", "each", "more", "most", "very"])


def family_matcher(family_map_file: Path):
    """Disease family of a trial from its condition text. Each word (4+ letters, English function words excluded) of the
    family map's disease names is weighted by how specific it is to one family: log(families / families using the word),
    so 'lymphoma' weighs much and 'carcinoma' (used by many families) little. The trial takes the family with the largest
    summed weight of shared words; no shared weighted word, or a tie between families, is 'other'. The matched disease is
    that family's disease name sharing the most weight."""
    import pyarrow.parquet as pq

    def words_of(text: str) -> set[str]:
        return {w for w in re.findall(r"[a-z]{4,}", (text or "").casefold()) if w not in FUNCTION_WORDS}

    rows = [r for r in pq.read_table(family_map_file).to_pylist() if (r.get("confidence") or 0) >= 0.7 and r["disease_family"] != "other"]
    table = [(words_of(r["disease"]), r["disease_family"], r["disease"]) for r in rows]
    fam_words: dict[str, set[str]] = {}
    for ws, fam, _n in table:
        fam_words.setdefault(fam, set()).update(ws)
    nf = len(fam_words)
    used: dict[str, int] = {}
    for ws in fam_words.values():
        for w in ws:
            used[w] = used.get(w, 0) + 1
    weight = {w: math.log(nf / c) for w, c in used.items()}

    def match(text: str) -> tuple[str, str | None]:
        words = words_of(text)
        scores = sorted(((sum(weight[w] for w in words & ws), fam) for fam, ws in fam_words.items()), reverse=True)
        if not scores or scores[0][0] <= 0 or (len(scores) > 1 and abs(scores[0][0] - scores[1][0]) < 1e-9):
            return ("other", None)
        fam = scores[0][1]
        name = max(((sum(weight[w] for w in words & ws), n) for ws, f, n in table if f == fam), key=lambda x: x[0])[1]
        return (fam, name)
    return match


def features(study: dict, mesh_map: dict) -> dict:
    ps = study["protocolSection"]
    st = ps.get("statusModule", {})
    meshes = ((study.get("derivedSection") or {}).get("conditionBrowseModule") or {}).get("meshes", [])
    family, disease = family_of_terms([m["term"] for m in meshes], mesh_map)
    refs = (ps.get("referencesModule") or {}).get("references", [])
    t = ac.trial_features(study, {})
    t.update({"status": st.get("overallStatus"), "why_stopped": st.get("whyStopped"), "enrollment_type": (ps.get("designModule", {}).get("enrollmentInfo") or {}).get("type"),
              "has_results": bool(study.get("hasResults")), "result_publication": any(r.get("type") == "RESULT" for r in refs),
              "disease_family": family, "matched_disease": disease})
    return t


def accrual_reason(text: str | None) -> bool:
    return bool(ACCRUAL_REASON.search(STOPPED_PHRASE.sub(" ", text or "")))


def outcome(t: dict) -> str | None:
    if t["status"] == "COMPLETED":
        return "completed"
    if t["status"] == "WITHDRAWN":
        return "withdrawn"
    if t["status"] == "TERMINATED":
        return "terminated_accrual" if accrual_reason(t.get("why_stopped")) else "terminated_other"
    return None                                               # SUSPENDED: not final


# ----------------------------------------------------------------------------- failure model


SPONSORS = ("INDUSTRY", "NIH", "NETWORK", "OTHER_GOV", "OTHER")


def failure_matrix(rows: list[dict], levels: dict | None = None) -> tuple[np.ndarray, list[str], dict]:
    if levels is None:
        phases = sorted({r["phase"] for r in rows})
        fams = sorted({r["disease_family"] for r in rows})
        levels = {"phase": phases, "family": fams}
    cols = (["intercept", "randomized", "pediatric", "year_centred", "log_arms"] + [f"phase={p}" for p in levels["phase"][1:]]
            + [f"sponsor={s}" for s in SPONSORS[1:]] + [f"family={f}" for f in levels["family"]])
    X = []
    for r in rows:
        sponsor = r["sponsor_class"] if r["sponsor_class"] in SPONSORS else "OTHER"
        X.append([1.0, float(r["randomized"]), float(r["pediatric"]), ((r["start_year"] or 2010) - 2010) / 10, math.log(max(1, r["arms"] or 1))]
                 + [float(r["phase"] == p) for p in levels["phase"][1:]] + [float(sponsor == s) for s in SPONSORS[1:]]
                 + [float(r["disease_family"] == f) for f in levels["family"]])
    return np.array(X), cols, levels


def fit_failure(rows: list[dict], prior_sd: float = 1.0, family_prior_sd: float = 0.5) -> dict:
    X, cols, levels = failure_matrix(rows)
    y = np.array([OUTCOMES.index(r["outcome"]) for r in rows])
    n, k = X.shape
    m = len(OUTCOMES) - 1                                     # 'completed' is the reference class
    sd = np.array([np.inf] + [family_prior_sd if c.startswith("family=") else prior_sd for c in cols[1:]])
    Y = np.zeros((n, m + 1))
    Y[np.arange(n), y] = 1

    def f(theta):
        B = theta.reshape(k, m)
        eta = np.hstack([np.zeros((n, 1)), X @ B])
        eta -= eta.max(axis=1, keepdims=True)
        logp = eta - np.log(np.exp(eta).sum(axis=1, keepdims=True))
        p = np.exp(logp)
        nll = -(Y * logp).sum() + 0.5 * ((B / sd[:, None]) ** 2).sum()
        grad = X.T @ (p - Y)[:, 1:] + B / sd[:, None] ** 2
        return nll, grad.ravel()
    res = optimize.minimize(f, np.zeros(k * m), jac=True, method="L-BFGS-B", options={"maxiter": 2000})
    return {"cols": cols, "levels": levels, "outcomes": list(OUTCOMES), "coef": res.x.reshape(k, m).tolist(), "converged": bool(res.success),
            "prior_sd": prior_sd, "family_prior_sd": family_prior_sd}


def predict_failure(model: dict, rows: list[dict]) -> np.ndarray:
    X, _, _ = failure_matrix(rows, model["levels"])
    eta = np.hstack([np.zeros((len(rows), 1)), X @ np.array(model["coef"])])
    eta -= eta.max(axis=1, keepdims=True)
    p = np.exp(eta)
    return p / p.sum(axis=1, keepdims=True)


def cross_validate_failure(rows: list[dict], folds: int = 5, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(rows))
    P = np.zeros((len(rows), len(OUTCOMES)))
    for f in range(folds):
        test = order[f::folds]
        train = np.setdiff1d(order, test)
        model = fit_failure([rows[i] for i in train])
        P[test] = predict_failure(model, [rows[i] for i in test])
    y = np.array([OUTCOMES.index(r["outcome"]) for r in rows])
    base = np.bincount(y, minlength=len(OUTCOMES)) / len(y)
    logloss = float(-np.mean(np.log(P[np.arange(len(y)), y])))
    base_logloss = float(-np.mean(np.log(base[y])))
    fail = np.isin(y, [OUTCOMES.index("terminated_accrual"), OUTCOMES.index("withdrawn")])
    pf = P[:, OUTCOMES.index("terminated_accrual")] + P[:, OUTCOMES.index("withdrawn")]
    from scipy.stats import rankdata
    ranks = rankdata(pf)
    auc = float((ranks[fail].sum() - fail.sum() * (fail.sum() + 1) / 2) / (fail.sum() * (~fail).sum())) if fail.any() and (~fail).any() else None
    bins = np.quantile(pf, np.linspace(0, 1, 11))
    idx = np.clip(np.searchsorted(bins, pf, side="right") - 1, 0, 9)
    reliability = [{"decile": d + 1, "predicted": float(pf[idx == d].mean()), "observed": float(fail[idx == d].mean()), "n": int((idx == d).sum())}
                   for d in range(10) if (idx == d).any()]
    return {"folds": folds, "trials": len(rows), "log_loss": logloss, "base_rate_log_loss": base_logloss,
            "accrual_failure_auc": auc, "accrual_failure_reliability": reliability, "base_rates": dict(zip(OUTCOMES, base.tolist(), strict=True))}


# ----------------------------------------------------------------------------- rate model (V1 method, stopped trials added, no log_enrolled)


DROP = ("log_enrolled",)


def build(model_client: Any, corpus_dir: Path, v1_windows: Path, holdout_file: Path, family_map_file: Path, out_dir: Path,
          created: str, start_year_min: int = 2000) -> dict:
    import pyarrow as pa
    import pyarrow.parquet as pq

    hold = holdout_ids(holdout_file)
    match = map_corpus_mesh(model_client, Path(corpus_dir) / "corpus.jsonl")
    trials = []
    with open(Path(corpus_dir) / "corpus.jsonl", encoding="utf-8") as fh:
        for line in fh:
            s = json.loads(line)
            if s["protocolSection"]["identificationModule"]["nctId"] in hold:
                continue
            trials.append(features(s, match))
    held_out = len(hold)

    # failure model: final statuses, planned-at-start covariates
    frows = [{**t, "outcome": outcome(t)} for t in trials if outcome(t) and t["start_year"] and t["start_year"] >= start_year_min]
    failure = fit_failure(frows)
    failure_cv = cross_validate_failure(frows)
    stopped = [t for t in trials if t["status"] == "TERMINATED"]
    audit = {"pattern": ACCRUAL_REASON.pattern,
             "accrual_examples": [t["why_stopped"] for t in stopped if outcome(t) == "terminated_accrual"][:25],
             "other_examples": [t["why_stopped"] for t in stopped if outcome(t) == "terminated_other"][:25],
             "terminated_without_reason": sum(not t["why_stopped"] for t in stopped)}

    # rate model: completed trials under the V1 criteria (results + results publication) and terminated trials with results
    rate_trials = [t for t in trials if (t["status"] == "COMPLETED" and t["has_results"] and t["result_publication"])
                   or (t["status"] == "TERMINATED" and t["has_results"])]
    old = json.loads(Path(v1_windows).read_text(encoding="utf-8")) if v1_windows and Path(v1_windows).exists() else {}
    new = [t for t in rate_trials if t["nct_id"] not in old and t["recruitment_details"] and re.search(r"(?:19|20)\d{2}", t["recruitment_details"])]
    windows = {k: v for k, v in old.items()}
    windows.update(ac.extract_windows(model_client, new) if new else {})
    rows = []
    for t in rate_trials:
        obs = ac.classify(t, windows.get(t["nct_id"]))
        rows.append({**{k: v for k, v in t.items() if k != "recruitment_details"}, **obs})
    direct = [r for r in rows if r["quality"] == "ACCRUAL_DIRECT"]
    cv = [ac.cross_validate(direct, tau, drop=DROP) for tau in (0.1, 0.25, 0.5, 1.0)]
    best = max(cv, key=lambda c: c["mean_log_predictive_density"])
    model = ac.fit(direct, best["tau"], DROP)
    v1_style = ac.cross_validate([r for r in direct if r["status"] == "COMPLETED"], best["tau"])      # V1 covariates, completed only
    by_status = {}
    for status in ("COMPLETED", "TERMINATED"):
        sub = [r for r in direct if r["status"] == status]
        if sub:            # in-sample predictive quantile of each observed rate, by status (a check of the tails)
            q = np.array([float(np.mean(ac.predict(model, r, draws=400, seed=i)["log_rate"] <= r["log_rate"])) for i, r in enumerate(sub)])
            by_status[status] = {"direct_trials": len(sub), "mean_predictive_quantile": float(q.mean()),
                                 "share_below_10th": float(np.mean(q < 0.1)), "share_above_90th": float(np.mean(q > 0.9))}

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    keys = list(dict.fromkeys(k for r in rows for k in r))
    table = [{k: (r.get(k).isoformat() if isinstance(r.get(k), dt.date) else r.get(k)) for k in keys} for r in rows]
    pq.write_table(pa.Table.from_pylist(table), out_dir / "study_level_rates.parquet")
    ftable = [{k: (r.get(k).isoformat() if isinstance(r.get(k), dt.date) else r.get(k)) for k in
               ("nct_id", "status", "outcome", "why_stopped", "phase", "randomized", "pediatric", "start_year", "sponsor_class", "arms", "disease_family", "matched_disease")}
              for r in frows]
    pq.write_table(pa.Table.from_pylist(ftable), out_dir / "trial_outcomes.parquet")
    (out_dir / "windows.json").write_text(json.dumps(windows, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    counts = {q: sum(r["quality"] == q for r in rows) for q in ("ACCRUAL_DIRECT", "ACCRUAL_INTERVAL_CENSORED", "ACCRUAL_UNUSABLE")}
    manifest = {"operational_version": OPERATIONAL_VERSION, "created": created, "corpus": json.loads((Path(corpus_dir) / "corpus_manifest.json").read_text(encoding="utf-8")),
                "holdout_excluded_ids": held_out,
                "failure_model": {"trials": len(frows), "start_year_min": start_year_min, "outcome_counts": {o: sum(r["outcome"] == o for r in frows) for o in OUTCOMES},
                                  "cross_validation": failure_cv, "reason_classification": audit, "converged": failure["converged"]},
                "rate_model": {"trials": len(rows), "quality_counts": counts,
                               "direct_by_status": {s: sum(r["status"] == s for r in direct) for s in ("COMPLETED", "TERMINATED")},
                               "windows_reused_from_v1": sum(1 for r in rows if r["nct_id"] in old), "windows_extracted_new": len(new),
                               "cross_validation": cv, "selected_tau": best["tau"], "calibration_by_status": by_status,
                               "v1_style_cross_validation_completed_only": v1_style,
                               "fitted_on": "ACCRUAL_DIRECT trials (completed and terminated)", "covariates": model["cols"]}}
    (out_dir / "accrual_model.json").write_text(json.dumps({**model, "manifest": manifest}, indent=1), encoding="utf-8")
    (out_dir / "failure_model.json").write_text(json.dumps(failure, indent=1), encoding="utf-8")
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1, default=str), encoding="utf-8")
    return manifest


# ----------------------------------------------------------------------------- disease family by the evidence build's mapper

MESH_FAMILIES = Path("data/spa_work/mesh_disease_families.json")
CONDITION_FAMILIES = Path("data/spa_work/condition_disease_families.json")
MIN_FAMILY_CONFIDENCE = 0.7


def _mapped(model, items: list[str], cache_file: Path) -> dict:
    """Disease families of terms, by the same mapper (taxonomy and instructions) that built the disease-family map;
    cached, so each term is mapped once."""
    from ..spa2.taxonomy import map_diseases

    cache = json.loads(Path(cache_file).read_text(encoding="utf-8")) if Path(cache_file).exists() else {}
    todo = sorted({t for t in items if t and t not in cache})
    if todo and model is not None:
        cache.update(map_diseases(model, [{"item": t} for t in todo]))
        Path(cache_file).parent.mkdir(parents=True, exist_ok=True)
        Path(cache_file).write_text(json.dumps(cache, indent=1, ensure_ascii=False), encoding="utf-8")
    return cache


def map_corpus_mesh(model, corpus_file: Path, cache_file: Path = MESH_FAMILIES) -> dict:
    terms = set()
    with open(corpus_file, encoding="utf-8") as fh:
        for line in fh:
            s = json.loads(line)
            terms.update(m["term"] for m in ((s.get("derivedSection") or {}).get("conditionBrowseModule") or {}).get("meshes", []))
    return _mapped(model, sorted(terms), cache_file)


def family_of_terms(terms: list[str], mapping: dict) -> tuple[str, str | None]:
    """A trial's disease family from its condition terms: the most frequent specific family among terms mapped with
    confidence >= 0.7 ('mixed_*' only when no specific family is found); a tie between families is 'other'."""
    fams = [mapping[t]["label"] for t in terms if t in mapping and (mapping[t].get("confidence") or 0) >= MIN_FAMILY_CONFIDENCE]
    specific = [f for f in fams if f != "other" and not f.startswith("mixed_")]
    pool = specific or [f for f in fams if f.startswith("mixed_")]
    if not pool:
        return ("other", None)
    counts = Counter(pool).most_common()
    if len(counts) > 1 and counts[0][1] == counts[1][1]:
        return ("other", None)
    fam = counts[0][0]
    return (fam, next(t for t in terms if t in mapping and mapping[t]["label"] == fam))


def condition_family(condition: str, model=None, cache_file: Path = CONDITION_FAMILIES) -> tuple[str, str | None]:
    """A protocol's disease family from its condition text, by the same mapper (mapped once and cached)."""
    mapping = _mapped(model, [condition], cache_file)
    if condition not in mapping:
        return ("other", None)
    return family_of_terms([condition], mapping)
