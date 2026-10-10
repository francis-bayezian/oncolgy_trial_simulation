"""Milestone 3D: protocol conditioning and the synthetic baseline generator.

A protocol is described by a canonical query (disease, disease family, setting, eligibility age
range, sex eligibility, allowed categories). Retrieval walks each baseline hierarchy to the
deepest node that exists for the query, adds between-context deviations for the levels that are
new, and reports how far it had to extrapolate and how much evidence stands behind the result.

generate_baseline_population(protocol, n_patients, posterior_draw=None, ...) then samples
patients:

* expected-world mode (default, posterior_draw=None): parameters at their posterior expectation
  for the context; no trial-level randomness beyond patient sampling;
* uncertainty mode (posterior_draw=int or "random"): one joint posterior draw of all parameters,
  so the trial-level parameters theta_trial are drawn once per trial; with future_study=True a
  new-study deviation (between-study heterogeneity) is added once per trial as well.

Eligibility is applied by direct conditional sampling: ages from the latent age distribution
truncated to the protocol range (quantile function, stable far in the tails), categorical
variables renormalised over the allowed categories. The Gaussian copula couples these
conditional marginals; its correlation matrix is sparse and evidence based (identity where no
within-patient evidence exists). The share of the retrieved population that meets the
protocol's eligibility is reported, and flagged when the protocol lies outside the evidence.
"""

import json
import re
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from scipy import special, stats

from .baseline import age_class

CONTEXT_AXES = ("disease_family", "disease", "setting")


@dataclass
class ProtocolQuery:
    disease: str | None = None
    disease_family: str | None = None
    setting: str | None = None
    min_age: float | None = None
    max_age: float | None = None
    sex: str = "ALL"                                    # ALL, FEMALE or MALE
    allowed_categories: dict = field(default_factory=dict)  # variable -> list of allowed categories
    label: str | None = None
    age_class: str | None = None  # optional override, e.g. 'less than 22 years' is the PEDIATRIC class '<= 21 years'

    def canonical(self, disease_family_map: dict | None = None) -> dict:
        family = self.disease_family
        if family is None and self.disease and disease_family_map:
            entry = disease_family_map.get(self.disease)
            if entry and entry.get("confidence", 0) >= 0.7:
                family = entry["label"]
        sex = (self.sex or "ALL").upper()
        if sex not in {"ALL", "FEMALE", "MALE"}:
            raise ValueError(f"unknown sex eligibility {self.sex!r}")
        if self.min_age is not None and self.max_age is not None and self.min_age >= self.max_age:
            raise ValueError("min_age must be below max_age")
        return {"disease_family": family or "__unknown__", "disease": self.disease or "__unknown__",
                "setting": self.setting or "__unknown__", "min_age": self.min_age, "max_age": self.max_age,
                "age_class": self.age_class or age_class(self.min_age, self.max_age), "sex": sex,
                "allowed_categories": {k: list(v) for k, v in (self.allowed_categories or {}).items()}, "label": self.label}


# ----------------------------------------------------------------------------- target models


@dataclass
class TargetModel:
    name: str
    kind: str                 # "binomial" (logit scale) or "gaussian"
    levels: list[str]         # full hierarchy levels
    context_levels: list[str]  # levels up to the parameter level
    nodes: dict               # path tuple -> {"draws": (D,), "studies": int, "N": int}
    tau: np.ndarray           # (D, L)
    root: np.ndarray          # (D,)
    centre: float = 0.0
    meta: dict = field(default_factory=dict)


def target_from_binomial(name: str, fit, records: list[dict], context_levels: list[str], meta: dict | None = None) -> TargetModel:
    stop = len(context_levels)
    stats_ = _node_support(records, fit.levels, stop)
    nodes = {k: {"draws": fit.node_draws[i].astype("float32"), **stats_[k]} for k, i in fit.tree.index.items() if len(k) <= stop}
    return TargetModel(name, "binomial", fit.levels, context_levels, nodes, fit.tau_draws, fit.root_draws, 0.0, meta or {})


def target_from_gaussian(name: str, fit, records: list[dict], context_levels: list[str], centre: float, meta: dict | None = None) -> TargetModel:
    stop = len(context_levels)
    stats_ = _node_support(records, fit.levels, stop)
    nodes = {k: {"draws": v.astype("float32"), **stats_[k]} for k, v in fit.node_draws.items() if len(k) <= stop}
    return TargetModel(name, "gaussian", fit.levels, context_levels, nodes, fit.tau_draws, fit.root_draws, centre, meta or {})


def _node_support(records: list[dict], levels: list[str], stop: int) -> dict:
    out: dict = {}
    for r in records:
        path = tuple(r[lv] for lv in levels)
        for d in range(1, stop + 1):
            e = out.setdefault(path[:d], {"studies": set(), "N": 0})
            e["studies"].add(r["study"])
            e["N"] += int(r.get("n") or 0)
    return {k: {"studies": len(v["studies"]), "N": v["N"], "study_ids": sorted(v["studies"])} for k, v in out.items()}


def _tokens(text: str) -> set:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def query_path(model: TargetModel, q: dict) -> tuple:
    """The query's context path, each level's value resolved to the model's own name for it: the same name in another
    letter case, else the name of the same parent sharing most words (Jaccard at least 0.6; most studies on a tie).
    An unresolved value stays as given (a new context: its between-context spread is added, L067)."""
    path: list = []
    for level in model.context_levels:
        v = q[level]
        names = {k[len(path)] for k in model.nodes if len(k) == len(path) + 1 and list(k[:len(path)]) == path}
        if v not in names and v and v != "__unknown__":
            same = [n for n in names if str(n).lower() == str(v).lower()]
            if same:
                v = same[0]
            else:
                tv = _tokens(v)
                scored = [(len(tv & _tokens(n)) / len(tv | _tokens(n)), model.nodes[(*path, n)]["studies"], n) for n in names if tv | _tokens(n)]
                best = max(scored, default=None)
                if best and best[0] >= 0.6:
                    v = best[2]
        path.append(v)
    return tuple(path)


def retrieve(model: TargetModel, q: dict, draws: int | None = None, seed: int = 0) -> dict:
    """Context-level draws (analysis scale) for the query, with extrapolation and support."""
    path = query_path(model, q)
    known = 0
    for d in range(len(path), 0, -1):
        if path[:d] in model.nodes:
            known = d
            break
    rng = np.random.default_rng(seed)
    base = model.root if known == 0 else model.nodes[path[:known]]["draws"].astype(float)
    theta = base.copy()
    for level in range(known, len(path)):  # new context levels: add between-context deviations
        theta = theta + model.tau[:, level] * rng.standard_normal(theta.size)
    missing = [model.context_levels[i] for i in range(known, len(path))]
    extrapolation = sum(1 for m in missing if m in CONTEXT_AXES) + (1 if "age_class" in missing else 0)
    direct = model.nodes.get(path) if known == len(path) else None
    # studies the estimate borrows from: the parent of an exact match, else the deepest known node
    parent_key = path[: known - 1] if (direct is not None and known > 1) else path[:known]
    parent = model.nodes.get(parent_key) if parent_key else None
    direct_ids = set(direct["study_ids"]) if direct else set()
    borrowed = len(set(parent["study_ids"]) - direct_ids) if parent else sum(n["studies"] for k, n in model.nodes.items() if len(k) == 1)
    natural = special.expit(theta) if model.kind == "binomial" else theta + model.centre
    var = float(np.var(natural))
    if model.kind == "binomial":
        pm = float(np.mean(natural))
        effective = pm * (1 - pm) / var if var > 0 else math.inf
    else:
        within = float(model.meta.get("within_variance") or 1.0)
        effective = within / var if var > 0 else math.inf
    return {
        "theta": theta, "study_tau": model.tau[:, len(model.context_levels)] if len(model.levels) > len(model.context_levels) else np.zeros_like(theta),
        "matched_path": list(path[:known]), "matched_level": model.context_levels[known - 1] if known else "root",
        "missing_levels": missing, "extrapolation_level": int(min(extrapolation, 4)),
        "support": {"direct_studies": direct["studies"] if direct else 0, "direct_N": direct["N"] if direct else 0,
                    "borrowed_parent_studies": int(borrowed),
                    "effective_information": float(effective),
                    "effective_information_unit": "patient-equivalent N (outcome variance / posterior variance of the context parameter)"},
    }


# ----------------------------------------------------------------------------- persistence


def save_models(models: dict[str, TargetModel], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    node_rows, hyper_rows, meta = [], [], {}
    for name, m in models.items():
        meta[name] = {"kind": m.kind, "levels": m.levels, "context_levels": m.context_levels, "centre": m.centre, "meta": m.meta}
        for path, node in m.nodes.items():
            node_rows.append({"target": name, "path": json.dumps(list(path)), "level": m.levels[len(path) - 1],
                              "studies": node["studies"], "N": node["N"], "study_ids": json.dumps(node["study_ids"]),
                              "draws": node["draws"].astype("float32").tolist()})
        for d in range(m.root.size):
            hyper_rows.append({"target": name, "draw": d, "root": float(m.root[d]), "tau": m.tau[d].astype(float).tolist()})
    pq.write_table(pa.Table.from_pylist(node_rows), out_dir / "baseline_node_draws.parquet")
    pq.write_table(pa.Table.from_pylist(hyper_rows), out_dir / "baseline_hyperparameter_draws.parquet")
    (out_dir / "baseline_models.json").write_text(json.dumps(meta, indent=1, default=str), encoding="utf-8")


def load_models(out_dir: Path) -> dict[str, TargetModel]:
    meta = json.loads((out_dir / "baseline_models.json").read_text(encoding="utf-8"))
    nodes: dict[str, dict] = {k: {} for k in meta}
    for r in pq.read_table(out_dir / "baseline_node_draws.parquet").to_pylist():
        nodes[r["target"]][tuple(json.loads(r["path"]))] = {"draws": np.array(r["draws"], "float32"), "studies": r["studies"],
                                                            "N": r["N"], "study_ids": json.loads(r["study_ids"])}
    hyper: dict[str, list] = {k: [] for k in meta}
    for r in pq.read_table(out_dir / "baseline_hyperparameter_draws.parquet").to_pylist():
        hyper[r["target"]].append(r)
    models = {}
    for name, m in meta.items():
        h = sorted(hyper[name], key=lambda r: r["draw"])
        models[name] = TargetModel(name, m["kind"], m["levels"], m["context_levels"], nodes[name],
                                   np.array([r["tau"] for r in h]), np.array([r["root"] for r in h]), m["centre"], m["meta"])
    return models


# ----------------------------------------------------------------------------- generator


@dataclass
class BaselineGenerator:
    models: dict[str, TargetModel]
    categorical: dict            # variable -> {"categories": [...], "steps": [target names]}
    copula: dict                 # {"variables": [...], "R": [[...]], "labels": ...}
    disease_family_map: dict = field(default_factory=dict)

    @classmethod
    def load(cls, root: Path | None = None) -> "BaselineGenerator":
        if root is None:                       # the V3 build in force (an as-of-T0 build under an evidence cut-off)
            from ..cutoff import asset
            root = asset("v3") / "baseline"
        spec = json.loads((root / "generator_spec.json").read_text(encoding="utf-8"))
        families_path = Path(spec.get("disease_family_map", ""))
        families = json.loads(families_path.read_text(encoding="utf-8")) if families_path.is_file() else {}
        return cls(load_models(root), spec["categorical"], json.loads((root / "copula.json").read_text(encoding="utf-8")), families)

    def parameters(self, protocol: ProtocolQuery | dict, posterior_draw=None, future_study: bool = True, seed: int = 0) -> dict:
        """Trial-level parameters for the protocol (expected world or one posterior draw)."""
        q = protocol.canonical(self.disease_family_map) if isinstance(protocol, ProtocolQuery) else protocol
        rng = np.random.default_rng(seed)
        retrieved = {name: retrieve(m, q, seed=seed + i) for i, (name, m) in enumerate(sorted(self.models.items()))}
        d_total = min(r["theta"].size for r in retrieved.values())
        if posterior_draw == "random":
            posterior_draw = int(rng.integers(d_total))
        mode = "expected_world" if posterior_draw is None else "uncertainty_propagating"

        def value(name: str) -> float:
            r, m = retrieved[name], self.models[name]
            theta = r["theta"]
            if posterior_draw is None:
                nat = special.expit(theta) if m.kind == "binomial" else theta + m.centre
                return float(np.mean(nat))
            t = theta[posterior_draw % theta.size]
            if future_study:  # new-study deviation drawn once per trial
                t = t + r["study_tau"][posterior_draw % theta.size] * rng.standard_normal()
            return float(special.expit(t)) if m.kind == "binomial" else float(t + m.centre)

        params = {"mode": mode, "posterior_draw": posterior_draw, "future_study_effect": bool(future_study and posterior_draw is not None),
                  "query": q}
        if "age_mean" in self.models:
            params["age_latent_mean"] = value("age_mean")
            params["age_latent_sd"] = math.exp(value("age_sd"))
        if "sex_female" in self.models:
            params["p_female"] = value("sex_female")
        for variable, spec in self.categorical.items():
            conditional = np.array([[value(step)] for step in spec["steps"]])
            remaining, probs = 1.0, []
            for c in conditional[:, 0]:
                probs.append(remaining * c)
                remaining *= 1 - c
            probs.append(remaining)
            params[f"{variable}_probabilities"] = dict(zip(spec["categories"], map(float, probs), strict=True))
        params["retrieval"] = {name: {k: v for k, v in r.items() if k not in {"theta", "study_tau"}} for name, r in retrieved.items()}
        params["extrapolation_level"] = max(r["extrapolation_level"] for r in retrieved.values())
        return params

    def sample(self, params: dict, n_patients: int, seed: int = 0) -> dict:
        """Patients for the trial-level parameters. Eligibility is applied to each marginal by
        direct conditional sampling (age from the latent age distribution truncated to the
        protocol range via its quantile function; categorical variables renormalised over the
        allowed categories), and the Gaussian copula couples these conditional marginals."""
        q = params["query"]
        rng = np.random.default_rng(seed + 7919)
        variables = self.copula["variables"]
        z = rng.multivariate_normal(np.zeros(len(variables)), np.array(self.copula["R"]), size=n_patients, method="eigh")
        u = np.clip(stats.norm.cdf(z), 1e-12, 1 - 1e-12)
        out = {"patient_id": list(range(n_patients))}
        for i, v in enumerate(variables):
            if v == "age" and "age_latent_mean" in params:
                mu, sd = params["age_latent_mean"], params["age_latent_sd"]
                lo = q["min_age"] if q["min_age"] is not None else 0.0
                hi = q["max_age"] if q["max_age"] is not None else 120.0
                a, b = (lo - mu) / sd, (hi - mu) / sd
                out["age"] = stats.truncnorm.ppf(u[:, i], a, b, loc=mu, scale=sd).round(2).tolist()
            elif v == "sex" and "p_female" in params:
                p = params["p_female"]
                allowed = {"ALL": ["female", "male"], "FEMALE": ["female"], "MALE": ["male"]}[q["sex"]]
                cats, cum = _renormalise({"female": p, "male": 1 - p}, allowed)
                out["sex"] = [cats[k] for k in np.searchsorted(cum, u[:, i], side="right").clip(0, len(cats) - 1)]
            elif f"{v}_probabilities" in params:
                probs = params[f"{v}_probabilities"]
                cats, cum = _renormalise(probs, q["allowed_categories"].get(v, list(probs)))
                out[v] = [cats[k] for k in np.searchsorted(cum, u[:, i], side="right").clip(0, len(cats) - 1)]
        return out


def eligibility_support(params: dict) -> dict:
    """Probability that a patient from the retrieved (untruncated) population meets the protocol's
    eligibility. Very small values mean the protocol lies outside the evidence for this context."""
    q = params["query"]
    out = {}
    if "age_latent_mean" in params:
        mu, sd = params["age_latent_mean"], params["age_latent_sd"]
        lo = q["min_age"] if q["min_age"] is not None else 0.0
        hi = q["max_age"] if q["max_age"] is not None else 120.0
        out["age"] = float(max(stats.norm.cdf(hi, mu, sd) - stats.norm.cdf(lo, mu, sd), 0.0))
    if "p_female" in params:
        out["sex"] = {"ALL": 1.0, "FEMALE": params["p_female"], "MALE": 1 - params["p_female"]}[q["sex"]]
    for key, probs in params.items():
        if key.endswith("_probabilities"):
            variable = key[: -len("_probabilities")]
            allowed = q["allowed_categories"].get(variable, list(probs))
            out[variable] = float(sum(probs[c] for c in allowed if c in probs))
    out["joint_if_independent"] = float(np.prod(list(out.values()))) if out else 1.0
    out["flag"] = "PROTOCOL_OUTSIDE_EVIDENCE" if out.get("joint_if_independent", 1.0) < 1e-3 else "OK"
    return out


def _renormalise(probs: dict, allowed: list[str]) -> tuple[list[str], np.ndarray]:
    cats = [c for c in probs if c in set(allowed)]
    if not cats:
        raise ValueError(f"no allowed categories among {list(probs)}")
    p = np.array([probs[c] for c in cats], float)
    p = p / p.sum()
    return cats, np.cumsum(p)


_DEFAULT: BaselineGenerator | None = None


def generate_baseline_population(protocol: ProtocolQuery | dict, n_patients: int, posterior_draw=None,
                                 future_study: bool = True, seed: int = 0, generator: BaselineGenerator | None = None) -> dict:
    """Synthetic baseline cohort for a protocol.

    posterior_draw=None gives the expected world; an integer (or "random") selects one joint
    posterior draw so the trial's parameters are drawn once per trial, with a new-study
    deviation when future_study is true. Returns patients plus the parameters, retrieval path,
    extrapolation level and evidence support that produced them."""
    global _DEFAULT
    if generator is None:
        if _DEFAULT is None:
            _DEFAULT = BaselineGenerator.load()
        generator = _DEFAULT
    if isinstance(protocol, dict):
        protocol = ProtocolQuery(**protocol)
    params = generator.parameters(protocol, posterior_draw, future_study, seed)
    patients = generator.sample(params, n_patients, seed)
    return {"patients": patients, "parameters": {k: v for k, v in params.items() if k != "query"},
            "eligibility_support": eligibility_support(params),
            "protocol": params["query"], "copula": {"variables": generator.copula["variables"],
                                                     "nonzero_offdiagonal": generator.copula.get("nonzero_offdiagonal", 0)},
            "protocol_input": asdict(protocol)}
