# Patient trace S0161 (arm ARM3)

Simulated patient. Each row names how it was generated: protocol (StudySpec rule or schedule), evidence (registry), parameter (fitted asset), assumption (listed in journey_summary.json).

| Day | Visit | Category | Item | Result | Clinical consequence | Basis |
| ---: | --- | --- | --- | --- | --- | --- |
| -28 | SCREENING | screening | eligibility | ELIGIBLE | 0 criteria not checkable with generated variables | protocol (A13) |
| -28 | SCREENING | baseline | demographics | age 65.07, female, white |  | evidence |
| -28 | SCREENING | laboratory | Absolute neutrophil count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | Platelet count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | Hemoglobin | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | ALT | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | Creatinine | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| 1 | C1D1 | treatment | start ensartinib | 225 mg | first dose | protocol |
| 23 | C2D1 | adverse event | decreased_platelet_count | grade 1; resolves by day 29 | ensartinib continued (DM014) | parameter (A1) |
| 57 | TA1 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | assumption (A7) |
| 64 | C4D1 | adverse event | blood_alkaline_phosphatase_increased | grade 2; resolves by day 85 | ensartinib continued (DM014) | parameter (A1) |
| 82 | C4D1 | adverse event | coughing | grade 2; resolves by day 85 | ensartinib continued (DM014) | parameter (A1) |
| 92 | C5D1 | adverse event | abdomen_distended | grade 1; resolves by day 113 | ensartinib continued (DM014) | parameter (A1) |
| 113 | TA2 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | assumption (A7) |
| 131 | C6D1 | adverse event | hypocalcemia | grade 2; resolves by day 141 | ensartinib continued (DM014) | parameter (A1) |
| 135 | C6D1 | adverse event | creatinine_renal_clearance_decreased | grade 1; resolves by day 141 | ensartinib continued (DM014) | parameter (A1) |
| 140 | C6D1 | adverse event | chest_pain | grade 2; resolves by day 141 | ensartinib continued (DM014) | parameter (A1) |
| 169 | TA3 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | assumption (A7) |
| 174 | C8D1 | adverse event | amylase_increased | grade 1; resolves by day 197 | ensartinib continued (DM014) | parameter (A1) |
| 213 | C9D1 | adverse event | fatigue | grade 2; resolves by day 225 | ensartinib continued (DM014) | parameter (A1) |
| 225 | TA4 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | assumption (A7) |
| 233 | C10D1 | adverse event | nausea | grade 2; resolves by day 253 | ensartinib continued (DM014) | parameter (A1) |
| 241 | C10D1 | adverse event | constipation | grade 1; resolves by day 253 | ensartinib continued (DM014) | parameter (A1) |
| 277 | C11D1 | adverse event | lipase_increased | grade 1; resolves by day 281 | ensartinib continued (DM014) | parameter (A1) |
| 281 | TA5 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | assumption (A7) |
| 293 | C12D1 | adverse event | edema | grade 2; resolves by day 309 | ensartinib continued (DM014) | parameter (A1) |
| 330 | C13D1 | adverse event | peripheral_edema | grade 2; resolves by day 337 | ensartinib continued (DM014) | parameter (A1) |
| 330 | C13D1 | adverse event | peripheral_edema | grade 3 serious; resolves by day 365 | undecidable: DM015 | parameter (A1) |
| 337 | C13D1 | adverse event | upper_respiratory_infections | grade 1; resolves by day 365 | ensartinib continued (DM014) | parameter (A1) |
| 337 | TA6 | tumour assessment | RECIST / protocol response criteria | progressive disease | progression detected: treatment ends | assumption (A7) |
| 337 | EOT | disposition | end of treatment | disease progression |  | protocol |
| 367 | FU1 | follow-up | follow-up visit | attended |  | protocol |
