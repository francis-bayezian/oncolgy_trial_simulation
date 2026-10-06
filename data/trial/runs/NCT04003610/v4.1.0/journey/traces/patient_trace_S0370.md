# Patient trace S0370 (arm ARM4)

Simulated patient. Each row names how it was generated: protocol (StudySpec rule or schedule), evidence (registry), parameter (fitted asset), assumption (listed in journey_summary.json).

| Day | Visit | Category | Item | Result | Clinical consequence | Basis |
| ---: | --- | --- | --- | --- | --- | --- |
| -35 | SCREENING | screening | eligibility | ELIGIBLE | 0 criteria not checkable with generated variables | protocol (A13) |
| -35 | SCREENING | baseline | demographics | age 58.38, male, white |  | evidence |
| -35 | SCREENING | laboratory | Absolute neutrophil count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -35 | SCREENING | laboratory | Platelet count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -35 | SCREENING | laboratory | Hemoglobin | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -35 | SCREENING | laboratory | ALT | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -35 | SCREENING | laboratory | Creatinine | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| 1 | C1D1 | treatment | start pembrolizumab | 200 mg | first dose | protocol |
| 1 | C1D1 | treatment | start gemcitabine | 1000 mg/m2 | first dose | protocol |
| 1 | C1D1 | treatment | start carboplatin | 5 auc | first dose | protocol |
| 8 | C1D8 | adverse event | diarrhea | grade 2; resolves by day 9 | pembrolizumab held until day 9 (DM026) | parameter (A1) |
| 12 | C1D12 | adverse event | pruritus | grade 1; resolves by day 13 | no protocol rule applies | parameter (A1) |
| 13 | C1D13 | adverse event | other serious adverse events (not individually predicted) | grade 3 serious; resolves by day 15 | no protocol rule applies | parameter (A1) |
| 18 | C1D18 | adverse event | headache | grade 1; resolves by day 19 | no protocol rule applies | parameter (A1) |
| 21 | C1D21 | adverse event | nasal_congestion_finding | grade 2; resolves by day 22 | no protocol rule applies | parameter (A1) |
| 23 | C2D2 | adverse event | arthralgia | grade 1; resolves by day 24 | no protocol rule applies | parameter (A1) |
| 25 | C2D4 | adverse event | urinary_tract_infection | grade 2; resolves by day 26 | no protocol rule applies | parameter (A1) |
| 25 | C2D4 | adverse event | dysuria | grade 2; resolves by day 26 | no protocol rule applies | parameter (A1) |
| 39 | C2D18 | adverse event | sleeplessness | grade 1; resolves by day 40 | no protocol rule applies | parameter (A1) |
| 50 | C3D8 | adverse event | alanine_aminotransferase_increased | grade 2; resolves by day 51 | pembrolizumab held until day 51 (DM028) | parameter (A1) |
| 50 | C3D8 | laboratory | ALT | 3.48 x ULN (grade 2) | during alanine_aminotransferase_increased | assumption (A5) |
| 51 | C3D9 | adverse event | hypocalcemia | grade 1; resolves by day 52 | no protocol rule applies | parameter (A1) |
| 60 | C3D18 | adverse event | decrease_in_appetite | grade 1; resolves by day 61 | no protocol rule applies | parameter (A1) |
| 61 | C3D19 | adverse event | fever | grade 1; resolves by day 62 | no protocol rule applies | parameter (A1) |
| 64 | TA1 | tumour assessment | RECIST / protocol response criteria | progressive disease | progression detected: treatment ends | evidence |
| 64 | EOT | disposition | end of treatment | disease progression |  | protocol |
| 67 | C4D4 | adverse event | hypoalbuminemia | grade 2; resolves by day 68 | after treatment | parameter (A1) |
| 80 | C4D17 | adverse event | increased_frequency_of_micturition | grade 2; resolves by day 81 | after treatment | parameter (A1) |
| 81 | C4D18 | adverse event | dyspnea | grade 2; resolves by day 82 | after treatment | parameter (A1) |
| 90 | TA2 | adverse event | blood_creatinine_increased | grade 2; resolves by day 127 | after treatment | parameter (A1) |
| 90 | TA2 | laboratory | Creatinine | 2.67 x ULN (grade 2) | during blood_creatinine_increased | assumption (A5) |
| 91 | TA2 | adverse event | hypertension_variable | grade 2; resolves by day 127 | after treatment | parameter (A1) |
| 148 | FU1 | follow-up | follow-up visit | attended |  | protocol |
