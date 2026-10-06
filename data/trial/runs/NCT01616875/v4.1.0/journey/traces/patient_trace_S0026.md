# Patient trace S0026 (arm ARM1)

Simulated patient. Each row names how it was generated: protocol (StudySpec rule or schedule), evidence (registry), parameter (fitted asset), assumption (listed in journey_summary.json).

| Day | Visit | Category | Item | Result | Clinical consequence | Basis |
| ---: | --- | --- | --- | --- | --- | --- |
| -7 | SCREENING | screening | eligibility | ELIGIBLE | 0 criteria not checkable with generated variables | protocol (A13) |
| -7 | SCREENING | baseline | demographics | age 74.71, male, white |  | evidence |
| -7 | SCREENING | laboratory | Absolute neutrophil count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -7 | SCREENING | laboratory | Platelet count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -7 | SCREENING | laboratory | Hemoglobin | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -7 | SCREENING | laboratory | ALT | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -7 | SCREENING | laboratory | Creatinine | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| 1 | C1D1 | treatment | start cabazitaxel | 15 mg/m2 | first dose | protocol |
| 1 | C1D1 | treatment | start cisplatin | 70 mg/m2 | first dose | protocol |
| 8 | C2D1 | adverse event | vomiting | grade 1; resolves by day 22 | no protocol rule applies | parameter (A1) |
| 18 | C2D1 | adverse event | decreased_platelet_count | grade 1; resolves by day 22 | no protocol rule applies | parameter (A1) |
| 21 | C2D1 | adverse event | white_blood_cell_decreased | grade 1; resolves by day 22 | no protocol rule applies | parameter (A1) |
| 21 | C2D1 | laboratory | White blood cell count | 3.92 10^9/L (grade 1) | during white_blood_cell_decreased | assumption (A5) |
| 22 | C2D1 | adverse event | anorexia | grade 1; resolves by day 43 | no protocol rule applies | parameter (A1) |
| 22 | C2D1 | adverse event | creatinine | grade 1; resolves by day 43 | undecidable: DM017 | parameter (A1) |
| 24 | C3D1 | adverse event | hyperglycemia | grade 1; resolves by day 43 | no protocol rule applies | parameter (A1) |
| 26 | C3D1 | adverse event | leukopenia | grade 1; resolves by day 43 | no protocol rule applies | parameter (A1) |
| 26 | C3D1 | laboratory | White blood cell count | 3.3 10^9/L (grade 1) | during leukopenia | assumption (A5) |
| 28 | C3D1 | adverse event | alanine_aminotransferase_increased | grade 1; resolves by day 43 | no protocol rule applies | parameter (A1) |
| 28 | C3D1 | laboratory | ALT | 2.35 x ULN (grade 1) | during alanine_aminotransferase_increased | assumption (A5) |
| 38 | C3D1 | adverse event | pain_other | grade 1; resolves by day 43 | no protocol rule applies | parameter (A1) |
| 38 | C3D1 | adverse event | rash_erythematous_macules_or_papules | grade 2; resolves by day 43 | no protocol rule applies | parameter (A1) |
| 45 | C4D1 | adverse event | abdominal_pain | grade 2; resolves by day 64 | no protocol rule applies | parameter (A1) |
| 47 | C4D1 | adverse event | weight_loss | grade 1; resolves by day 64 | no protocol rule applies | parameter (A1) |
| 56 | unscheduled | tumour assessment | progression | progressive disease | no tumour assessment schedule resolved: recorded at its true time | assumption |
| 56 | EOT | disposition | end of treatment | disease progression |  | protocol |
| 62 | C4D1 | adverse event | hypomagnesemia | grade 1; resolves by day 64 | after treatment | parameter (A1) |
| 62 | C4D1 | adverse event | peripheral_edema | grade 1; resolves by day 64 | after treatment | parameter (A1) |
| 64 | C4D1 | adverse event | neuropathy:_sensory | grade 2; resolves by day 71 | after treatment | parameter (A1) |
| 64 | C4D1 | adverse event | aspartate_aminotransferase_increased | grade 2; resolves by day 71 | after treatment | parameter (A1) |
| 64 | C4D1 | laboratory | AST | 4.03 x ULN (grade 2) | during aspartate_aminotransferase_increased | assumption (A5) |
| 72 | unscheduled | adverse event | rash/desquamation | grade 1; resolves by day 79 | after treatment | parameter (A1) |
| 76 | unscheduled | adverse event | myalgia | grade 1; resolves by day 83 | after treatment | parameter (A1) |
| 80 | unscheduled | adverse event | fever | grade 2; resolves by day 87 | after treatment | parameter (A1) |
| 84 | unscheduled | adverse event | dehydration | grade 3 serious; resolves by day 98 | after treatment | parameter (A1) |
| 104 | follow-up | disposition | death | died during follow-up |  | evidence (A15) |
