# Patient trace S0002 (arm ARM1)

Simulated patient. Each row names how it was generated: protocol (StudySpec rule or schedule), evidence (registry), parameter (fitted asset), assumption (listed in journey_summary.json).

| Day | Visit | Category | Item | Result | Clinical consequence | Basis |
| ---: | --- | --- | --- | --- | --- | --- |
| -7 | SCREENING | screening | eligibility | ELIGIBLE | 0 criteria not checkable with generated variables | protocol (A13) |
| -7 | SCREENING | baseline | demographics | age 56.15, male, white |  | evidence |
| -7 | SCREENING | laboratory | Absolute neutrophil count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -7 | SCREENING | laboratory | Platelet count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -7 | SCREENING | laboratory | Hemoglobin | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -7 | SCREENING | laboratory | ALT | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -7 | SCREENING | laboratory | Creatinine | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| 1 | C1D1 | treatment | start cabazitaxel | 15 mg/m2 | first dose | protocol |
| 1 | C1D1 | treatment | start cisplatin | 70 mg/m2 | first dose | protocol |
| 4 | C2D1 | adverse event | creatinine | grade 2; resolves by day 22 | undecidable: DM017 | parameter (A1) |
| 5 | C2D1 | adverse event | decreased_platelet_count | grade 2; resolves by day 22 | no protocol rule applies | parameter (A1) |
| 10 | C2D1 | adverse event | back_pain | grade 1; resolves by day 22 | no protocol rule applies | parameter (A1) |
| 22 | C2D1 | adverse event | anorexia | grade 1; resolves by day 43 | no protocol rule applies | parameter (A1) |
| 23 | C3D1 | adverse event | rash_erythematous_macules_or_papules | grade 1; resolves by day 43 | no protocol rule applies | parameter (A1) |
| 26 | C3D1 | adverse event | vomiting | grade 2; resolves by day 43 | no protocol rule applies | parameter (A1) |
| 30 | C3D1 | adverse event | myalgia | grade 1; resolves by day 43 | no protocol rule applies | parameter (A1) |
| 33 | C3D1 | adverse event | white_blood_cell_decreased | grade 2; resolves by day 43 | no protocol rule applies | parameter (A1) |
| 33 | C3D1 | laboratory | White blood cell count | 2.27 10^9/L (grade 2) | during white_blood_cell_decreased | assumption (A5) |
| 34 | C3D1 | adverse event | hair_loss/alopecia_(scalp_or_body) | grade 1; resolves by day 43 | no protocol rule applies | parameter (A1) |
| 49 | C4D1 | adverse event | hypomagnesemia | grade 1; resolves by day 64 | no protocol rule applies | parameter (A1) |
| 51 | C4D1 | adverse event | dizziness | grade 1; resolves by day 64 | no protocol rule applies | parameter (A1) |
| 54 | C4D1 | adverse event | edema | grade 1; resolves by day 64 | no protocol rule applies | parameter (A1) |
| 55 | C4D1 | adverse event | hyperglycemia | grade 1; resolves by day 64 | no protocol rule applies | parameter (A1) |
| 63 | C4D1 | adverse event | constipation | grade 2; resolves by day 64 | no protocol rule applies | parameter (A1) |
| 66 | unscheduled | adverse event | dehydration | grade 3 serious; resolves by day 80 | no protocol rule applies | parameter (A1) |
| 67 | unscheduled | adverse event | alanine_aminotransferase_increased | grade 1; resolves by day 74 | no protocol rule applies | parameter (A1) |
| 67 | unscheduled | laboratory | ALT | 2.91 x ULN (grade 1) | during alanine_aminotransferase_increased | assumption (A5) |
| 74 | unscheduled | adverse event | rash/desquamation | grade 2; resolves by day 81 | no protocol rule applies | parameter (A1) |
| 84 | EOT | disposition | end of treatment | completed planned treatment |  | protocol |
| 102 | unscheduled | adverse event | hyponatremia | grade 2; resolves by day 109 | after treatment | parameter (A1) |
| 103 | unscheduled | adverse event | alopecia | grade 1; resolves by day 110 | after treatment | parameter (A1) |
| 106 | unscheduled | adverse event | fever | grade 1; resolves by day 113 | after treatment | parameter (A1) |
| 112 | unscheduled | adverse event | leukopenia | grade 2; resolves by day 119 | after treatment | parameter (A1) |
| 112 | unscheduled | laboratory | White blood cell count | 2.68 10^9/L (grade 2) | during leukopenia | assumption (A5) |
