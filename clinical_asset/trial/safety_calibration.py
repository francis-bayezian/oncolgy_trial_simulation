"""Plausibility calibration of predicted adverse-event rates against comparable registry arms (L061).

The safety asset's event models add drug-class effects; for a multi-agent regimen the sum can predict rates no trial of
that regimen has reported. For every predicted event of an arm, the comparable registry arms are found (the same drug
classes and disease family; else the same classes; else the same family with all of these classes), at least
MIN_ARMS of them. Each comparable arm contributes its reported rate, or, when its table of that seriousness exists but
does not list the event, its reporting threshold (the most the rate can be, so the evidence is never biased upwards).
A predicted median above the 95th percentile of those arms is moved down to it (the logit mean shifts; the spread is
kept); the original prediction, the comparable arms and the reason are recorded. With too few comparable arms the
prediction is kept and the arm is reported as uncalibrated.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import special

from .. import assets

MIN_ARMS = 8
UPPER_QUANTILE = 0.95
_CACHE: dict = {}


def _norm(t: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (t or "").casefold()).strip()


def _index() -> dict:
    """Registry arms (classes, family, threshold, which tables they report) and each event's reported rates by arm."""
    if "i" in _CACHE:
        return _CACHE["i"]
    import pyarrow.parquet as pq

    arms = {}
    for a in pq.read_table(Path(assets.path("safety")) / "arms.parquet",
                           columns=["nct_id", "group", "classes", "disease_family", "threshold", "serious_table", "other_table"]).to_pylist():
        arms[(a["nct_id"], _norm(a["group"]))] = {"classes": frozenset(json.loads(a["classes"] or "[]")), "family": a["disease_family"],
                                                  "threshold": float(a["threshold"] or 5.0) / 100, "serious": bool(a["serious_table"]),
                                                  "other": bool(a["other_table"])}
    prof = {p["profile_id"]: (p["source_nct"], _norm(p["registry_group"])) for p in
            pq.read_table(Path(assets.path("asset")) / "parquet" / "profile.parquet", columns=["profile_id", "source_nct", "registry_group"]).to_pylist()}
    rates = defaultdict(dict)
    t = pq.read_table(Path(assets.path("asset")) / "parquet" / "toxicity_event.parquet", columns=["profile_id", "event_key", "kind", "rate"]).to_pydict()
    for pid, ev, kind, r in zip(t["profile_id"], t["event_key"], t["kind"], t["rate"], strict=True):
        key = prof.get(pid)
        if key in arms and r is not None:
            rates[(ev, "serious" if kind == "key_serious_events" else "other")][key] = float(r)
    _CACHE["i"] = {"arms": arms, "rates": rates}
    return _CACHE["i"]


def comparable(classes: set, family: str | None) -> tuple[list[tuple], str, float]:
    """The closest set of registry arms with at least MIN_ARMS members, and the quantile that bounds a rate there
    (95th, and 99th only for the last fallback over all registry arms)."""
    arms = _index()["arms"]
    c = frozenset(classes)
    for label, q, test in (("same drug classes and disease family", 0.95, lambda a: a["classes"] == c and a["family"] == family),
                           ("same drug classes", 0.95, lambda a: a["classes"] == c),
                           ("same disease family with all these drug classes", 0.95, lambda a: a["family"] == family and c <= a["classes"]),
                           ("same disease family", 0.95, lambda a: a["family"] == family),
                           ("all registry arms", 0.99, lambda a: True)):
        keys = [k for k, a in arms.items() if test(a)]
        if len(keys) >= MIN_ARMS:
            return keys, label, q
    return [], "fewer than %d registry arms" % MIN_ARMS, UPPER_QUANTILE


def calibrate(events: list[dict], features: dict) -> tuple[list[dict], dict]:
    """The arm's predicted events with implausible medians moved to the comparable arms' 95th percentile."""
    if not features.get("classes"):
        return events, {"status": "NOT_CALIBRATED", "reason": "no drug classes"}
    keys, level, q = comparable(set(features["classes"]), features.get("disease_family"))
    if not keys:
        return events, {"status": "NOT_CALIBRATED", "reason": level}
    idx = _index()
    moved = []
    for e in events:
        if "logit_mu" not in e:
            continue
        sev = "serious" if e.get("seriousness") == "serious" else "other"
        reported = idx["rates"].get((e["event"], sev), {})
        obs = [reported.get(k, idx["arms"][k]["threshold"]) for k in keys if idx["arms"][k][sev]]
        if len(obs) < MIN_ARMS:
            continue
        upper = float(np.quantile(obs, q))
        e["plausible_upper"] = {"rate": round(upper, 4), "quantile": q, "comparable_arms": len(obs), "level": level}
        if e["rate"] > upper and upper > 0:
            new_mu = float(special.logit(min(max(upper, 1e-4), 1 - 1e-4)))
            moved.append({"event": e["event"], "seriousness": e["seriousness"], "predicted": round(e["rate"], 4),
                          "calibrated_to": round(upper, 4), "comparable_arms": len(obs)})
            e.update({"calibrated_from": {"rate": e["rate"], "logit_mu": e["logit_mu"]}, "logit_mu": new_mu, "rate": upper,
                      "calibration": f"above the {q:.0%} percentile of {len(obs)} comparable registry arms ({level})"})
    return events, {"status": "CALIBRATED", "comparable_arms": len(keys), "level": level, "moved": moved}
