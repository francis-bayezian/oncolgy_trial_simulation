"""Milestone 2C: adverse-event rates with the registry reporting mechanism modelled.

ClinicalTrials.gov lists non-serious ("other") adverse events only above a per-study frequency
threshold q (percent of participants in a group). So for a study whose non-serious table does
not list an event, the information is Y <= floor(q * N / 100): left-censored, never Y = 0.
Serious adverse events must all be reported, so an unlisted serious term in a study with a
serious-event table is an exact zero. The two are modelled separately.

Model per (event, seriousness, treatment-class context): beta-binomial with exact and censored
likelihood terms on an exact grid; regimen estimates borrow from that class population through
importance weighting of the class hyperposterior.
"""

import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy import special, stats

from ..registry import parse_study
from ..terminology import FINDING_TYPES, Terminology

LOGIT = np.linspace(-12, 12, 73)
LOGK = np.linspace(np.log(0.05), np.log(1e5), 49)


def study_event_tables(raw_dir: Path, arms: dict[tuple, dict], terminology: Terminology) -> tuple[list[dict], list[dict]]:
    """Per arm and term: exact counts from the full registry tables, plus reporting metadata."""
    observations, thresholds = [], []
    ncts = sorted({nct for nct, _ in arms})
    key_cache: dict[str, str] = {}
    for nct in ncts:
        path = raw_dir / f"{nct}.json"
        if not path.exists():
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        ae = raw.get("resultsSection", {}).get("adverseEventsModule", {})
        threshold = ae.get("frequencyThreshold")
        try:
            threshold = float(threshold) if threshold is not None else None
        except ValueError:
            threshold = None
        has_other = bool(ae.get("otherEvents"))
        has_serious = bool(ae.get("seriousEvents"))
        thresholds.append({"nct_id": nct, "report_threshold": threshold, "threshold_unit": "percent_of_participants",
                           "threshold_scope": "any reporting group", "non_serious_table": has_other,
                           "serious_table": has_serious})
        parsed = parse_study(raw)
        for profile in parsed.profiles:
            arm = (nct, profile.source_arm)
            if arm not in arms or profile.source_population != "treatment_arm_aggregate":
                continue
            for source, seriousness in (("non_serious_terms", "non_serious"), ("serious_terms", "serious")):
                for item in profile.toxicity.get(source, []):
                    term = str(item["term"])
                    if term not in key_cache:
                        concept = terminology.link(term, FINDING_TYPES)
                        key_cache[term] = concept.key if concept else term.casefold().replace(" ", "_")
                    observations.append({"nct_id": nct, "arm": arm, "event": key_cache[term], "seriousness": seriousness,
                                         "y": int(item["n"]), "n": int(item["N"]), "threshold": threshold,
                                         "has_table": has_other if seriousness == "non_serious" else has_serious})
    return observations, thresholds


def _loglik_grid(exact: list[tuple[int, int]], censored: list[tuple[int, int]]) -> np.ndarray:
    lm, lk = np.meshgrid(LOGIT, LOGK, indexing="ij")
    m, k = special.expit(lm), np.exp(lk)
    a, b = m * k, (1 - m) * k
    total = np.zeros_like(a)
    # Identical (count, N) pairs contribute identical terms: compute once, weight by multiplicity.
    for (y, n), times in Counter(exact).items():
        total += times * (special.betaln(y + a, n - y + b) - special.betaln(a, b) + special.gammaln(n + 1)
                          - special.gammaln(y + 1) - special.gammaln(n - y + 1))
    for (c, n), times in Counter(censored).items():
        ys = np.arange(c + 1)
        terms = (special.betaln(ys[None, None, :] + a[..., None], n - ys[None, None, :] + b[..., None]) - special.betaln(a, b)[..., None]
                 + special.gammaln(n + 1) - special.gammaln(ys + 1) - special.gammaln(n - ys + 1))
        total += times * special.logsumexp(terms, axis=-1)
    return total


def fit_censored(exact: list[tuple[int, int]], censored: list[tuple[int, int]], seed: int, draws: int = 1000) -> dict:
    lm, lk = np.meshgrid(LOGIT, LOGK, indexing="ij")
    log_post = _loglik_grid(exact, censored) - 0.5 * (lm / 1.5) ** 2 - 0.5 * ((lk - np.log(10)) / 1.5) ** 2
    w = np.exp(log_post - log_post.max())
    w /= w.sum()
    edge = float(w[0, :].sum() + w[-1, :].sum() + w[:, 0].sum() + w[:, -1].sum())
    rng = np.random.default_rng(seed)
    idx = rng.choice(w.size, size=draws, p=w.ravel())
    i, j = np.unravel_index(idx, w.shape)
    m = special.expit(LOGIT[i] + rng.uniform(-0.1, 0.1, draws))
    k = np.exp(LOGK[j] + rng.uniform(-0.12, 0.12, draws))
    return {"m": m, "k": k, "edge": edge, "new_study": rng.beta(m * k, (1 - m) * k)}


def regimen_posterior(class_fit: dict, exact: list[tuple[int, int]], censored: list[tuple[int, int]], seed: int) -> np.ndarray:
    """p for one regimen: prior = class population Beta(m k, (1-m) k) per hyperdraw, weighted by this
    regimen's own exact and censored observations."""
    rng = np.random.default_rng(seed)
    m, k = np.repeat(class_fit["m"], 20), np.repeat(class_fit["k"], 20)
    p = np.clip(rng.beta(m * k, (1 - m) * k), 1e-9, 1 - 1e-9)
    logw = np.zeros_like(p)
    for y, n in exact:
        logw += y * np.log(p) + (n - y) * np.log1p(-p)
    for c, n in censored:
        logw += stats.binom.logcdf(c, n, p)
    w = np.exp(logw - logw.max())
    w /= w.sum()
    return p[rng.choice(p.size, size=1000, p=w)]


def build_contexts(observations: list[dict], arm_context: dict[tuple, dict], min_studies: int = 3) -> dict[tuple, dict]:
    """(event, seriousness, class_signature) -> per-arm exact or censored observations."""
    listed = defaultdict(set)
    for o in observations:
        listed[(o["event"], o["seriousness"])].add(o["nct_id"])
    common = {key for key, studies in listed.items() if len(studies) >= min_studies}
    arms_by_class: dict[str, set] = defaultdict(set)
    for arm, ctx in arm_context.items():
        arms_by_class[ctx["class_signature"]].add(arm)
    by_arm_event = {(o["arm"], o["event"], o["seriousness"]): o for o in observations}
    arm_meta = {}
    for o in observations:
        arm_meta.setdefault((o["arm"], o["seriousness"]), o)
    contexts: dict[tuple, dict] = {}
    for event, seriousness in common:
        classes = {arm_context[a]["class_signature"] for a in arm_context
                   if (a, event, seriousness) in by_arm_event}
        for cls in classes:
            exact, censored = [], []
            for arm in arms_by_class[cls]:
                obs = by_arm_event.get((arm, event, seriousness))
                meta = arm_meta.get((arm, seriousness))
                if obs is not None:
                    exact.append((arm, obs["y"], obs["n"]))
                elif meta is not None and meta["has_table"]:
                    n = meta["n"]
                    if seriousness == "serious":
                        exact.append((arm, 0, n))  # all serious events are reported
                    elif meta["threshold"] is not None:
                        censored.append((arm, math.floor(meta["threshold"] * n / 100 + 1e-9), n))
            if exact:
                contexts[(event, seriousness, cls)] = {"exact": exact, "censored": censored}
    return contexts
