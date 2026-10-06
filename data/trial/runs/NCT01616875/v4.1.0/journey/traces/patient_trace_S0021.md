# Patient trace S0021 (arm ARM1)

Simulated patient. Each row names how it was generated: protocol (StudySpec rule or schedule), evidence (registry), parameter (fitted asset), assumption (listed in journey_summary.json).

| Day | Visit | Category | Item | Result | Clinical consequence | Basis |
| ---: | --- | --- | --- | --- | --- | --- |
| -7 | SCREENING | screening | eligibility | ELIGIBLE | 0 criteria not checkable with generated variables | protocol (A13) |
| -7 | SCREENING | baseline | demographics | age 62.81, male, white |  | evidence |
| -7 | SCREENING | laboratory | Absolute neutrophil count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -7 | SCREENING | laboratory | Platelet count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -7 | SCREENING | laboratory | Hemoglobin | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -7 | SCREENING | laboratory | ALT | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -7 | SCREENING | laboratory | Creatinine | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| 1 | C1D1 | treatment | start cabazitaxel | 15 mg/m2 | first dose | protocol |
| 1 | C1D1 | treatment | start cisplatin | 70 mg/m2 | first dose | protocol |
| 5 | C2D1 | adverse event | myalgia | grade 2; resolves by day 22 | no protocol rule applies | parameter (A1) |
| 12 | C2D1 | adverse event | decreased_platelet_count | grade 1; resolves by day 22 | no protocol rule applies | parameter (A1) |
| 13 | C2D1 | adverse event | alopecia | grade 1; resolves by day 22 | no protocol rule applies | parameter (A1) |
| 19 | C2D1 | adverse event | creatinine | grade 1; resolves by day 22 | undecidable: DM017 | parameter (A1) |
| 21 | C2D1 | adverse event | fever | grade 1; resolves by day 22 | no protocol rule applies | parameter (A1) |
| 24 | C3D1 | adverse event | anorexia | grade 2; resolves by day 43 | no protocol rule applies | parameter (A1) |
| 26 | C3D1 | adverse event | vomiting | grade 1; resolves by day 43 | no protocol rule applies | parameter (A1) |
| 28 | C3D1 | adverse event | weight_loss | grade 2; resolves by day 43 | no protocol rule applies | parameter (A1) |
| 32 | C3D1 | adverse event | sleeplessness | grade 1; resolves by day 43 | no protocol rule applies | parameter (A1) |
| 36 | C3D1 | adverse event | hyperglycemia | grade 1; resolves by day 43 | no protocol rule applies | parameter (A1) |
| 36 | C3D1 | adverse event | alanine_aminotransferase_increased | grade 1; resolves by day 43 | no protocol rule applies | parameter (A1) |
| 36 | C3D1 | laboratory | ALT | 2.44 x ULN (grade 1) | during alanine_aminotransferase_increased | assumption (A5) |
| 53 | C4D1 | adverse event | hyponatremia | grade 2; resolves by day 64 | no protocol rule applies | parameter (A1) |
| 69 | unscheduled | adverse event | back_pain | grade 2; resolves by day 76 | no protocol rule applies | parameter (A1) |
| 75 | unscheduled | adverse event | edema | grade 1; resolves by day 82 | no protocol rule applies | parameter (A1) |
| 84 | EOT | disposition | end of treatment | completed planned treatment |  | protocol |
| 85 | unscheduled | adverse event | peripheral_edema | grade 2; resolves by day 92 | after treatment | parameter (A1) |
| 96 | unscheduled | adverse event | diarrhea | grade 1; resolves by day 103 | after treatment | parameter (A1) |
| 100 | unscheduled | adverse event | rash_erythematous_macules_or_papules | grade 1; resolves by day 107 | after treatment | parameter (A1) |
| 102 | unscheduled | adverse event | rash/desquamation | grade 1; resolves by day 109 | after treatment | parameter (A1) |
| 108 | unscheduled | adverse event | neuropathy:_sensory | grade 2; resolves by day 115 | after treatment | parameter (A1) |
| 110 | unscheduled | adverse event | anemia | grade 2; resolves by day 117 | after treatment | parameter (A1) |
| 110 | unscheduled | laboratory | Hemoglobin | 9.03 g/dL (grade 2) | during anemia | assumption (A5) |
