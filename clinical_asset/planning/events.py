"""Calendar-time event accumulation under an explicitly supplied accrual and survival scenario."""

import numpy as np


def simulate_cure_calendar(target_n: int, rate_year: float, survival: dict, dropout: dict,
                           thresholds: list[int], draws: int = 5000, seed: int = 20260927,
                           hr: float = 1.0, by_month: int = 36) -> dict:
    if target_n < 1 or rate_year <= 0 or hr <= 0 or draws < 100:
        raise ValueError("Positive target, rate, HR and at least 100 draws required")
    if survival.get("family") != "cure_model" or survival.get("status") != "RESOLVED":
        raise ValueError("Event calendar requires a resolved cure-model survival distribution")
    pi = float(survival["cure_fraction"])
    lam = float(survival["failure_rate_per_year"])
    censor = float(dropout.get("rate_per_year") or 0)
    if not (0 <= pi < 1 and lam > 0 and censor >= 0):
        raise ValueError("Invalid survival or dropout parameters")
    rng = np.random.default_rng(seed)
    crossing = {n: [] for n in thresholds}
    by_date = {n: 0 for n in thresholds}
    counts_at_date = []
    for _ in range(draws):
        enrollment = np.cumsum(rng.exponential(12 / rate_year, target_n))
        enrollment -= enrollment[0]  # calendar origin is first patient in
        u = rng.random(target_n)
        event_years = np.full(target_n, np.inf)
        susceptible = u > pi ** hr
        residual = (np.power(u[susceptible], 1 / hr) - pi) / (1 - pi)
        event_years[susceptible] = -np.log(residual) / lam
        censor_years = rng.exponential(1 / censor, target_n) if censor else np.full(target_n, np.inf)
        observed = event_years < censor_years
        dates = np.sort(enrollment[observed] + event_years[observed] * 12)
        counts_at_date.append(int(np.searchsorted(dates, by_month, side="right")))
        for n in thresholds:
            if len(dates) >= n:
                crossing[n].append(float(dates[n - 1]))
                by_date[n] += dates[n - 1] <= by_month
    result = {}
    for n in thresholds:
        values = crossing[n]
        result[str(n)] = {"reach_probability": len(values) / draws,
                          "month_from_first_patient": {"median": float(np.median(values)),
                            "pi80": [float(x) for x in np.quantile(values, [.1, .9])]}
                          if values else None,
                          f"probability_by_month_{by_month}": by_date[n] / draws}
    return {"draws": draws, "seed": seed, "target_enrollment": target_n, "rate_per_year": rate_year,
            "hr": hr, "thresholds": result,
            "event_count_at_month": {"month": by_month, "median": float(np.median(counts_at_date)),
                                     "pi80": [float(x) for x in np.quantile(counts_at_date, [.1, .9])]},
            "conditioning": "All target patients enroll; homogeneous Poisson arrivals; proportional-hazards cure model; "
                            "independent exponential loss to follow-up; no site activation or administrative stop"}
