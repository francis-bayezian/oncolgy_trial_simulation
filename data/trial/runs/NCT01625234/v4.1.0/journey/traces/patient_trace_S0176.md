# Patient trace S0176 (arm ARM3)

Simulated patient. Each row names how it was generated: protocol (StudySpec rule or schedule), evidence (registry), parameter (fitted asset), assumption (listed in journey_summary.json).

| Day | Visit | Category | Item | Result | Clinical consequence | Basis |
| ---: | --- | --- | --- | --- | --- | --- |
| -28 | SCREENING | screening | eligibility | ELIGIBLE | 0 criteria not checkable with generated variables | protocol (A13) |
| -28 | SCREENING | baseline | demographics | age 62.13, male, white |  | evidence |
| -28 | SCREENING | laboratory | Absolute neutrophil count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | Platelet count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | Hemoglobin | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | ALT | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | Creatinine | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| 1 | C1D1 | treatment | start ensartinib | 225 mg | first dose | protocol |
| 18 | C2D1 | adverse event | hypocalcemia | grade 2; resolves by day 29 | ensartinib continued (DM014) | parameter (A1) |
| 25 | C2D1 | adverse event | creatinine_renal_clearance_decreased | grade 2; resolves by day 29 | ensartinib continued (DM014) | parameter (A1) |
| 57 | TA1 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | assumption (A7) |
| 106 | C5D1 | adverse event | hemoptysis | grade 1; resolves by day 113 | ensartinib continued (DM014) | parameter (A1) |
| 113 | TA2 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | assumption (A7) |
| 125 | C6D1 | adverse event | fever | grade 1; resolves by day 141 | ensartinib continued (DM014) | parameter (A1) |
| 135 | C6D1 | adverse event | abdomen_distended | grade 2; resolves by day 141 | ensartinib continued (DM014) | parameter (A1) |
| 169 | TA3 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | assumption (A7) |
| 225 | TA4 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | assumption (A7) |
| 281 | TA5 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | assumption (A7) |
| 292 | C12D1 | adverse event | chest_pain | grade 1; resolves by day 309 | ensartinib continued (DM014) | parameter (A1) |
| 300 | C12D1 | adverse event | decreased_platelet_count | grade 1; resolves by day 309 | ensartinib continued (DM014) | parameter (A1) |
| 337 | TA6 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | assumption (A7) |
| 367 | C15D1 | adverse event | blood_alkaline_phosphatase_increased | grade 2; resolves by day 393 | ensartinib continued (DM014) | parameter (A1) |
| 393 | TA7 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | assumption (A7) |
| 415 | C16D1 | adverse event | fatigue | grade 2; resolves by day 421 | ensartinib continued (DM014) | parameter (A1) |
| 449 | TA8 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | assumption (A7) |
| 505 | TA9 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | assumption (A7) |
| 548 | C21D1 | adverse event | anemia | grade 1; resolves by day 561 | ensartinib continued (DM014) | parameter (A1) |
| 548 | C21D1 | laboratory | Hemoglobin | 11.56 g/dL (grade 1) | during anemia | assumption (A5) |
| 561 | C21D1 | adverse event | constipation | grade 2; resolves by day 589 | ensartinib continued (DM014) | parameter (A1) |
| 561 | TA10 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | assumption (A7) |
| 580 | C22D1 | adverse event | pruritus | grade 2; resolves by day 589 | ensartinib continued (DM014) | parameter (A1) |
| 617 | TA11 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | assumption (A7) |
| 634 | C24D1 | adverse event | amylase_increased | grade 1; resolves by day 645 | ensartinib continued (DM014) | parameter (A1) |
| 673 | C25D1 | adverse event | lipase_increased | grade 1; resolves by day 701 | ensartinib continued (DM014) | parameter (A1) |
| 673 | TA12 | tumour assessment | RECIST / protocol response criteria | progressive disease | progression detected: treatment ends | assumption (A7) |
| 673 | EOT | disposition | end of treatment | disease progression |  | protocol |
| 691 | C26D1 | adverse event | edema | grade 2; resolves by day 701 | after treatment | parameter (A1) |
| 703 | FU1 | follow-up | follow-up visit | attended |  | protocol |
