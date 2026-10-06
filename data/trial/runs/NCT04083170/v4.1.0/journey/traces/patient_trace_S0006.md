# Patient trace S0006 (arm ARM2)

Simulated patient. Each row names how it was generated: protocol (StudySpec rule or schedule), evidence (registry), parameter (fitted asset), assumption (listed in journey_summary.json).

| Day | Visit | Category | Item | Result | Clinical consequence | Basis |
| ---: | --- | --- | --- | --- | --- | --- |
| -1 | SCREENING | screening | eligibility | ELIGIBLE | 0 criteria not checkable with generated variables | protocol |
| -1 | SCREENING | baseline | demographics | age 60.69, female, white |  | evidence |
| -1 | SCREENING | laboratory | Absolute neutrophil count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -1 | SCREENING | laboratory | Platelet count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -1 | SCREENING | laboratory | Hemoglobin | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -1 | SCREENING | laboratory | ALT | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -1 | SCREENING | laboratory | Creatinine | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| 1 | C1D1 | treatment | start intrathecal_therapy | dose not compiled | first dose | protocol |
| 1 | C1D1 | treatment | start intrathecal_methotrexate | dose not compiled | first dose | protocol |
| 1 | EOT | disposition | end of treatment | completed planned procedures |  | protocol |
| 3 | unscheduled | adverse event | diarrhea | grade 1; resolves by day 10 | after treatment | parameter (A1) |
| 9 | unscheduled | adverse event | blood_bilirubin_increased | grade 1; resolves by day 16 | after treatment | parameter (A1) |
| 9 | unscheduled | laboratory | Total bilirubin | 1.11 x ULN (grade 1) | during blood_bilirubin_increased | assumption (A5) |
| 13 | unscheduled | adverse event | hyperphosphatemia_disorder | grade 1; resolves by day 20 | after treatment | parameter (A1) |
| 14 | unscheduled | adverse event | epistaxis | grade 2; resolves by day 21 | after treatment | parameter (A1) |
| 16 | unscheduled | adverse event | rash_erythematous_macules_or_papules | grade 1; resolves by day 23 | after treatment | parameter (A1) |
| 22 | unscheduled | adverse event | nausea | grade 2; resolves by day 29 | after treatment | parameter (A1) |
| 22 | unscheduled | adverse event | febrile_neutropenia | grade 2; resolves by day 29 | after treatment | parameter (A1) |
| 22 | unscheduled | laboratory | Absolute neutrophil count | 1.36 10^9/L (grade 2) | during febrile_neutropenia | assumption (A5) |
