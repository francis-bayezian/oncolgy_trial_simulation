# Patient trace S0044 (arm ARM3)

Simulated patient. Each row names how it was generated: protocol (StudySpec rule or schedule), evidence (registry), parameter (fitted asset), assumption (listed in journey_summary.json).

| Day | Visit | Category | Item | Result | Clinical consequence | Basis |
| ---: | --- | --- | --- | --- | --- | --- |
| -28 | SCREENING | screening | eligibility | ELIGIBLE | 0 criteria not checkable with generated variables | protocol (A13) |
| -28 | SCREENING | baseline | demographics | age 76.33, female, white |  | evidence |
| -28 | SCREENING | laboratory | Absolute neutrophil count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | Platelet count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | Hemoglobin | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | ALT | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | Creatinine | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| 1 | C1D1 | treatment | start ensartinib | 225 mg | first dose | protocol |
| 12 | C2D1 | adverse event | amylase_increased | grade 1; resolves by day 29 | ensartinib continued (DM014) | parameter (A1) |
| 19 | C2D1 | adverse event | hyponatremia | grade 2; resolves by day 29 | ensartinib continued (DM014) | parameter (A1) |
| 44 | C3D1 | adverse event | lipase_increased | grade 1; resolves by day 57 | ensartinib continued (DM014) | parameter (A1) |
| 57 | TA1 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | assumption (A7) |
| 94 | C5D1 | adverse event | chest_pain | grade 1; resolves by day 113 | ensartinib continued (DM014) | parameter (A1) |
| 113 | TA2 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | assumption (A7) |
| 126 | C6D1 | adverse event | back_pain | grade 1; resolves by day 141 | ensartinib continued (DM014) | parameter (A1) |
| 139 | C6D1 | adverse event | blood_alkaline_phosphatase_increased | grade 1; resolves by day 141 | ensartinib continued (DM014) | parameter (A1) |
| 169 | TA3 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | assumption (A7) |
| 200 | C9D1 | adverse event | dyspepsia | grade 1; resolves by day 225 | ensartinib continued (DM014) | parameter (A1) |
| 225 | TA4 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | assumption (A7) |
| 228 | C10D1 | adverse event | headache | grade 2; resolves by day 253 | ensartinib continued (DM014) | parameter (A1) |
| 239 | C10D1 | adverse event | anemia | grade 2; resolves by day 253 | ensartinib continued (DM014) | parameter (A1) |
| 239 | C10D1 | laboratory | Hemoglobin | 8.92 g/dL (grade 2) | during anemia | assumption (A5) |
| 270 | C11D1 | adverse event | decreased_platelet_count | grade 1; resolves by day 281 | ensartinib continued (DM014) | parameter (A1) |
| 281 | TA5 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | assumption (A7) |
| 288 | C12D1 | adverse event | hypocalcemia | grade 2; resolves by day 309 | ensartinib continued (DM014) | parameter (A1) |
| 319 | C13D1 | adverse event | pleural_effusion_disorder | grade 2; resolves by day 337 | ensartinib continued (DM014) | parameter (A1) |
| 337 | TA6 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | assumption (A7) |
| 359 | C14D1 | adverse event | edema | grade 1; resolves by day 365 | ensartinib continued (DM014) | parameter (A1) |
| 390 | C15D1 | adverse event | fatigue | grade 1; resolves by day 393 | ensartinib continued (DM014) | parameter (A1) |
| 393 | TA7 | tumour assessment | RECIST / protocol response criteria | progressive disease | progression detected: treatment ends | assumption (A7) |
| 393 | EOT | disposition | end of treatment | disease progression |  | protocol |
| 414 | C16D1 | adverse event | creatinine_renal_clearance_decreased | grade 2; resolves by day 421 | after treatment | parameter (A1) |
| 419 | C16D1 | adverse event | dyspnea | grade 2; resolves by day 421 | after treatment | parameter (A1) |
| 423 | FU1 | follow-up | follow-up visit | attended |  | protocol |
