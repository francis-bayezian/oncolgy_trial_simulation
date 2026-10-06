# Per-arm binary decision rules (binary-1.0.0)

each arm's true response rate p is unknown: results are given for a grid of p (exact) and at rates the protocol cites.

Mode: decision rules.
Decision rules not executable in the StudySpec (unresolved, not simulated): ['DR2', 'DR3'].

## DR1 (primary): cediranib (30 mg) (cediranib (30 mg))

Cohort: For patients who are not newly diagnosed:. Arm status in this protocol version: ['closed'].
Design (simon_optimal): 10 (stop if <= 1) -> 22; of interest if >= 6 responses; p0 0.15, p1 0.4.

Exact check against the protocol: type I error 0.091 (stated alpha 0.1), power 0.903 (stated 1-beta 0.9), early stop under p0 0.544 (stated 0.54).

| true rate | P(of interest) | P(early stop) | expected enrolled | observed rate (median, 90%) |
| ---: | ---: | ---: | ---: | --- |
| 0.05 | 0.001 | 0.914 | 11.0 | 0.00 (0.00-0.10) |
| 0.10 | 0.016 | 0.736 | 13.2 | 0.10 (0.00-0.23) |
| 0.15 | 0.091 | 0.544 | 15.5 | 0.10 (0.00-0.27) |
| 0.20 | 0.246 | 0.376 | 17.5 | 0.18 (0.00-0.36) |
| 0.25 | 0.451 | 0.244 | 19.1 | 0.23 (0.00-0.41) |
| 0.30 | 0.650 | 0.149 | 20.2 | 0.27 (0.10-0.45) |
| 0.35 | 0.804 | 0.086 | 21.0 | 0.36 (0.10-0.55) |
| 0.40 | 0.903 | 0.046 | 21.4 | 0.41 (0.14-0.59) |
| 0.45 | 0.957 | 0.023 | 21.7 | 0.45 (0.23-0.64) |
| 0.50 | 0.983 | 0.011 | 21.9 | 0.50 (0.32-0.68) |
| 0.55 | 0.994 | 0.005 | 21.9 | 0.55 (0.36-0.73) |
| 0.60 | 0.998 | 0.002 | 22.0 | 0.59 (0.41-0.77) |
| 0.65 | 0.999 | 0.001 | 22.0 | 0.64 (0.50-0.82) |
| 0.70 | 1.000 | 0.000 | 22.0 | 0.70 (0.55-0.86) |

## DR2 (primary): sunitinib malate (37.5 mg) (sunitinib malate (37.5 mg))

Cohort: For patients who are not newly diagnosed:. Arm status in this protocol version: ['open'].
Design (simon_optimal): 10 (stop if <= 1) -> 22; of interest if >= 6 responses; p0 0.15, p1 0.4.

Exact check against the protocol: type I error 0.091 (stated alpha 0.1), power 0.903 (stated 1-beta 0.9), early stop under p0 0.544 (stated 0.54).

| true rate | P(of interest) | P(early stop) | expected enrolled | observed rate (median, 90%) |
| ---: | ---: | ---: | ---: | --- |
| 0.05 | 0.001 | 0.914 | 11.0 | 0.00 (0.00-0.14) |
| 0.10 | 0.016 | 0.736 | 13.2 | 0.10 (0.00-0.18) |
| 0.15 | 0.091 | 0.544 | 15.5 | 0.10 (0.00-0.27) |
| 0.20 | 0.246 | 0.376 | 17.5 | 0.18 (0.00-0.32) |
| 0.25 | 0.451 | 0.244 | 19.1 | 0.23 (0.00-0.41) |
| 0.30 | 0.650 | 0.149 | 20.2 | 0.27 (0.10-0.45) |
| 0.35 | 0.804 | 0.086 | 21.0 | 0.36 (0.10-0.50) |
| 0.40 | 0.903 | 0.046 | 21.4 | 0.41 (0.18-0.59) |
| 0.45 | 0.957 | 0.023 | 21.7 | 0.45 (0.27-0.64) |
| 0.50 | 0.983 | 0.011 | 21.9 | 0.50 (0.32-0.68) |
| 0.55 | 0.994 | 0.005 | 21.9 | 0.55 (0.36-0.73) |
| 0.60 | 0.998 | 0.002 | 22.0 | 0.59 (0.45-0.77) |
| 0.65 | 0.999 | 0.001 | 22.0 | 0.64 (0.50-0.82) |
| 0.70 | 1.000 | 0.000 | 22.0 | 0.68 (0.55-0.86) |

## DR3 (primary): cediranib (30 mg) (cediranib (30 mg))

Cohort: newly diagnosed ASPS cohort. Arm status in this protocol version: ['closed'].
Design (simon_minimax): 8 (stop if <= 1) -> 11; of interest if >= 4 responses; p0 0.15, p1 0.45.

Exact check against the protocol: type I error 0.068 (stated alpha 0.1), power 0.804 (stated 1-beta 0.8), early stop under p0 0.657 (stated 0.66).

| true rate | P(of interest) | P(early stop) | expected enrolled | observed rate (median, 90%) |
| ---: | ---: | ---: | ---: | --- |
| 0.05 | 0.002 | 0.943 | 8.2 | 0.00 (0.00-0.18) |
| 0.10 | 0.018 | 0.813 | 8.6 | 0.12 (0.00-0.27) |
| 0.15 | 0.068 | 0.657 | 9.0 | 0.12 (0.00-0.36) |
| 0.20 | 0.158 | 0.503 | 9.5 | 0.12 (0.00-0.45) |
| 0.25 | 0.283 | 0.367 | 9.9 | 0.18 (0.00-0.45) |
| 0.30 | 0.425 | 0.255 | 10.2 | 0.27 (0.00-0.55) |
| 0.35 | 0.569 | 0.169 | 10.5 | 0.36 (0.12-0.55) |
| 0.40 | 0.698 | 0.106 | 10.7 | 0.36 (0.12-0.64) |
| 0.45 | 0.804 | 0.063 | 10.8 | 0.45 (0.12-0.73) |
| 0.50 | 0.883 | 0.035 | 10.9 | 0.55 (0.27-0.73) |
| 0.55 | 0.936 | 0.018 | 10.9 | 0.55 (0.27-0.82) |
| 0.57 | 0.953 | 0.013 | 11.0 | 0.55 (0.27-0.82) |
| 0.60 | 0.969 | 0.009 | 11.0 | 0.64 (0.36-0.82) |
| 0.65 | 0.987 | 0.004 | 11.0 | 0.64 (0.45-0.91) |
| 0.70 | 0.995 | 0.001 | 11.0 | 0.73 (0.45-0.91) |

Conditional on the rate the protocol cites (F079: 0.57): P(of interest) = 0.953.

## DR4 (primary): sunitinib malate (37.5 mg) (sunitinib malate (37.5 mg))

Cohort: newly diagnosed ASPS cohort. Arm status in this protocol version: ['open'].
Design (simon_minimax): 8 (stop if <= 1) -> 11 (stop if <= 1); of interest if >= 4 responses; p0 0.15, p1 0.45.

Exact check against the protocol: type I error 0.068 (stated alpha 0.1), power 0.804 (stated 1-beta 0.8), early stop under p0 0.657 (stated 0.66).

| true rate | P(of interest) | P(early stop) | expected enrolled | observed rate (median, 90%) |
| ---: | ---: | ---: | ---: | --- |
| 0.05 | 0.002 | 0.943 | 8.2 | 0.00 (0.00-0.13) |
| 0.10 | 0.018 | 0.813 | 8.6 | 0.12 (0.00-0.27) |
| 0.15 | 0.068 | 0.657 | 9.0 | 0.12 (0.00-0.36) |
| 0.20 | 0.158 | 0.503 | 9.5 | 0.12 (0.00-0.36) |
| 0.25 | 0.283 | 0.367 | 9.9 | 0.18 (0.00-0.45) |
| 0.30 | 0.425 | 0.255 | 10.2 | 0.27 (0.00-0.55) |
| 0.35 | 0.569 | 0.169 | 10.5 | 0.36 (0.12-0.64) |
| 0.40 | 0.698 | 0.106 | 10.7 | 0.36 (0.12-0.64) |
| 0.45 | 0.804 | 0.063 | 10.8 | 0.45 (0.12-0.73) |
| 0.50 | 0.883 | 0.035 | 10.9 | 0.45 (0.27-0.73) |
| 0.55 | 0.936 | 0.018 | 10.9 | 0.55 (0.27-0.82) |
| 0.60 | 0.969 | 0.009 | 11.0 | 0.64 (0.36-0.82) |
| 0.65 | 0.987 | 0.004 | 11.0 | 0.64 (0.45-0.91) |
| 0.70 | 0.995 | 0.001 | 11.0 | 0.73 (0.45-0.91) |

