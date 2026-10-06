"""Subgroup evidence: the protocol's subgroup factors as patient variables, and their effect on outcomes (L039).

A. Generation. Every factor the protocol stratifies by or names as an analysis subgroup, and that no patient variable
   carries yet, is generated for each patient from registry BASELINE tables (data/evidence_baseline_v1: baseline
   characteristics of enrolled participants, 13.6k registry trials):
   * retrieval: registry baseline measures whose title or category labels share the factor's distinctive words;
   * mapping: a model maps each measure's category labels to the protocol's levels (or 'none'), three independent
     votes, a mapping kept when at least two agree; a measure of another characteristic maps to nothing;
   * pooling: per trial, the share of each level; trials weighted equally, within the protocol's disease family and
     phase, then family, then all oncology, with at least MIN_TRIALS_PREVALENCE trials;
   * otherwise the stated levels are equally likely (assumption A27).
   Variables an eligibility criterion reads are left to the eligibility machinery (not generated here).

B. Effects. For every factor (generated, existing baseline variables such as performance status, sex, and age split at
   65) the registry RESULTS tables reported by subgroup (outcome measures whose classes are the factor's levels; 13.7k
   registry trials) give, within each trial and group, the response odds ratio and the median ratio of a
   time-to-event outcome of each level against the reference level (the first). Trial estimates are pooled by their
   median within the disease family, else all oncology, with at least MIN_TRIALS_EFFECT trials. The effect is
   prognostic (A28): applied in every arm, multiplicative on the progression hazard (hazard ratio = 1 / median ratio)
   and the response odds, summed across factors on the log scale, and centred on the patient mix so each arm's
   overall rate is unchanged. A factor with no such evidence has no effect ('mix only').

Every value records its source. The evidence cut-off (cutoff.excluded) and the protocol's own trial are excluded.
"""

import gzip
import json
import math
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

import numpy as np

from ..protocol import schemas as psc

SUBGROUP_EVIDENCE_VERSION = "subgroup-evidence-1.0.0"
MIN_TRIALS_PREVALENCE = 3
MIN_TRIALS_EFFECT = 3
MAX_CANDIDATES = 20
VOTES = 3
ALL = "ALL"                        # a results row covering the whole population (every level together)
BATCH = 10
EVIDENCE_FILE = "subgroup_evidence.json"
BASELINE = Path("data/evidence_baseline_v1/baseline_measures.parquet")
RESULTS_CORPUS = Path("data/raw/ctgov_oncology_results/corpus.jsonl.gz")
OUTCOME_INDEX = Path("data/reference_derived/subgroup_outcomes.jsonl")
GENERIC = {"the", "of", "and", "or", "vs", "versus", "at", "to", "in", "on", "for", "a", "an", "by", "with", "each", "baseline",
           "study", "entry", "patients", "patient", "participants", "participant", "number", "status", "categories", "category",
           "type", "group", "yes", "no", "not", "any", "all", "other", "per", "who", "had", "have", "were", "was", "is", "are"}
DEMOGRAPHIC_WORDS = {"age", "aged", "older", "elderly", "sex", "gender", "male", "female", "men", "women", "race", "racial",
                     "ethnicity", "ethnic", "hispanic"}
TTE_VARS = {"progression_free_survival", "overall_survival", "event_free_survival", "disease_free_survival", "time_to_progression",
            "relapse_free_survival"}

TEXT = {"type": "string"}
MAP_SCHEMA = psc.obj({"levels": {"type": "array", "items": TEXT}, "measures": {"type": "array", "items": psc.obj({
    "id": TEXT, "relevant": {"type": "boolean"}, "maps": {"type": "array", "items": psc.obj({"category": TEXT, "level": TEXT})}})}})
MAP_INSTRUCTIONS = (
    "A clinical trial protocol names a patient subgroup factor ('factor') and, when it states them, its levels "
    "('levels'). 'measures' are tables from other trials' registry results, each with its category labels. For every "
    "measure decide whether it reports this same patient characteristic, measured the same way (relevant). For a "
    "relevant measure map EVERY category label to the protocol level it belongs to, copying the level name exactly; a "
    "label that covers ALL participants of the table (the whole population, every level together, e.g. 'all "
    "participants', 'overall', 'intent-to-treat') maps to 'ALL'; a label that belongs to no single level (missing, "
    "unknown, a row combining some but not all levels, a different cut-off, or a value of another characteristic) "
    "maps to 'none'. A measure of a different characteristic, of a response category, of a "
    "time point or of a treatment group is not relevant. When 'levels' is empty, return in 'levels' the level names to "
    "use (2 to 6, taken from the category labels of the relevant measures, mutually exclusive) and map to them; "
    "otherwise return 'levels' unchanged.")


# ----------------------------------------------------------------------------- words and factors


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (s or "").casefold().replace("_", " ")) if w not in GENERIC and len(w) > 1}


def slug(text: str) -> str:
    return "_".join(re.findall(r"[a-z0-9]+", (text or "").casefold().split("(")[0]))[:60] or "factor"


def _q(x):
    return ((x or {}).get("text") if isinstance(x, dict) else x) or ""


def parse_levels(text: str) -> list[str]:
    """Levels a factor's own wording states: 'prior X (yes vs no)', 'stage (1 or 2 vs 3)', '(A, B, C)'."""
    m = re.findall(r"\(([^()]*)\)", text or "")
    if not m and re.search(r"\s(?:vs\.?|versus)\s", text or ""):
        m = [text]                                     # 'A versus B' without parentheses: the whole wording
    for inner in reversed(m):
        inner = inner.split(";")[0]                    # alternative groupings: the first one stated
        parts = list(dict.fromkeys(p.strip(" .") for p in re.split(r"\s+(?:vs\.?|versus)\s+|\s*[,/]\s*", inner) if p.strip(" .")))
        if 2 <= len(parts) <= 6:
            return parts
    return []


def protocol_factors(spec: dict) -> list[dict]:
    """Stratification factors and analysis-section subgroups, with the variable key and levels the protocol gives.
    Demographic factors (age, sex, race, ethnicity) are not listed: they are generated by the population stage."""
    from ..protocol import expressions as ex

    strat = spec.get("stratification") or {}
    leaves = [lf for st in strat.get("strata") or [] for lf in ex.leaves(st.get("logic"))]
    out = []
    named = [(_q(f), f.get("canonical_factor"), "protocol stratification factor") for f in strat.get("factors") or []]
    named += [(_q(s.get("subgroup")), None, "protocol subgroup (analysis section)") for s in spec.get("subgroups") or []]
    for text, canon, source in named:
        w = _words(text)
        if not w or w & DEMOGRAPHIC_WORDS:
            continue
        if any(len(w & _words(o["text"])) / max(1, len(w | _words(o["text"]))) >= 0.6 for o in out):
            continue                                       # the same factor named twice
        mine = [lf for lf in leaves if canon and (lf.get("canonical") == canon or lf.get("variable") == f"var:{canon}")]
        key = next((lf["variable"] for lf in mine if lf.get("variable")), None) or f"var:{canon or slug(text)}"
        levels = list(dict.fromkeys(c for lf in mine for c in lf.get("categories") or []))
        if len(levels) < 2:
            levels = parse_levels(text) or levels
        out.append({"key": key, "text": " ".join(text.split()), "levels": levels, "source": source, "kind": "generated"})
    return out


def existing_key(factor: dict, patients: list[dict], spec: dict, keys: set[str]) -> str | None:
    """A patient variable generated before this step (e.g. for eligibility; `keys`) that carries this factor, matched by
    meaning: at least half of the factor's distinctive words are in its name (or the protocol's name for it) or values."""
    from .subgroup_report import _value, variable_names

    names = variable_names(spec)
    fw = _words(factor["text"].split("(")[0])
    lw = {w for lv in factor["levels"] for w in _words(lv)}
    best, score = None, 0
    for k in keys - {"patient_id"}:
        if k.startswith("demographic:"):
            continue
        kw = _words(k.split(":", 1)[-1]) | _words(names.get(k, ""))
        vw = {w for p in patients[:500] for w in _words(str(_value(p.get(k)) or ""))}
        covered = len(fw & (kw | vw))
        if covered < max(1, math.ceil(len(fw) / 2)):
            continue
        s = 2 * covered + len(lw & vw)
        if s > score:
            best, score = k, s
    return best


def eligibility_variables(spec: dict) -> set[str]:
    return {m for c in spec.get("eligibility") or [] for m in re.findall(r'"variable": "([^"]+)"', json.dumps(c))}


# ----------------------------------------------------------------------------- model mapping (three votes)


def map_categories(model, factor: dict, candidates: list[dict], votes: int = VOTES) -> tuple[list[str], dict]:
    """{candidate id: {category label: level}} kept where at least two of three votes agree, and the levels. Candidates
    go in batches of BATCH (a large table list overflows a response); levels the protocol does not state are fixed by
    the first batch."""
    levels, maps = factor["levels"], {}
    for i in range(0, len(candidates), BATCH):
        levels, m = _map_batch(model, {**factor, "levels": levels}, candidates[i:i + BATCH], votes)
        maps.update(m)
        if not levels:
            break
    return levels, maps


def _map_batch(model, factor: dict, candidates: list[dict], votes: int) -> tuple[list[str], dict]:
    if not candidates:
        return factor["levels"], {}
    payload = {"instructions": MAP_INSTRUCTIONS, "factor": factor["text"], "levels": factor["levels"],
               "measures": [{"id": c["id"], "measure": c["title"][:300], "categories": [x[:200] for x in c["categories"][:25]]}
                            for c in candidates]}

    def one(v):
        p = dict(payload)
        if v:
            p["independent_review"] = f"review {v + 1} of {votes}: judge from scratch"
        try:
            return model.extract("subgroup_category_map", MAP_SCHEMA, p)
        except Exception:  # noqa: BLE001 - a failed vote counts as no vote
            return None
    with ThreadPoolExecutor(votes) as pool:
        outs = [o for o in pool.map(one, range(votes)) if o]
    levels = factor["levels"]
    if not levels:
        sets = Counter(tuple(o.get("levels") or []) for o in outs if 2 <= len(o.get("levels") or []) <= 6)
        top = sets.most_common(1)
        levels = list(top[0][0]) if top and top[0][1] >= 2 else []
    if not levels:
        return [], {}
    tally = defaultdict(Counter)
    for o in outs:
        for m in o.get("measures") or []:
            if not m.get("relevant"):
                continue
            for x in m.get("maps") or []:
                if x.get("level") in levels or x.get("level") == ALL:
                    tally[(m["id"], x.get("category"))][x["level"]] += 1
    maps = defaultdict(dict)
    need = min(2, len(outs))
    for (cid, cat), c in tally.items():
        lvl, k = c.most_common(1)[0]
        if k >= need:
            maps[cid][cat] = lvl
    return levels, {k: v for k, v in maps.items() if len(set(v.values())) >= 2}


def _retrieve(index: list[dict], factor: dict, idf: dict, labels_only: bool = False, k: int = MAX_CANDIDATES) -> list[dict]:
    """The candidate measures sharing the factor's distinctive words (title or labels; for results tables the labels,
    where a subgroup split is written), best first."""
    fw = _words(factor["text"].split("(")[0]) | _words(factor["key"].split(":", 1)[-1])
    lw = {w for lv in factor["levels"] for w in _words(lv)}
    scored = []
    for c in index:
        tw = c["label_words"] if labels_only else c["words"]
        hit = fw & tw
        if not hit:
            continue
        s = sum(idf.get(w, 1.0) for w in hit) + 0.5 * sum(idf.get(w, 1.0) for w in lw & tw)
        scored.append((s * math.log(1 + len(c["ncts"])), c))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:k]]


def _idf(index: list[dict]) -> dict:
    df = Counter(w for c in index for w in c["words"])
    n = len(index) or 1
    return {w: math.log(n / k) for w, k in df.items()}


# ----------------------------------------------------------------------------- A. prevalence from baseline tables


@lru_cache(maxsize=1)
def _baseline_trials() -> dict:
    """{(nct, measure title): {"family", "phase", "counts": {label: n}}} of categorical baseline measures."""
    import pyarrow.parquet as pq

    from .baseline_extra import _family

    rows = pq.read_table(BASELINE, columns=["nct_id", "phase", "condition_mesh", "measure_title", "param_type", "class_title",
                                            "category", "is_total_group", "value"]).to_pylist()
    per = {}
    for r in rows:
        if r["param_type"] not in ("COUNT_OF_PARTICIPANTS", "NUMBER") or r["value"] is None:
            continue
        label = (r["category"] or r["class_title"] or "").strip()
        if not label or not r["measure_title"]:
            continue
        t = per.setdefault((r["nct_id"], " ".join(r["measure_title"].split())), {"mesh": r["condition_mesh"], "phase": r["phase"],
                                                                     "total": Counter(), "groups": Counter()})
        (t["total"] if r["is_total_group"] else t["groups"])[label] += float(r["value"])
    out = {}
    for k, t in per.items():
        counts = t["total"] or t["groups"]
        if len(counts) >= 2 and sum(counts.values()) >= 5:
            out[k] = {"family": _family(t["mesh"]), "phase": t["phase"], "counts": dict(counts)}
    return out


@lru_cache(maxsize=1)
def _baseline_index() -> tuple[list[dict], dict]:
    sig = defaultdict(list)
    for (nct, title), t in _baseline_trials().items():
        sig[(title, tuple(sorted(t["counts"])))].append(nct)
    index = [{"id": f"B{i}", "title": t, "categories": list(cats), "ncts": ncts, "words": _words(t) | {w for c in cats for w in _words(c)}}
             for i, ((t, cats), ncts) in enumerate(sorted(sig.items()))]
    return index, _idf(index)


def prevalence(model, factor: dict, family: str | None, phase: str | None, exclude: set[str]) -> dict:
    index, idf = _baseline_index()
    cands = _retrieve(index, factor, idf)
    levels, maps = map_categories(model, factor, cands)
    factor["levels"] = levels or factor["levels"]
    trials = _baseline_trials()
    per_trial = {}
    for c in cands:
        m = maps.get(c["id"])
        if not m:
            continue
        for nct in c["ncts"]:
            if nct in exclude or nct in per_trial:
                continue
            t = trials.get((nct, c["title"]))
            if not t:
                continue
            by = Counter()
            for lab, k in t["counts"].items():
                if m.get(lab) in factor["levels"]:
                    by[m[lab]] += k
            tot = sum(by.values())
            if tot >= 5 and len(by) >= 2:
                per_trial[nct] = {"family": t["family"], "phase": t["phase"], "p": [by.get(lv, 0) / tot for lv in factor["levels"]],
                                  "n": tot, "measure": c["title"]}
    sel_all = list(per_trial.values())
    for label, sel in ((f"{family}, {phase}", [t for t in sel_all if t["family"] == family and t["phase"] == phase]),
                       (f"{family}", [t for t in sel_all if t["family"] == family]), ("all oncology", sel_all)):
        if len(sel) >= MIN_TRIALS_PREVALENCE and factor["levels"]:
            P = np.array([t["p"] for t in sel])
            return {"status": "RESOLVED", "levels": factor["levels"], "p": P.mean(axis=0).round(4).tolist(),
                    "trial_range_10_90": np.quantile(P, [0.1, 0.9], axis=0).round(3).tolist(), "trials": len(sel),
                    "participants": int(sum(t["n"] for t in sel)),
                    "measures": sorted({t["measure"] for t in sel})[:5],
                    "source": f"registry baseline tables of enrolled participants ({label}; {len(sel)} trials)"}
    if factor["levels"]:
        k = len(factor["levels"])
        return {"status": "ASSUMED", "levels": factor["levels"], "p": [round(1 / k, 4)] * k, "trials": len(sel_all),
                "source": f"assumption A27: levels equally likely (registry baseline tables: {len(sel_all)} trials, fewer than "
                          f"{MIN_TRIALS_PREVALENCE})"}
    return {"status": "NO_LEVELS", "levels": [], "p": [], "source": "the protocol states no levels and no registry table reports the factor"}


# ----------------------------------------------------------------------------- B. effects from results by subgroup


def build_outcome_index(corpus: Path = RESULTS_CORPUS, out: Path = OUTCOME_INDEX) -> int:
    """Efficacy outcome measures reported by class (>= 2 classes) from the registry results corpus: one JSON line per
    trial measure with each group's value per class (and the class denominators)."""
    from .quantify import classify

    out.parent.mkdir(parents=True, exist_ok=True)
    k = 0
    with gzip.open(corpus, "rt", encoding="utf-8") as fh, open(out, "w", encoding="utf-8") as wf:
        for line in fh:
            d = json.loads(line)
            ps = d.get("protocolSection") or {}
            nct = (ps.get("identificationModule") or {}).get("nctId")
            mesh = "; ".join(m.get("term", "") for m in (((d.get("derivedSection") or {}).get("conditionBrowseModule") or {}).get("meshes") or []))
            phase = ",".join((ps.get("designModule") or {}).get("phases") or [])
            separate = defaultdict(list)          # (variable, param) -> single-table measures: a subgroup reported as its own measure
            for m in ((d.get("resultsSection") or {}).get("outcomeMeasuresModule") or {}).get("outcomeMeasures") or []:
                kind, var = classify(m.get("title") or "", None)
                param = m.get("paramType")
                if not ((kind == "proportion" and var == "objective_response_rate" and param in ("NUMBER", "COUNT_OF_PARTICIPANTS"))
                        or (kind == "time_to_event" and var in TTE_VARS and param == "MEDIAN")):
                    continue
                classes = [c for c in m.get("classes") or [] if c.get("title")]
                if len(classes) < 2:
                    separate[(var, param)].append(m)
                    continue
                groups = defaultdict(dict)
                denoms = defaultdict(dict)
                for c in classes:
                    for dn in c.get("denoms") or []:
                        for x in dn.get("counts") or []:
                            try:
                                denoms[x["groupId"]][c["title"]] = float(x["value"])
                            except (KeyError, TypeError, ValueError):
                                pass
                    for cat in c.get("categories") or []:
                        for x in cat.get("measurements") or []:
                            try:
                                groups[x["groupId"]][c["title"]] = float(x["value"])
                            except (KeyError, TypeError, ValueError):
                                pass
                if not groups:
                    continue
                wf.write(json.dumps({"nct_id": nct, "mesh": mesh, "phase": phase, "title": m.get("title"), "variable": var, "param": param,
                                     "unit": m.get("unitOfMeasure"), "classes": [c["title"] for c in classes],
                                     "groups": groups, "denoms": denoms, "layout": "classes"}, ensure_ascii=False) + "\n")
                k += 1
            # one trial's separate measures of the same endpoint: each measure's title is a subgroup label; arms are matched
            # across measures by group title
            for (var, param), ms in separate.items():
                if len(ms) < 2:
                    continue
                groups, denoms = defaultdict(dict), defaultdict(dict)
                for m in ms:
                    gtitle = {g.get("id"): " ".join((g.get("title") or "").split()) for g in m.get("groups") or []}
                    for dn in m.get("denoms") or []:
                        for x in dn.get("counts") or []:
                            try:
                                denoms[gtitle.get(x["groupId"], x["groupId"])][m["title"]] = float(x["value"])
                            except (KeyError, TypeError, ValueError):
                                pass
                    for c in (m.get("classes") or [])[:1]:
                        for cat in (c.get("categories") or [])[:1]:
                            for x in cat.get("measurements") or []:
                                try:
                                    groups[gtitle.get(x["groupId"], x["groupId"])][m["title"]] = float(x["value"])
                                except (KeyError, TypeError, ValueError):
                                    pass
                if sum(len(v) >= 2 for v in groups.values()):
                    wf.write(json.dumps({"nct_id": nct, "mesh": mesh, "phase": phase, "title": f"{var.replace('_', ' ')}: separate result tables",
                                         "variable": var, "param": param, "unit": ms[0].get("unitOfMeasure"),
                                         "classes": [m["title"] for m in ms], "groups": groups, "denoms": denoms,
                                         "layout": "separate measures"}, ensure_ascii=False) + "\n")
                    k += 1
    return k


@lru_cache(maxsize=1)
def _outcome_rows() -> list[dict]:
    if not OUTCOME_INDEX.exists():
        build_outcome_index()
    with open(OUTCOME_INDEX, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


@lru_cache(maxsize=1)
def _outcome_index() -> tuple[list[dict], dict]:
    sig = defaultdict(list)
    for i, r in enumerate(_outcome_rows()):
        sig[(" ".join((r["title"] or "").split()), tuple(r["classes"]))].append(i)
    index = [{"id": f"O{j}", "title": t, "categories": list(cats), "rows": rows, "ncts": sorted({_outcome_rows()[i]["nct_id"] for i in rows}),
              "words": _words(t) | {w for c in cats for w in _words(c)}, "label_words": {w for c in cats for w in _words(c)}}
             for j, ((t, cats), rows) in enumerate(sorted(sig.items()))]
    return index, _idf(index)


def _logit(p):
    p = min(max(p, 0.01), 0.99)
    return math.log(p / (1 - p))


def complement(val: dict, levels: list[str], orr: bool) -> tuple[str, float] | None:
    """A two-level factor reported as one level and the whole population ('CPS >= 10' and 'all participants'): the
    other level's value from the whole and the level's share of patients (the denominators). A response proportion is
    exact (the whole is the patient-weighted average); a median through the event rates (ln 2 / median), exact for
    exponential times and approximate otherwise."""
    if ALL not in val or len(levels) != 2:
        return None
    have = [lv for lv in levels if lv in val]
    if len(have) != 1:
        return None
    lv, other = have[0], next(x for x in levels if x != have[0])
    (v_l, n_l), (v_all, n_all) = val[lv], val[ALL]
    if not n_l or not n_all or n_l >= n_all or v_l is None or v_all is None:
        return None
    s = n_l / n_all
    if orr:
        v = (v_all - s * v_l) / (1 - s)
        return (other, v) if 0 < v < 1 else None
    if v_l <= 0 or v_all <= 0:
        return None
    lam = (math.log(2) / v_all - s * math.log(2) / v_l) / (1 - s)
    return (other, math.log(2) / lam) if lam > 0 else None


def effects(model, factor: dict, family: str | None, exclude: set[str]) -> dict:
    from .baseline_extra import _family

    index, idf = _outcome_index()
    cands = _retrieve(index, factor, idf, labels_only=True, k=2 * MAX_CANDIDATES)
    if not cands or not factor["levels"]:
        return {"status": "NO_EVIDENCE", "source": "no registry results table reports outcomes by this factor"}
    _, maps = map_categories(model, factor, cands)
    rows = _outcome_rows()
    ref = factor["levels"][0]
    est = {"orr": defaultdict(list), "tte": defaultdict(list)}     # level -> [(nct, family, log effect vs reference)]
    for c in cands:
        m = maps.get(c["id"])
        if not m:
            continue
        for i in c["rows"]:
            r = rows[i]
            if r["nct_id"] in exclude:
                continue
            fam = _family(r["mesh"])
            orr = r["variable"] == "objective_response_rate"
            pct = "%" in (r["unit"] or "") or "percent" in (r["unit"] or "").casefold()
            for gid, vals in r["groups"].items():
                by = defaultdict(list)
                for cls, v in vals.items():
                    if m.get(cls) in factor["levels"] or m.get(cls) == ALL:
                        by[m[cls]].append((v, (r["denoms"].get(gid) or {}).get(cls)))
                # each level's value (a response proportion or a median) and its number of patients
                val = {}
                for lv, xs in by.items():
                    v, d = xs[0]
                    if orr:
                        v = v / d if r["param"] == "COUNT_OF_PARTICIPANTS" and d else (v / 100 if pct or v > 1 else v)
                    val[lv] = (v, d)
                derived = complement(val, factor["levels"], orr)
                if derived:
                    val[derived[0]] = (derived[1], None)
                val.pop(ALL, None)
                if ref not in val or len(val) < 2:
                    continue
                v0 = val[ref][0]
                for lv, (v1, _) in val.items():
                    if lv == ref:
                        continue
                    if orr:
                        est["orr"][lv].append((r["nct_id"], fam, _logit(v1) - _logit(v0)))
                    elif v0 > 0 and v1 > 0:
                        est["tte"][lv].append((r["nct_id"], fam, -math.log(v1 / v0)))     # log hazard ratio = -log median ratio
    out = {"reference_level": ref}
    for kind, by in est.items():
        res = {}
        for lv, xs in by.items():
            for label, sel in ((family, [x for x in xs if x[1] == family]), ("all oncology", xs)):
                per_trial = defaultdict(list)
                for nct, _, e in sel:
                    per_trial[nct].append(e)
                if len(per_trial) >= MIN_TRIALS_EFFECT:
                    vals = [float(np.median(v)) for v in per_trial.values()]
                    res[lv] = {"log_effect": round(float(np.median(vals)), 4), "trials": len(per_trial),
                               "range_10_90": np.quantile(vals, [0.1, 0.9]).round(3).tolist(), "evidence": label}
                    break
        out["log_odds_ratio" if kind == "orr" else "log_hazard_ratio"] = res
    found = bool(out.get("log_odds_ratio") or out.get("log_hazard_ratio"))
    n = max([v["trials"] for k in ("log_odds_ratio", "log_hazard_ratio") for v in (out.get(k) or {}).values()] or [0])
    out["status"] = "RESOLVED" if found else "NO_EVIDENCE"
    out["source"] = (f"registry results reported by this subgroup (up to {n} trials; prognostic, A28)" if found
                     else "no registry results table reports outcomes by this factor in enough trials")
    return out


# ----------------------------------------------------------------------------- the stage step and the patient multiplier


def level_of(factor: dict, b: dict):
    from .subgroup_report import _ecog, _value

    if factor["kind"] == "age":
        a = _value(b.get("demographic:age"))
        return None if a is None else ("< 65 years" if float(a) < 65 else ">= 65 years")
    v = _value(b.get(factor["key"]))
    if v is None:
        return None
    return _ecog(v) if "ecog" in factor["key"] else str(v)


def build(model, spec: dict, patients: list[dict], family: str | None, phase: str | None, own_nct: str | None, rng) -> dict:
    """Generate the protocol's subgroup factors for `patients` (in place) and find every factor's effects."""
    from ..cutoff import excluded

    exclude = set(excluded()) | ({own_nct} if own_nct else set())
    keys = {k for p in patients[:2000] for k in p}
    elig = eligibility_variables(spec)
    factors = []
    for f in protocol_factors(spec):
        found = f["key"] if f["key"] in keys else existing_key(f, patients[:2000], spec, keys)
        if found or f["key"] in elig:
            f["key"], f["kind"] = found or f["key"], "existing"
            vals = {str(level_of(f, p)) for p in patients[:2000] if level_of(f, p) is not None}
            f["levels"] = sorted(vals) if 2 <= len(vals) <= 6 else f["levels"]
            factors.append(f)
            continue
        prev = prevalence(model, f, family, phase, exclude)
        f["prevalence"] = prev
        if prev["levels"]:
            draws = rng.choice(len(prev["levels"]), size=len(patients), p=np.array(prev["p"]) / sum(prev["p"]))
            for p, i in zip(patients, draws, strict=True):
                p[f["key"]] = prev["levels"][int(i)]
        factors.append(f)
    for key, text, kind in (("var:ecog_performance_status", "ECOG performance status (0, 1, 2 or more)", "existing"),
                            ("demographic:sex", "sex (female, male)", "existing"), ("demographic:age", "age (< 65 years, >= 65 years)", "age")):
        ages = [((p.get("demographic:age") or {}).get("value") or 0) for p in patients[:2000]]
        if key in keys and not (kind == "age" and sum(a >= 65 for a in ages) < 0.05 * max(1, len(ages))):
            factors.append({"key": key, "text": text, "levels": parse_levels(text), "source": "baseline factor", "kind": kind})
    for f in factors:
        if f.get("levels"):
            mix = Counter(level_of(f, p) for p in patients)
            n = sum(v for k, v in mix.items() if k is not None) or 1
            f["mix"] = {lv: round(mix.get(lv, 0) / n, 4) for lv in f["levels"]}
            f["effects"] = effects(model, f, family, exclude)
        else:
            f["effects"] = {"status": "NO_EVIDENCE", "source": "no levels"}
    return {"version": SUBGROUP_EVIDENCE_VERSION, "family": family, "phase": phase, "factors": factors,
            "assumptions": ["A27_subgroup_prevalence_equal", "A28_prognostic_effects"]}


def patient_log_effects(b: dict, evidence: dict | None) -> tuple[float, float]:
    """(log hazard multiplier, log odds shift) of one patient: the sum over factors of the level's effect minus its
    mix-weighted mean (A28), so each arm's overall rate is unchanged."""
    if not evidence:
        return 0.0, 0.0
    lh = lo = 0.0
    for f in evidence.get("factors") or []:
        eff, mix = f.get("effects") or {}, f.get("mix") or {}
        if eff.get("status") != "RESOLVED":
            continue
        lv = level_of(f, b)
        for key, acc in (("log_hazard_ratio", "h"), ("log_odds_ratio", "o")):
            table = eff.get(key) or {}
            if not table:
                continue
            val = lambda x: 0.0 if x == eff["reference_level"] else (table.get(x) or {}).get("log_effect", 0.0)  # noqa: E731
            centred = (val(lv) if lv is not None else 0.0) - sum(w * val(x) for x, w in mix.items())
            if lv is None:
                centred = 0.0
            if acc == "h":
                lh += centred
            else:
                lo += centred
    return lh, lo


def effect_sources(evidence: dict | None) -> dict:
    """{variable: {"source": ...}} of the factors with a resolved effect (for the subgroup report's outcome driver)."""
    return {f["key"]: {"source": f["effects"]["source"]} for f in (evidence or {}).get("factors") or []
            if (f.get("effects") or {}).get("status") == "RESOLVED"}


def prevalence_sources(evidence: dict | None) -> dict:
    """{variable: source} of the factors this step generated (for the subgroup report)."""
    return {f["key"]: f["prevalence"]["source"] for f in (evidence or {}).get("factors") or [] if (f.get("prevalence") or {}).get("source")}


def load(stage_dir: Path) -> dict | None:
    """The subgroup evidence of the population stage that `stage_dir` (any stage of the same run version) descends from."""
    d = Path(stage_dir)
    m = re.match(r"^[a-z_]+_(v.+)$", d.name)
    cands = [d.parent / f"population_{m.group(1)}"] if m else []
    cands += [d.parent / "population", d.parent.parent / "population"]
    for c in cands:
        f = c / EVIDENCE_FILE
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
    return None
