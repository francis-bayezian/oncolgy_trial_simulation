# Patient trace S0007 (arm ARM1)

Simulated patient. Each row names how it was generated: protocol (StudySpec rule or schedule), evidence (registry), parameter (fitted asset), assumption (listed in journey_summary.json).

| Day | Visit | Category | Item | Result | Clinical consequence | Basis |
| ---: | --- | --- | --- | --- | --- | --- |
| -1 | SCREENING | screening | eligibility | ELIGIBLE | 0 criteria not checkable with generated variables | protocol |
| -1 | SCREENING | baseline | demographics | age 43.65, female, white |  | evidence |
| -1 | SCREENING | laboratory | Absolute neutrophil count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -1 | SCREENING | laboratory | Platelet count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -1 | SCREENING | laboratory | Hemoglobin | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -1 | SCREENING | laboratory | ALT | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -1 | SCREENING | laboratory | Creatinine | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| 1 | C1D1 | treatment | start intrathecal_therapy | dose not compiled | first dose | protocol |
| 1 | C1D1 | treatment | start intrathecal_methotrexate | dose not compiled | first dose | protocol |
| 1 | unscheduled | adverse event | abdominal_pain | grade 1; resolves by day 8 | no protocol rule applies | parameter (A1) |
| 1 | EOT | disposition | end of treatment | completed planned procedures |  | protocol |
| 4 | unscheduled | adverse event | neutropenia | grade 2; resolves by day 11 | after treatment | parameter (A1) |
| 4 | unscheduled | laboratory | Absolute neutrophil count | 1.43 10^9/L (grade 2) | during neutropenia | assumption (A5) |
| 6 | unscheduled | adverse event | febrile_neutropenia | grade 3 serious; resolves by day 20 | after treatment | parameter (A1) |
| 6 | unscheduled | laboratory | Absolute neutrophil count | 0.62 10^9/L (grade 3) | during febrile_neutropenia | assumption (A5) |
| 11 | unscheduled | adverse event | rash_erythematous_macules_or_papules | grade 2; resolves by day 18 | after treatment | parameter (A1) |
| 13 | unscheduled | adverse event | asthenia | grade 2; resolves by day 20 | after treatment | parameter (A1) |
| 13 | unscheduled | adverse event | coughing | grade 2; resolves by day 20 | after treatment | parameter (A1) |
| 23 | unscheduled | adverse event | fever | grade 1; resolves by day 30 | after treatment | parameter (A1) |
