"""Primary engine for a continuous comparison (lesson L034), paired (one group measured twice, e.g. two tracers in each
patient) or between two groups, for any protocol whose analysis states its design: the test, alpha, power, the effect
the study is powered for, and the evaluable sample size.

Every input comes from the protocol:
* the effect delta: the number in the analysis's stated effect ('a mean of paired differences of 10 in SUVmean');
* alpha, sidedness, power: the compiled analysis;
* n: the evaluable target, else the target or maximum accrual;
* the standard deviation, when not stated, is DERIVED from those figures: the one at which the protocol's own test has
  the stated power for delta at n (normal approximation with the test's asymptotic relative efficiency: 3/pi for
  rank tests). It is a derivation from the protocol, labelled as such, and checked by simulating the stated power.

Results: P(the test succeeds) over a grid of true effects (0 up to 1.5 x delta), and the predictive percentiles
(p10, p30, p50, p70, p90) of the observed mean difference at no effect and at the design effect.
"""

import json
import math
import re
from pathlib import Path

import numpy as np
from scipy import stats

from .predictive import from_draws

CONTINUOUS_VERSION = "continuous-1.0.0"
RANK_TESTS = ("wilcoxon", "signed rank", "rank sum", "mann", "whitney")
CONTINUOUS_TESTS = RANK_TESTS + ("t_test", "t-test", "ttest", "anova", "ancova", "mixed")
GRID = (0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5)


def _q(x):
    return ((x or {}).get("text") if isinstance(x, dict) else x) or ""


def primary_analysis(spec: dict) -> dict | None:
    an = spec.get("analyses") or []
    return next((a for a in an if a.get("primary")), an[0] if an else None)


def design(spec: dict) -> dict:
    """The stated continuous design, or status UNRESOLVED with the missing piece."""
    from .run_forward import analysis_alpha

    a = primary_analysis(spec)
    if not a:
        return {"status": "UNRESOLVED", "reason": "no primary analysis"}
    test = " ".join([str(a.get("test_family") or ""), _q(a.get("test")), _q(a.get("evidence"))]).casefold()
    if not any(t in test for t in CONTINUOUS_TESTS):
        return {"status": "UNRESOLVED", "reason": "the primary analysis is not a continuous comparison"}
    effects = [_q(e) for e in a.get("effects") or []]
    num = next((float(m.group(0)) for e in effects for m in [re.search(r"-?\d+(?:\.\d+)?", e)] if m), None)
    sd = next((float(m.group(1)) for e in effects for m in [re.search(r"(?:standard deviation|sd)\D{0,12}(\d+(?:\.\d+)?)", e, re.I)] if m), None)
    if num is None:
        return {"status": "UNRESOLVED", "reason": "no effect size stated in the primary analysis"}
    power = (a.get("power") or {}).get("value") if isinstance(a.get("power"), dict) else a.get("power")
    alpha = analysis_alpha(a)
    sizes = {x.get("quantity"): x.get("value") for x in spec.get("sample_size") or [] if x.get("value")}
    n = sizes.get("evaluable_target") or sizes.get("target_accrual") or sizes.get("maximum_accrual")
    if not n:
        return {"status": "UNRESOLVED", "reason": "no evaluable or target sample size"}
    paired = "paired" in (a.get("design_qualifiers") or []) or "signed rank" in test or "paired" in test
    rank = any(t in test for t in RANK_TESTS)
    two_sided = a.get("sidedness") != "one_sided"
    are = 3 / math.pi if rank else 1.0
    z = stats.norm.ppf(1 - alpha["value"] / (2 if two_sided else 1)) + stats.norm.ppf(power or 0.8)
    n_eff = n * are if paired else n / 2 * are
    sd_source = "stated in the protocol"
    if sd is None:
        sd = abs(num) * math.sqrt(n_eff) / z if paired else abs(num) * math.sqrt(n_eff / 2) / z
        sd_source = (f"derived from the protocol's power statement ({power:.0%} power for {num:g} at n = {n:g}, alpha "
                     f"{alpha['value']:g} {'two' if two_sided else 'one'}-sided" + (", rank test efficiency 3/pi)" if rank else ")"))
    return {"status": "RESOLVED", "analysis_id": a.get("analysis_id"), "endpoint": _q(a.get("endpoint")), "effect": num,
            "effect_wording": effects, "sd": sd, "sd_source": sd_source, "n": int(n), "paired": paired, "rank_test": rank,
            "two_sided": two_sided, "alpha": alpha, "power_stated": power}


def _test(x: np.ndarray, y: np.ndarray | None, d: dict) -> float:
    alt = "two-sided" if d["two_sided"] else "greater"
    if d["paired"]:
        return stats.wilcoxon(x, alternative=alt).pvalue if d["rank_test"] else stats.ttest_1samp(x, 0.0, alternative=alt).pvalue
    return stats.mannwhitneyu(x, y, alternative=alt).pvalue if d["rank_test"] else stats.ttest_ind(x, y, alternative=alt).pvalue


def simulate(d: dict, true_effect: float, rng: np.random.Generator, replicates: int) -> dict:
    n, sd = d["n"], d["sd"]
    ok, means = 0, []
    for _ in range(replicates):
        if d["paired"]:
            x, y = rng.normal(true_effect, sd, n), None
            mean = float(x.mean())
        else:
            x, y = rng.normal(true_effect, sd, n // 2), rng.normal(0.0, sd, n - n // 2)
            mean = float(x.mean() - y.mean())
        ok += _test(x, y, d) < d["alpha"]["value"]
        means.append(mean)
    return {"true_effect": true_effect, "p_success": ok / replicates, "observed_mean_difference": from_draws(means)}


def run(spec_lock: Path, out_dir: Path, replicates: int = 2000, seed: int = 20261006) -> dict:
    from .studyspec import load_studyspec

    spec, record = load_studyspec(spec_lock)
    d = design(spec)
    doc = {"continuous_version": CONTINUOUS_VERSION, "seed": seed, "replicates": replicates,
           "inputs": {"studyspec": record["files"]["studyspec.json"]}, "design": d}
    if d["status"] == "RESOLVED":
        rng = np.random.default_rng(seed)
        curve = [simulate(d, g * d["effect"], rng, replicates) for g in GRID]
        at_design = next(c for c in curve if c["true_effect"] == d["effect"])
        doc.update({"status": "RESOLVED", "truth": "the true mean difference is unknown: results are given over a grid of true effects",
                    "success_curve": curve, "simulated_power_at_design_effect": at_design["p_success"],
                    "design_check": {"stated_power": d["power_stated"], "simulated_power": at_design["p_success"],
                                     "consistent": d["power_stated"] is None or abs(at_design["p_success"] - d["power_stated"]) < 0.06}})
    else:
        doc.update({"status": d["status"], "reason": d["reason"]})
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "continuous_results.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    lines = [f"# Continuous primary analysis ({CONTINUOUS_VERSION})", ""]
    if doc["status"] == "RESOLVED":
        lines += [f"{'Paired' if d['paired'] else 'Two-group'} {'rank' if d['rank_test'] else 't'} test, alpha {d['alpha']['value']:g} "
                  f"({'two' if d['two_sided'] else 'one'}-sided), n = {d['n']}, design effect {d['effect']:g}, SD {d['sd']:.2f} ({d['sd_source']}).", "",
                  f"Design check: stated power {d['power_stated']}, simulated {doc['simulated_power_at_design_effect']:.3f}.", "",
                  "| true effect | P(success) | observed mean difference p10 / p30 / p50 / p70 / p90 |", "| ---: | ---: | --- |"]
        for c in curve:
            o = c["observed_mean_difference"]
            lines.append(f"| {c['true_effect']:g} | {c['p_success']:.3f} | {o['p10']:.2f} / {o['p30']:.2f} / {o['p50']:.2f} / {o['p70']:.2f} / {o['p90']:.2f} |")
    else:
        lines.append(f"{doc['status']}: {doc['reason']}")
    (out / "continuous_results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return doc
