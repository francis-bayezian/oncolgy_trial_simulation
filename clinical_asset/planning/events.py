"""Planning: calendar timelines by simulation (accrual, loss to follow-up, event maturity, analysis triggers).

One planning world draws arrival times (Poisson process at an accrual rate), and for a time-to-event protocol each
patient's event time (the locked outcome model at a stated true effect) and loss to follow-up. From many worlds:

* first patient in -> last patient in (enrollment duration);
* time to each stated event count (event maturity) and the probability that it is reached by a given date;
* time to the protocol's analysis trigger (for example 'N evaluable patients enrolled and followed for Y years');
* study completion (last patient's off-study limit).

Accrual rates come from the caller: a rate the protocol states, or a draw from the historical accrual model. The
outcome model is used only at an effect the caller states (no effect, or a design hypothesis): the timing of events
depends on the true effect, which is unknown, and every result says which effect it assumes.
"""

import numpy as np

DAY = 365.25


def _quantiles(v: np.ndarray, probs=(0.1, 0.25, 0.5, 0.75, 0.9)) -> dict:
    v = v[np.isfinite(v)]
    if len(v) == 0:
        return {"reached_in": 0.0}
    return {"median": float(np.median(v)), **{f"q{int(p * 100):02d}": float(np.quantile(v, p)) for p in probs if p != 0.5}}


def enrollment_worlds(n: int, rates_per_year: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Arrival days of n patients in each world (one accrual rate per world); shape (worlds, n)."""
    gaps = rng.exponential(1.0, size=(len(rates_per_year), n)) * (DAY / rates_per_year)[:, None]
    return np.cumsum(gaps, axis=1)


def timelines(n_enrolled: int, rates_per_year: np.ndarray, rng: np.random.Generator, outcome: dict | None = None,
              hr: float = 1.0, event_targets: tuple[int, ...] = (), analysis_rule: dict | None = None,
              loss_rate_per_year: float = 0.0, off_study_days: float | None = None, deadlines_years: tuple[float, ...] = ()) -> dict:
    """Calendar distributions over worlds; times are years from the first patient in."""
    worlds = len(rates_per_year)
    arrive = enrollment_worlds(n_enrolled, rates_per_year, rng)
    arrive -= arrive[:, :1]                                           # time 0 = first patient in
    last = np.full(worlds, n_enrolled - 1)
    trigger = None
    if analysis_rule and analysis_rule.get("evaluable_target"):
        # accrual stops when the Nth evaluable patient enrolls (excluded share drawn per patient); the analysis follows
        # after the minimum follow-up
        excl = analysis_rule.get("excluded_share") or 0.0
        evaluable = rng.random((worlds, n_enrolled)) >= excl
        reached = np.cumsum(evaluable, axis=1) >= int(analysis_rule["evaluable_target"])
        last = np.where(reached.any(axis=1), reached.argmax(axis=1), n_enrolled - 1)
        trigger = np.where(reached.any(axis=1), arrive[np.arange(worlds), last] / DAY + (analysis_rule.get("min_followup_years") or 0), np.inf)
    lpi = arrive[np.arange(worlds), last] / DAY
    enrolled = np.arange(n_enrolled)[None, :] <= last[:, None]
    out = {"assumed": {"patients_max": n_enrolled, "worlds": worlds, "hr": hr if outcome else None},
           "enrolled": _quantiles((last + 1).astype(float)),
           "last_patient_in_years": _quantiles(lpi),
           "p_enrollment_complete_by": {f"{d:g}y": float(np.mean(lpi <= d)) for d in deadlines_years}}
    if trigger is not None:
        out["primary_analysis_years"] = _quantiles(trigger)
        out["p_primary_analysis_by"] = {f"{d:g}y": float(np.mean(trigger <= d)) for d in deadlines_years}
    if outcome and event_targets:
        from ..trial.outcomes import sample_efs_years

        event_days = np.stack([sample_efs_years(n_enrolled, outcome, hr, rng) for _ in range(worlds)]) * DAY
        loss = rng.exponential(DAY / loss_rate_per_year, size=(worlds, n_enrolled)) if loss_rate_per_year > 0 else np.full((worlds, n_enrolled), np.inf)
        limit = off_study_days if off_study_days else np.inf
        observed = np.where(enrolled & (event_days <= loss) & (event_days <= limit), arrive + event_days, np.inf) / DAY
        observed.sort(axis=1)
        out["event_maturity"] = {}
        for k in event_targets:
            t = observed[:, k - 1] if k <= n_enrolled else np.full(worlds, np.inf)
            out["event_maturity"][str(k)] = {**_quantiles(t), "p_reached_ever": float(np.mean(np.isfinite(t))),
                                             "p_reached_by": {f"{d:g}y": float(np.mean(t <= d)) for d in deadlines_years}}
    if off_study_days:
        out["study_completion_years"] = _quantiles(lpi + off_study_days / DAY)
    return out
