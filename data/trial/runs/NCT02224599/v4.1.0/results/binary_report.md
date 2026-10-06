# Per-arm binary decision rules (binary-1.0.0)

each arm's true response rate p is unknown: results are given for a grid of p (exact) and at rates the protocol cites.

Mode: decision rules.


## DR1 (primary): Phase I/II Study of Low Dose Cyclophosphamide, Tumor Associated Peptide
Antigen-Pulsed Dendritic Cell Therapy and Imiquimod (Patients will receive five (5) days of low-dose cyclophosphamide prior to each vaccination
with TAPA-pulsed DCs to decrease Treg activity. TAPA-pulsed DCs will be administered
at a fixed dose of up to 1 X 107 DCs following cyclophosphamide administration. DC
vaccination schedule will be once every seven (7) days via intradermal (ID) injections for
a total of 3 vaccinations. Topical Imiquimod will also be administered once after the
TAPA-pulsed DC vaccination, to optimize immune responses.)

Cohort: total of 17 patients. Arm status in this protocol version: ['open'].
Design (two_stage_other): 6 (stop if <= 0) -> 17; of interest if >= 3 responses; p0 0.05, p1 0.35.

Exact check against the protocol: type I error 0.039 (stated alpha 0.05), power 0.907 (stated 1-beta 0.9), early stop under p0 0.735 (stated None).

| true rate | P(of interest) | P(early stop) | expected enrolled | observed rate (median, 90%) |
| ---: | ---: | ---: | ---: | --- |
| 0.05 | 0.039 | 0.735 | 8.9 | 0.00 (0.00-0.12) |
| 0.10 | 0.191 | 0.531 | 11.2 | 0.00 (0.00-0.24) |
| 0.15 | 0.397 | 0.377 | 12.9 | 0.12 (0.00-0.29) |
| 0.20 | 0.590 | 0.262 | 14.1 | 0.18 (0.00-0.35) |
| 0.25 | 0.739 | 0.178 | 15.0 | 0.24 (0.00-0.41) |
| 0.30 | 0.842 | 0.118 | 15.7 | 0.29 (0.00-0.47) |
| 0.35 | 0.907 | 0.075 | 16.2 | 0.35 (0.00-0.53) |
| 0.40 | 0.947 | 0.047 | 16.5 | 0.41 (0.12-0.59) |
| 0.45 | 0.970 | 0.028 | 16.7 | 0.47 (0.24-0.65) |
| 0.50 | 0.984 | 0.016 | 16.8 | 0.53 (0.29-0.71) |
| 0.55 | 0.992 | 0.008 | 16.9 | 0.53 (0.35-0.76) |
| 0.60 | 0.996 | 0.004 | 17.0 | 0.59 (0.41-0.76) |
| 0.65 | 0.998 | 0.002 | 17.0 | 0.65 (0.47-0.82) |
| 0.70 | 0.999 | 0.001 | 17.0 | 0.71 (0.53-0.88) |

## DR2 (secondary): Phase I/II Study of Low Dose Cyclophosphamide, Tumor Associated Peptide
Antigen-Pulsed Dendritic Cell Therapy and Imiquimod (Patients will receive five (5) days of low-dose cyclophosphamide prior to each vaccination
with TAPA-pulsed DCs to decrease Treg activity. TAPA-pulsed DCs will be administered
at a fixed dose of up to 1 X 107 DCs following cyclophosphamide administration. DC
vaccination schedule will be once every seven (7) days via intradermal (ID) injections for
a total of 3 vaccinations. Topical Imiquimod will also be administered once after the
TAPA-pulsed DC vaccination, to optimize immune responses.)

Cohort: up to six (6) consecutive subjects. Arm status in this protocol version: ['open'].
Design (single_stage): 6; of interest if >= 5 responses; p0 None, p1 None.

| true rate | P(of interest) | P(early stop) | expected enrolled | observed rate (median, 90%) |
| ---: | ---: | ---: | ---: | --- |
| 0.05 | 0.967 | 0.000 | 6.0 | 1.00 (0.83-1.00) |
| 0.10 | 0.886 | 0.000 | 6.0 | 1.00 (0.67-1.00) |
| 0.15 | 0.776 | 0.000 | 6.0 | 0.83 (0.50-1.00) |
| 0.20 | 0.655 | 0.000 | 6.0 | 0.83 (0.50-1.00) |
| 0.25 | 0.534 | 0.000 | 6.0 | 0.83 (0.50-1.00) |
| 0.30 | 0.420 | 0.000 | 6.0 | 0.67 (0.33-1.00) |
| 0.35 | 0.319 | 0.000 | 6.0 | 0.67 (0.33-1.00) |
| 0.40 | 0.233 | 0.000 | 6.0 | 0.67 (0.33-0.83) |
| 0.45 | 0.164 | 0.000 | 6.0 | 0.50 (0.17-0.83) |
| 0.50 | 0.109 | 0.000 | 6.0 | 0.50 (0.17-0.83) |
| 0.55 | 0.069 | 0.000 | 6.0 | 0.50 (0.17-0.83) |
| 0.60 | 0.041 | 0.000 | 6.0 | 0.33 (0.17-0.67) |
| 0.65 | 0.022 | 0.000 | 6.0 | 0.33 (0.00-0.67) |
| 0.70 | 0.011 | 0.000 | 6.0 | 0.33 (0.00-0.67) |

