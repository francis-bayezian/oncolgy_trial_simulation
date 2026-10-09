"""Primary engine for ratio noninferiority (L060): a comparison of geometric means (pharmacokinetic exposure, any
log-normal measure) against a stated ratio margin, for any protocol whose primary analyses state it.

Every input comes from the protocol, per primary analysis:
* the margin: the ratio in the null hypothesis ('GMR <= 0.8');
* the true ratio the study is powered for: the stated effect ('under a true AUC GMR = 1.07');
* alpha and sidedness, power, the evaluable n, the allocation ratio;
* alpha recycling: an alpha stated for when another hypothesis is rejected ('or at alpha = 0.05 one-sided if the
  hypothesis for X is rejected').
The log-scale standard deviation, when the protocol does not state it, is DERIVED from its own power statement (the
one at which the stated test has the stated power at the stated ratio), labelled as such; the variability registry trials
report for the same measure (geometric coefficient of variation) is the evidence-based sensitivity analysis.

Per simulated trial: log values per patient in each arm, Welch's t on the log scale, the lower (1 - alpha) confidence
bound of the geometric-mean ratio, success when it exceeds the margin. Results over a grid of true ratios (the margin:
type I error; up to the design ratio and beyond), per endpoint and for the whole family with alpha recycling.
"""

from __future__ import annotations

import glob
import json
import math
import re
from pathlib import Path

import numpy as np
from scipy import optimize, stats

from .. import assets
from .predictive import from_draws

RATIO_NI_VERSION = "ratio-ni-1.0.0"
RATIO_WORDS = re.compile(r"\b(gmr|geometric\s+mean\s+ratio|ratio\s+of\s+(?:the\s+)?geometric\s+means?)\b", re.I)
NI_WORDS = re.compile(r"non.?inferior|lower\s+bound|margin", re.I)


def _q(x):
    return ((x or {}).get("text") if isinstance(x, dict) else x) or ""


def _num(text: str, lo: float, hi: float, after: str = "") -> float | None:
    for m in re.finditer(rf"{after}[^0-9]{{0,20}}?(\d+(?:\.\d+)?)", text, re.I):
        v = float(m.group(1))
        if lo <= v <= hi:
            return v
    return None


def analyses(spec: dict) -> list[dict]:
    """The primary analyses stated as ratio noninferiority, each with margin, true ratio, alpha, power and n."""
    sizes = [x for x in spec.get("sample_size") or [] if x.get("quantity") == "evaluable_target" and x.get("value")]
    alloc = ((spec.get("design") or {}).get("allocation") or {}).get("ratio") or [1, 1]
    out = []
    for a in spec.get("analyses") or []:
        if not a.get("primary"):
            continue
        text = " ".join(_q(a.get(k)) for k in ("hypothesis", "estimate", "method", "evidence")) + " " + " ".join(_q(e) for e in a.get("effects") or [])
        if not (RATIO_WORDS.search(text) and (NI_WORDS.search(text) or re.search(r"(?:≤|<=|<)\s*\d", _q(a.get("hypothesis"))))):
            continue
        margin = _num(_q(a.get("hypothesis")), 0.5, 1.0, r"(?:≤|<=|<|margin)")
        effect = next((v for e in a.get("effects") or [] for v in [_num(_q(e), 0.5, 3.0, r"(?:gmr|ratio)\s*=?")] if v), None)
        alpha = (a.get("alpha") or {}).get("value")
        if margin is None or effect is None or not alpha:
            continue
        ep = _q(a.get("endpoint"))
        epk = set(re.findall(r"[a-z0-9]+", ep.casefold()))
        n = next((s["value"] for s in sizes if epk & set(re.findall(r"[a-z0-9]+", (_q(s.get("refers_to")) + " " + _q(s.get("text"))).casefold()))
                  - {"cycle", "the", "with", "evaluable", "data", "participants"}), None)
        if n is None:
            continue
        out.append({"analysis_id": a["analysis_id"], "endpoint": ep, "margin": margin, "design_ratio": effect, "alpha": float(alpha),
                    "power_stated": (a.get("power") or {}).get("value"), "n": int(n), "allocation": [float(x) for x in alloc],
                    "sources": {"margin": _q(a.get("hypothesis")), "ratio": [_q(e) for e in a.get("effects") or []],
                                "alpha": _q((a.get("alpha") or {}).get("text")), "n": "evaluable target matched to the endpoint"}})
    # alpha recycling: another primary analysis's alpha text 'or at alpha = X ... if the hypothesis for <endpoint> is rejected'
    for a in spec.get("analyses") or []:
        t = _q((a.get("alpha") or {}).get("text"))
        m = re.search(r"or at\s*(?:α|alpha)\s*=?\s*(\d*\.\d+).{0,40}?if the hypothesis for\s+(.+?)\s+is rejected", t, re.I | re.S)
        if not m:
            continue
        target = set(re.findall(r"[a-z0-9]+", _q(a.get("endpoint")).casefold()))
        source = set(re.findall(r"[a-z0-9]+", m.group(2).casefold()))
        for x in out:
            if target and target <= set(re.findall(r"[a-z0-9]+", x["endpoint"].casefold())) | target and \
                    len(target & set(re.findall(r"[a-z0-9]+", x["endpoint"].casefold()))) >= max(1, len(target) - 1):
                x["recycled_alpha"] = {"alpha": float(m.group(1)), "if_rejected": " ".join(sorted(source)), "source": t}
    return out


def _arms(n: int, alloc: list[float]) -> tuple[int, int]:
    n1 = int(round(n * alloc[0] / sum(alloc)))
    return n1, n - n1


def power_normal(sd: float, d: dict) -> float:
    n1, n2 = _arms(d["n"], d["allocation"])
    se = sd * math.sqrt(1 / n1 + 1 / n2)
    return float(stats.norm.cdf((math.log(d["design_ratio"]) - math.log(d["margin"])) / se - stats.norm.ppf(1 - d["alpha"])))


def derived_sd(d: dict) -> float | None:
    """The log-scale SD at which the stated test has the stated power at the stated ratio (from the protocol)."""
    p = d.get("power_stated")
    if not p or not 0 < p < 1:
        return None
    try:
        return float(optimize.brentq(lambda s: power_normal(s, d) - p, 1e-4, 20))
    except ValueError:
        return None


def registry_sd(endpoint: str, agents: list[str]) -> dict:
    """Log-scale SD from the geometric coefficients of variation registry trials report for the same kind of measure
    (AUC, trough), preferring trials of the same agents; sd = sqrt(log(1 + CV^2))."""
    kind = "trough" if re.search(r"trough|cmin", endpoint, re.I) else "auc" if re.search(r"\bauc", endpoint, re.I) else None
    if not kind:
        return {"status": "NO_EVIDENCE", "reason": "the endpoint is neither an AUC nor a trough concentration"}
    pat = re.compile(r"trough|ctrough|cmin\b" if kind == "trough" else r"\bauc", re.I)
    own, other = [], []
    for f in glob.glob(str(Path(assets.path("raw_ctgov")) / "NCT*.json")):
        t = json.loads(Path(f).read_text(encoding="utf-8"))
        ivs = " ".join((iv.get("name") or "") + " " + " ".join(iv.get("otherNames") or []) for iv in
                       ((t.get("protocolSection") or {}).get("armsInterventionsModule") or {}).get("interventions") or []).casefold()
        mine = any(a and a in ivs for a in agents)
        for m in ((t.get("resultsSection") or {}).get("outcomeMeasuresModule") or {}).get("outcomeMeasures") or []:
            if m.get("paramType") != "GEOMETRIC_MEAN" or "coefficient" not in (m.get("dispersionType") or "").casefold() or not pat.search(m.get("title") or ""):
                continue
            for cl in m.get("classes") or []:
                for c in cl.get("categories") or []:
                    for x in c.get("measurements") or []:
                        try:
                            cv = float(x.get("spread")) / 100
                        except (TypeError, ValueError):
                            continue
                        if 0 < cv < 5:
                            (own if mine else other).append((t["protocolSection"]["identificationModule"]["nctId"], cv))
    use, level = (own, "same agents") if len({n for n, _ in own}) >= 2 else (own + other, "all registry trials")
    if not use:
        return {"status": "NO_EVIDENCE", "reason": f"no registry geometric CV for {kind}"}
    cvs = np.array([c for _, c in use])
    cv = float(np.median(cvs))
    return {"status": "RESOLVED", "kind": kind, "level": level, "trials": len({n for n, _ in use}), "values": len(cvs),
            "median_cv": round(cv, 3), "cv_iqr": np.round(np.quantile(cvs, [0.25, 0.75]), 3).tolist(),
            "sd": round(math.sqrt(math.log(1 + cv ** 2)), 4)}


def _trial(d: dict, sd: float, ratio: float, rng) -> tuple[bool, float, float, float]:
    """One simulated trial: Welch t on log values; success, observed GMR, its lower bound, the one-sided p-value."""
    n1, n2 = _arms(d["n"], d["allocation"])
    x = rng.normal(math.log(ratio), sd, n1)
    y = rng.normal(0.0, sd, n2)
    diff = x.mean() - y.mean()
    v1, v2 = x.var(ddof=1) / n1, y.var(ddof=1) / n2
    se = math.sqrt(v1 + v2)
    df = (v1 + v2) ** 2 / (v1 ** 2 / (n1 - 1) + v2 ** 2 / (n2 - 1))
    tstat = (diff - math.log(d["margin"])) / se
    p = float(stats.t.sf(tstat, df))
    lower = diff - stats.t.ppf(1 - d["alpha"], df) * se
    return bool(lower > math.log(d["margin"])), math.exp(diff), math.exp(lower), p


def simulate(ds: list[dict], sds: dict, ratios: dict, rng, replicates: int) -> dict:
    """Every endpoint at its own alpha; then the family with alpha recycling (one rejection lets the other be tested at
    its recycled alpha)."""
    per = {d["analysis_id"]: {"success": 0, "gmr": [], "lower": []} for d in ds}
    family = {"all": 0, "any": 0}
    for _ in range(replicates):
        res = {d["analysis_id"]: _trial(d, sds[d["analysis_id"]], ratios[d["analysis_id"]], rng) for d in ds}
        ok = {k: r[0] for k, r in res.items()}
        for d in ds:                                       # recycling: tested again at the recycled alpha
            rc = d.get("recycled_alpha")
            if not ok[d["analysis_id"]] and rc and any(ok[o["analysis_id"]] for o in ds if o is not d):
                ok[d["analysis_id"]] = res[d["analysis_id"]][3] < rc["alpha"]
        for k, r in res.items():
            per[k]["success"] += ok[k]
            per[k]["gmr"].append(r[1])
            per[k]["lower"].append(r[2])
        family["all"] += all(ok.values())
        family["any"] += any(ok.values())
    return {"per_endpoint": {k: {"p_success": v["success"] / replicates, "observed_gmr": from_draws(v["gmr"]),
                                 "lower_bound": from_draws(v["lower"])} for k, v in per.items()},
            "all_endpoints_succeed": family["all"] / replicates, "any_endpoint_succeeds": family["any"] / replicates}


def design(spec: dict) -> dict:
    ds = analyses(spec)
    return {"status": "RESOLVED", "analyses": ds} if ds else {"status": "UNRESOLVED", "reason": "no primary ratio-noninferiority analysis with margin, ratio, alpha and n"}


def run(spec_lock: Path, out_dir: Path, replicates: int = 4000, seed: int = 20261008) -> dict:
    from .studyspec import load_studyspec

    spec, record = load_studyspec(spec_lock)
    ds = analyses(spec)
    doc = {"ratio_ni_version": RATIO_NI_VERSION, "seed": seed, "replicates": replicates, "inputs": {"studyspec": record["files"]["studyspec.json"]}}
    if not ds:
        doc.update({"status": "UNRESOLVED", "reason": "no primary ratio-noninferiority analysis with margin, ratio, alpha and n"})
    else:
        agents = sorted({(it.get("canonical_agent") or _q(it.get("agent"))).replace("_", " ").casefold()
                         for it in spec.get("interventions") or [] if it.get("category") == "anticancer_drug"})
        from .review import synonym
        agents = sorted(set(agents) | {s for s in (synonym(a) for a in agents) if s})
        sd_info = {}
        for d in ds:
            der, reg = derived_sd(d), registry_sd(d["endpoint"], agents)
            sd_info[d["analysis_id"]] = {"protocol_derived_sd": der, "registry": reg,
                                         "protocol_derived_cv": round(math.sqrt(math.exp(der ** 2) - 1), 3) if der else None}
        rng = np.random.default_rng(seed)
        scenarios = []
        for label, pick in (("protocol-derived variability", "protocol_derived_sd"), ("registry variability (sensitivity)", "registry")):
            sds = {}
            for d in ds:
                s = sd_info[d["analysis_id"]]
                sds[d["analysis_id"]] = s["protocol_derived_sd"] if pick == "protocol_derived_sd" else (s["registry"].get("sd") if s["registry"].get("status") == "RESOLVED" else None)
            if any(v is None for v in sds.values()):
                scenarios.append({"variability": label, "status": "UNRESOLVED", "reason": "no standard deviation for every endpoint"})
                continue
            grid = []
            for g in (0.0, 0.5, 1.0, 1.5):                 # 0: true ratio at the margin (type I error); 1: the design ratio
                ratios = {d["analysis_id"]: math.exp(math.log(d["margin"]) + g * (math.log(d["design_ratio"]) - math.log(d["margin"]))) for d in ds}
                grid.append({"position": g, "true_ratios": {k: round(v, 4) for k, v in ratios.items()}, **simulate(ds, sds, ratios, rng, replicates)})
            scenarios.append({"variability": label, "status": "RESOLVED", "sd": {k: round(v, 4) for k, v in sds.items()}, "grid": grid})
        doc.update({"status": "RESOLVED", "analyses": ds, "variability": sd_info, "scenarios": scenarios,
                    "truth": "the true ratios are unknown: results over a grid from the margin (type I error) to beyond the design ratio"})
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "ratio_ni_results.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    L = [f"# Ratio noninferiority primary analysis ({RATIO_NI_VERSION})", ""]
    if doc["status"] != "RESOLVED":
        L.append(f"{doc['status']}: {doc['reason']}")
    else:
        L += ["| Analysis | Endpoint | Margin | Design ratio | Alpha (one-sided) | Recycled alpha | n (allocation) | SD: protocol-derived (CV) | SD: registry (CV, trials, level) |",
              "| --- | --- | ---: | ---: | ---: | --- | --- | --- | --- |"]
        for d in ds:
            s = doc["variability"][d["analysis_id"]]
            r = s["registry"]
            reg = f"{r['sd']} ({r['median_cv']:.0%}, {r['trials']} trials, {r['level']})" if r.get("status") == "RESOLVED" else r.get("reason")
            der = f"{s['protocol_derived_sd']:.3f} ({s['protocol_derived_cv']:.0%})" if s["protocol_derived_sd"] else "not derivable"
            L.append(f"| {d['analysis_id']} | {d['endpoint']} | {d['margin']} | {d['design_ratio']} | {d['alpha']} | "
                     f"{(d.get('recycled_alpha') or {}).get('alpha', '-')} | {d['n']} ({':'.join(f'{x:g}' for x in d['allocation'])}) | {der} | {reg} |")
        for sc in doc["scenarios"]:
            L += ["", f"## {sc['variability']}", ""]
            if sc["status"] != "RESOLVED":
                L.append(f"{sc['status']}: {sc['reason']}")
                continue
            L += ["| True ratios | " + " | ".join(f"P(success) {d['analysis_id']}" for d in ds) + " | All succeed | Observed GMR p10/p50/p90 |",
                  "| --- | " + " | ".join("---:" for _ in ds) + " | ---: | --- |"]
            for g in sc["grid"]:
                obs = "; ".join(f"{k}: {v['observed_gmr']['p10']:.3f}/{v['observed_gmr']['p50']:.3f}/{v['observed_gmr']['p90']:.3f}" for k, v in g["per_endpoint"].items())
                L.append(f"| {', '.join(f'{k} {v}' for k, v in g['true_ratios'].items())} | " + " | ".join(f"{g['per_endpoint'][d['analysis_id']]['p_success']:.3f}" for d in ds)
                         + f" | {g['all_endpoints_succeed']:.3f} | {obs} |")
    (out / "ratio_ni_results.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return doc
