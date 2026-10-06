# Patient trace S0184 (arm ARM1)

Simulated patient. Each row names how it was generated: protocol (StudySpec rule or schedule), evidence (registry), parameter (fitted asset), assumption (listed in journey_summary.json).

| Day | Visit | Category | Item | Result | Clinical consequence | Basis |
| ---: | --- | --- | --- | --- | --- | --- |
| -35 | SCREENING | screening | eligibility | ELIGIBLE | 0 criteria not checkable with generated variables | protocol (A13) |
| -35 | SCREENING | baseline | demographics | age 46.12, male, white |  | evidence |
| -35 | SCREENING | laboratory | Absolute neutrophil count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -35 | SCREENING | laboratory | Platelet count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -35 | SCREENING | laboratory | Hemoglobin | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -35 | SCREENING | laboratory | ALT | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -35 | SCREENING | laboratory | Creatinine | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| 1 | C1D1 | treatment | start pemigatinib | 18 mg | first dose | protocol |
| 1 | C1D1 | treatment | start pembrolizumab | 200 mg | first dose | protocol |
| 8 | C1D8 | adverse event | diarrhea | grade 2; resolves by day 9 | pemigatinib continued (DM004); pembrolizumab held until day 9 (DM026) | parameter (A1) |
| 19 | C1D19 | adverse event | dizziness | grade 2; resolves by day 20 | pemigatinib continued (DM004) | parameter (A1) |
| 22 | C2D1 | adverse event | palmar_plantar_erythrodysesthesia_syndrome | grade 1; resolves by day 23 | pemigatinib continued (DM004); pembrolizumab held until day 23 (DM035) | parameter (A1) |
| 22 | C2D1 | treatment | pembrolizumab | 0/1 planned administrations | interrupted or discontinued | protocol |
| 42 | C2D21 | adverse event | dyspnea | grade 1; resolves by day 43 | pemigatinib continued (DM004) | parameter (A1) |
| 44 | C3D2 | adverse event | aspartate_aminotransferase_increased | grade 1; resolves by day 45 | pemigatinib continued (DM004); undecidable: DM003 | parameter (A1) |
| 44 | C3D2 | laboratory | AST | 1.91 x ULN (grade 1) | during aspartate_aminotransferase_increased | assumption (A5) |
| 55 | C3D13 | adverse event | diarrhea | grade 2; resolves by day 56 | pemigatinib continued (DM004); pembrolizumab held until day 56 (DM026) | parameter (A1) |
| 60 | C3D18 | adverse event | coughing | grade 2; resolves by day 61 | pemigatinib continued (DM004) | parameter (A1) |
| 64 | TA1 | tumour assessment | RECIST / protocol response criteria | progressive disease | progression detected: treatment ends | evidence |
| 64 | EOT | disposition | end of treatment | disease progression |  | protocol |
| 70 | C4D7 | adverse event | hemoglobin_normal_12_16_gm | grade 2; resolves by day 71 | after treatment | parameter (A1) |
| 85 | TA2 | adverse event | hypertension_variable | grade 1; resolves by day 127 | after treatment | parameter (A1) |
| 86 | TA2 | adverse event | anorexia | grade 1; resolves by day 127 | after treatment | parameter (A1) |
| 88 | TA2 | adverse event | pain | grade 1; resolves by day 127 | after treatment | parameter (A1) |
| 92 | TA2 | adverse event | anemia | grade 2; resolves by day 127 | after treatment | parameter (A1) |
| 92 | TA2 | laboratory | Hemoglobin | 8.01 g/dL (grade 2) | during anemia | assumption (A5) |
| 92 | TA2 | adverse event | hypocalcemia | grade 1; resolves by day 127 | after treatment | parameter (A1) |
| 148 | FU1 | follow-up | follow-up visit | attended |  | protocol |
