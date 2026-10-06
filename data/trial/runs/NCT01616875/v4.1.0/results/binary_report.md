# Per-arm binary decision rules (binary-1.0.0)

each arm's true response rate p is unknown: results are given for a grid of p (exact) and at rates the protocol cites.

Mode: decision rules.
Decision rules not executable in the StudySpec (unresolved, not simulated): ['DR1'].

## DR1 (primary): Cabazitaxel 15 mg/m2 day 1 + cisplatin 70mg/ m2 day 1 (Four cycles of chemotherapy using a combination regimen
comprising:
Cabazitaxel 15 mg/m2 day 1 + cisplatin 70mg/ m2 day 1. The
combination treatment is prescribed every 21 days.)

Cohort: 26 patients. Arm status in this protocol version: ['open'].
Design (two_stage_other): 9 (stop if <= 0) -> 26; of interest if >= 14 responses; p0 0.35, p1 0.6.

Exact check against the protocol: type I error 0.038 (stated alpha 0.05), power 0.801 (stated 1-beta 0.8), early stop under p0 0.021 (stated None).

| true rate | P(of interest) | P(early stop) | expected enrolled | observed rate (median, 90%) |
| ---: | ---: | ---: | ---: | --- |
| 0.05 | 0.000 | 0.630 | 15.3 | 0.00 (0.00-0.12) |
| 0.10 | 0.000 | 0.387 | 19.4 | 0.08 (0.00-0.19) |
| 0.15 | 0.000 | 0.232 | 22.1 | 0.15 (0.00-0.27) |
| 0.20 | 0.000 | 0.134 | 23.7 | 0.19 (0.00-0.35) |
| 0.25 | 0.002 | 0.075 | 24.7 | 0.23 (0.00-0.38) |
| 0.30 | 0.009 | 0.040 | 25.3 | 0.31 (0.12-0.46) |
| 0.35 | 0.038 | 0.021 | 25.6 | 0.35 (0.19-0.50) |
| 0.40 | 0.108 | 0.010 | 25.8 | 0.38 (0.23-0.54) |
| 0.45 | 0.238 | 0.005 | 25.9 | 0.46 (0.31-0.62) |
| 0.50 | 0.422 | 0.002 | 26.0 | 0.50 (0.35-0.65) |
| 0.55 | 0.626 | 0.001 | 26.0 | 0.54 (0.38-0.69) |
| 0.60 | 0.801 | 0.000 | 26.0 | 0.62 (0.46-0.77) |
| 0.65 | 0.917 | 0.000 | 26.0 | 0.65 (0.50-0.81) |
| 0.70 | 0.974 | 0.000 | 26.0 | 0.69 (0.54-0.85) |

