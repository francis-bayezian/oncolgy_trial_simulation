# Per-arm binary decision rules (binary-1.0.0)

each arm's true response rate p is unknown: results are given for a grid of p (exact) and at rates the protocol cites.

Mode: decision rules.
Decision rules not executable in the StudySpec (unresolved, not simulated): ['DR1', 'DR2', 'DR3', 'DR4', 'DR5'].

## DR1 (primary): Cabozantinib (Cabozantinib)

Cohort: A phase II single-arm two-stage multicentre study. Arm status in this protocol version: ['unclear'].
Design (two_stage_other): 22 (stop if <= 7) -> 51; of interest if >= 21 responses; p0 0.3, p1 0.5.

Exact check against the protocol: type I error 0.051 (stated alpha 0.05), power 0.882 (stated 1-beta 0.8), early stop under p0 0.671 (stated None).

| true rate | P(of interest) | P(early stop) | expected enrolled | observed rate (median, 90%) |
| ---: | ---: | ---: | ---: | --- |
| 0.05 | 0.000 | 1.000 | 22.0 | 0.05 (0.00-0.14) |
| 0.10 | 0.000 | 0.999 | 22.0 | 0.09 (0.00-0.23) |
| 0.15 | 0.000 | 0.989 | 22.3 | 0.14 (0.05-0.27) |
| 0.20 | 0.000 | 0.944 | 23.6 | 0.18 (0.05-0.32) |
| 0.25 | 0.007 | 0.838 | 26.7 | 0.23 (0.09-0.33) |
| 0.30 | 0.051 | 0.671 | 31.5 | 0.27 (0.14-0.39) |
| 0.35 | 0.191 | 0.474 | 37.3 | 0.32 (0.18-0.47) |
| 0.40 | 0.438 | 0.290 | 42.6 | 0.39 (0.23-0.51) |
| 0.45 | 0.702 | 0.152 | 46.6 | 0.45 (0.27-0.57) |
| 0.50 | 0.882 | 0.067 | 49.1 | 0.51 (0.32-0.61) |
| 0.55 | 0.964 | 0.024 | 50.3 | 0.55 (0.43-0.67) |
| 0.60 | 0.991 | 0.007 | 50.8 | 0.61 (0.49-0.71) |
| 0.65 | 0.998 | 0.002 | 51.0 | 0.65 (0.53-0.75) |
| 0.70 | 1.000 | 0.000 | 51.0 | 0.71 (0.59-0.80) |

## DR2 (primary): Cabozantinib (Cabozantinib)

Cohort: The total sample size to be enrolled is 57 patients.. Arm status in this protocol version: ['unclear'].
Design (two_stage_other): 22 (stop if <= 7) -> 51; of interest if >= 21 responses; p0 0.3, p1 0.5.

Exact check against the protocol: type I error 0.051 (stated alpha 0.05), power 0.882 (stated 1-beta 0.8), early stop under p0 0.671 (stated None).

| true rate | P(of interest) | P(early stop) | expected enrolled | observed rate (median, 90%) |
| ---: | ---: | ---: | ---: | --- |
| 0.05 | 0.000 | 1.000 | 22.0 | 0.05 (0.00-0.14) |
| 0.10 | 0.000 | 0.999 | 22.0 | 0.09 (0.00-0.23) |
| 0.15 | 0.000 | 0.989 | 22.3 | 0.14 (0.05-0.27) |
| 0.20 | 0.000 | 0.944 | 23.6 | 0.18 (0.09-0.32) |
| 0.25 | 0.007 | 0.838 | 26.7 | 0.23 (0.09-0.33) |
| 0.30 | 0.051 | 0.671 | 31.5 | 0.27 (0.14-0.39) |
| 0.35 | 0.191 | 0.474 | 37.3 | 0.32 (0.18-0.45) |
| 0.40 | 0.438 | 0.290 | 42.6 | 0.39 (0.23-0.51) |
| 0.45 | 0.702 | 0.152 | 46.6 | 0.45 (0.27-0.57) |
| 0.50 | 0.882 | 0.067 | 49.1 | 0.49 (0.32-0.61) |
| 0.55 | 0.964 | 0.024 | 50.3 | 0.55 (0.43-0.67) |
| 0.60 | 0.991 | 0.007 | 50.8 | 0.61 (0.49-0.71) |
| 0.65 | 0.998 | 0.002 | 51.0 | 0.65 (0.53-0.76) |
| 0.70 | 1.000 | 0.000 | 51.0 | 0.71 (0.59-0.80) |

## DR5 (secondary): BEVACIZUMAB (PATIENTS UNDER BEVACIZUMAB)

Cohort: 19 evaluable bevacizumab pre-treated patients. Arm status in this protocol version: ['unclear'].
Design (single_stage): 19; of interest if >= 8 responses; p0 0.2, p1 0.5.

Exact check against the protocol: type I error 0.023 (stated alpha 0.025), power 0.820 (stated 1-beta 0.8), early stop under p0 0.000 (stated None).

| true rate | P(of interest) | P(early stop) | expected enrolled | observed rate (median, 90%) |
| ---: | ---: | ---: | ---: | --- |
| 0.05 | 0.000 | 0.000 | 19.0 | 0.05 (0.00-0.16) |
| 0.10 | 0.000 | 0.000 | 19.0 | 0.11 (0.00-0.21) |
| 0.15 | 0.004 | 0.000 | 19.0 | 0.16 (0.05-0.32) |
| 0.20 | 0.023 | 0.000 | 19.0 | 0.21 (0.05-0.37) |
| 0.25 | 0.077 | 0.000 | 19.0 | 0.26 (0.11-0.42) |
| 0.30 | 0.182 | 0.000 | 19.0 | 0.32 (0.11-0.47) |
| 0.35 | 0.334 | 0.000 | 19.0 | 0.37 (0.16-0.53) |
| 0.40 | 0.512 | 0.000 | 19.0 | 0.42 (0.21-0.58) |
| 0.45 | 0.683 | 0.000 | 19.0 | 0.42 (0.26-0.63) |
| 0.50 | 0.820 | 0.000 | 19.0 | 0.53 (0.32-0.68) |
| 0.55 | 0.913 | 0.000 | 19.0 | 0.58 (0.37-0.74) |
| 0.60 | 0.965 | 0.000 | 19.0 | 0.58 (0.42-0.79) |
| 0.65 | 0.989 | 0.000 | 19.0 | 0.63 (0.47-0.84) |
| 0.70 | 0.997 | 0.000 | 19.0 | 0.68 (0.53-0.84) |

