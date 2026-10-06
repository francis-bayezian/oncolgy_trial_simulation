# Patient trace S0050 (arm ARM2)

Simulated patient. Each row names how it was generated: protocol (StudySpec rule or schedule), evidence (registry), parameter (fitted asset), assumption (listed in journey_summary.json).

| Day | Visit | Category | Item | Result | Clinical consequence | Basis |
| ---: | --- | --- | --- | --- | --- | --- |
| -28 | SCREENING | screening | eligibility | ELIGIBLE | 0 criteria not checkable with generated variables | protocol (A13) |
| -28 | SCREENING | baseline | demographics | age 32.13, female, white |  | evidence |
| -28 | SCREENING | laboratory | Absolute neutrophil count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | Platelet count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | Hemoglobin | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | ALT | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | Creatinine | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| 1 | C1D1 | treatment | start cabozantinib | 60 mg | first dose | protocol |
| 12 | C1D12 | adverse event | alanine_aminotransferase_increased | grade 2; resolves by day 13 | cabozantinib continued (DM017) | parameter (A1) |
| 12 | C1D12 | laboratory | ALT | 4.74 x ULN (grade 2) | during alanine_aminotransferase_increased | assumption (A5) |
| 17 | C1D17 | adverse event | dyspnea | grade 2; resolves by day 18 | cabozantinib continued (DM017) | parameter (A1) |
| 18 | C1D18 | adverse event | white_blood_cell_decreased | grade 1; resolves by day 19 | no protocol rule applies | parameter (A1) |
| 18 | C1D18 | laboratory | White blood cell count | 3.68 10^9/L (grade 1) | during white_blood_cell_decreased | assumption (A5) |
| 29 | C2D1 | treatment | cabozantinib | 26/28 planned administrations | interrupted or discontinued | protocol |
| 45 | C2D17 | adverse event | asthenia | grade 1; resolves by day 46 | cabozantinib continued (DM017) | parameter (A1) |
| 45 | C2D17 | adverse event | neoplasms_benign,_malignant_and_unspecified_(incl_cysts_and_polyps)_-_other,_specify | grade 3 serious; resolves by day 47 | cabozantinib held until day 47 (DM019) | parameter (A1) |
| 69 | C3D13 | adverse event | anxiety | grade 1; resolves by day 70 | cabozantinib continued (DM017) | parameter (A1) |
| 74 | C3D18 | adverse event | vomiting | grade 1; resolves by day 75 | cabozantinib continued (DM017) | parameter (A1) |
| 85 | TA1 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | assumption (A7) |
| 90 | C4D6 | adverse event | hypertension_variable | grade 1; resolves by day 91 | cabozantinib continued (DM017); undecidable: DM026 | parameter (A1) |
| 94 | C4D10 | adverse event | rash_erythematous_macules_or_papules | grade 1; resolves by day 95 | cabozantinib continued (DM017) | parameter (A1) |
| 95 | C4D11 | adverse event | abdomen_distended | grade 1; resolves by day 96 | cabozantinib continued (DM017) | parameter (A1) |
| 104 | C4D20 | adverse event | rash/desquamation | grade 2; resolves by day 105 | cabozantinib continued (DM017) | parameter (A1) |
| 112 | C4D28 | adverse event | acneiform_eruptions | grade 1; resolves by day 113 | cabozantinib continued (DM017) | parameter (A1) |
| 125 | C5D13 | adverse event | anorexia | grade 1; resolves by day 126 | cabozantinib continued (DM017) | parameter (A1) |
| 138 | C5D26 | adverse event | palmar_plantar_erythrodysesthesia_syndrome | grade 2; resolves by day 139 | cabozantinib continued (DM017) | parameter (A1) |
| 169 | TA2 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | assumption (A7) |
| 197 | C8D1 | treatment | cabozantinib | 26/28 planned administrations | interrupted or discontinued | protocol |
| 204 | C8D8 | adverse event | urinary_tract_infection | grade 3 serious; resolves by day 206 | cabozantinib held until day 206 (DM019) | parameter (A1) |
| 240 | C9D16 | adverse event | thrombocytopenia | grade 2; resolves by day 241 | cabozantinib continued (DM012) | parameter (A1) |
| 240 | C9D16 | laboratory | Platelet count | 74.44 10^9/L (grade 2) | during thrombocytopenia | assumption (A5) |
| 252 | C9D28 | adverse event | sensory_neuropathy | grade 1; resolves by day 253 | cabozantinib continued (DM017) | parameter (A1) |
| 253 | TA3 | tumour assessment | RECIST / protocol response criteria | progressive disease | progression detected: treatment ends | assumption (A7) |
| 253 | EOT | disposition | end of treatment | disease progression |  | protocol |
| 277 | C10D25 | adverse event | weight_loss | grade 1; resolves by day 278 | after treatment | parameter (A1) |
