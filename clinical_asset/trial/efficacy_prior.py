"""Evidence-based prediction of a binary efficacy endpoint (response-type proportions) for a protocol arm.

The protocol's own assumptions (p0, p1, a cited rate) are hypotheses. Next to them, this gives what the evidence build
predicts for a NEW study of the arm: the future-study predictive draws of Simulation Parameter Asset V3 (hierarchical,
leave-one-study-out calibrated) for the endpoint in the arm's disease family, at the deepest matching context:

  regimen       the same set of agents in the same disease family;
  class         otherwise, a mixture of every published context with the same drug-class combination in the family;
  family        otherwise, a mixture of every published context of the endpoint in the family.

The level used is always reported. No match at any level: UNRESOLVED (no borrowing across disease families).
The protocol's endpoint is mapped to the asset's endpoint variables by the evidence build's model mapper (cached).
"""

import json
from pathlib import Path

import numpy as np

ASSET = Path("data/simulation_parameters_v3/proportions")
ENDPOINT_TARGETS = Path("data/spa_work/endpoint_targets.json")
RESPONSE_TARGETS = ("objective_response_rate", "complete_response", "pathological_complete_response", "disease_control_rate",
                    "clinical_benefit_rate", "psa_response")


def endpoint_target(name: str, model=None, cache_file: Path = ENDPOINT_TARGETS) -> str | None:
    """The asset endpoint variable of a protocol endpoint ('objective response rate' -> objective_response_rate)."""
    cache = json.loads(Path(cache_file).read_text(encoding="utf-8")) if Path(cache_file).exists() else {}
    key = " ".join((name or "").split()).casefold()
    if key and key not in cache and model is not None:
        from ..spa2.taxonomy import _map

        labels = list(RESPONSE_TARGETS) + ["none"]
        found = _map(model, "endpoint_target",
                     "Assign each trial endpoint (item = its name as written) to the matching endpoint variable from labels: the "
                     "proportion of patients with that outcome. Use none when the endpoint is not one of these proportions (a "
                     "time-to-event endpoint, a continuous measure, toxicity, feasibility). Give confidence between 0 and 1.",
                     [{"item": key}], labels)
        cache[key] = found.get(key) or {"label": "none", "confidence": 0.0}
        Path(cache_file).parent.mkdir(parents=True, exist_ok=True)
        Path(cache_file).write_text(json.dumps(cache, indent=1, ensure_ascii=False), encoding="utf-8")
    hit = cache.get(key)
    return hit["label"] if hit and hit["label"] != "none" and (hit.get("confidence") or 0) >= 0.7 else None


def _contexts(target: str, family: str) -> list[dict]:
    import pyarrow.parquet as pq

    rows = pq.read_table(ASSET / "parameter_index.parquet").to_pylist()
    return [r for r in rows if r["status"] == "PUBLISHED" and r["target_variable"] == target and r["context_disease_family"] == family]


def _draws(parameter_ids: list[str]) -> dict[str, np.ndarray]:
    import pyarrow.parquet as pq

    t = pq.read_table(ASSET / "posterior_draws.parquet", filters=[("parameter_id", "in", parameter_ids)],
                      columns=["parameter_id", "future_study"]).to_pylist()
    out: dict[str, list] = {}
    for r in t:
        out.setdefault(r["parameter_id"], []).append(r["future_study"])
    return {k: np.array(v, dtype=float) for k, v in out.items()}


def arm_prior(target: str, family: str, agents: list[str], classes: list[str]) -> dict:
    """Future-study predictive draws of the endpoint proportion for the arm, at the deepest matching level."""
    ctx = _contexts(target, family)
    agent_set = {a.casefold() for a in agents if a}
    signature = "+".join(sorted(classes))

    def regimen_of(r):
        return {x.strip().casefold() for x in (r["context_regimen"] or "").split("+") if x.strip()}
    levels = [("regimen", [r for r in ctx if agent_set and regimen_of(r) == agent_set]),
              ("class", [r for r in ctx if signature and r["context_class_signature"] == signature]),
              ("family", ctx)]
    for level, chosen in levels:
        if chosen:
            draws = _draws([r["parameter_id"] for r in chosen])
            pooled = np.concatenate([draws[r["parameter_id"]] for r in chosen if r["parameter_id"] in draws]) if draws else np.array([])
            if pooled.size:
                q = np.quantile(pooled, [0.05, 0.1, 0.5, 0.9, 0.95])
                return {"status": "RESOLVED", "level": level, "target": target, "family": family, "contexts": len(chosen),
                        "regimens": sorted({r["context_regimen"] for r in chosen})[:12], "studies": int(sum(int(r["studies"]) for r in chosen)),
                        "rate": {"median": float(q[2]), "q05": float(q[0]), "q10": float(q[1]), "q90": float(q[3]), "q95": float(q[4])},
                        "draws": pooled}
    return {"status": "UNRESOLVED", "reason": f"no published {target} context in the {family} family", "target": target, "family": family}


def observed_interval(draws: np.ndarray, n: int, rng: np.random.Generator, level: float = 0.90) -> tuple[float, float]:
    """Predictive interval of the OBSERVED rate among n patients: rate uncertainty and binomial sampling."""
    x = rng.binomial(n, rng.choice(draws, size=20000)) / n
    return float(np.quantile(x, (1 - level) / 2)), float(np.quantile(x, 1 - (1 - level) / 2))
