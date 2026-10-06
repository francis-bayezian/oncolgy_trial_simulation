# Patient trace S0005 (arm ARM2)

Simulated patient. Each row names how it was generated: protocol (StudySpec rule or schedule), evidence (registry), parameter (fitted asset), assumption (listed in journey_summary.json).

| Day | Visit | Category | Item | Result | Clinical consequence | Basis |
| ---: | --- | --- | --- | --- | --- | --- |
| -28 | SCREENING | screening | eligibility | ELIGIBLE | 0 criteria not checkable with generated variables | protocol (A13) |
| -28 | SCREENING | baseline | demographics | age 37.43, female, white |  | evidence |
| -28 | SCREENING | laboratory | Absolute neutrophil count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | Platelet count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | Hemoglobin | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | ALT | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | Creatinine | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| 1 | C1D1 | treatment | start cabozantinib | 60 mg | first dose | protocol |
| 5 | C1D5 | adverse event | thrombocytopenia | grade 1; resolves by day 6 | cabozantinib continued (DM012) | parameter (A1) |
| 5 | C1D5 | laboratory | Platelet count | 76.54 10^9/L (grade 1) | during thrombocytopenia | assumption (A5) |
| 8 | C1D8 | adverse event | pain_in_limb | grade 2; resolves by day 9 | cabozantinib continued (DM017) | parameter (A1) |
| 10 | C1D10 | adverse event | palmar_plantar_erythrodysesthesia_syndrome | grade 2; resolves by day 11 | cabozantinib continued (DM017) | parameter (A1) |
| 24 | C1D24 | adverse event | rash/desquamation | grade 2; resolves by day 25 | cabozantinib continued (DM017) | parameter (A1) |
| 27 | C1D27 | adverse event | anemia | grade 2; resolves by day 28 | cabozantinib continued (DM014) | parameter (A1) |
| 27 | C1D27 | laboratory | Hemoglobin | 8.9 g/dL (grade 2) | during anemia | assumption (A5) |
| 29 | C2D1 | treatment | cabozantinib | 16/19 planned administrations | interrupted or discontinued | protocol |
| 31 | C2D3 | adverse event | neoplasms_benign,_malignant_and_unspecified_(incl_cysts_and_polyps)_-_other,_specify | grade 3 serious; resolves by day 33 | cabozantinib held until day 33 (DM019) | parameter (A1) |
| 33 | C2D5 | adverse event | dyspnea | grade 2; resolves by day 34 | cabozantinib continued (DM017) | parameter (A1) |
| 37 | C2D9 | adverse event | hypertension_variable | grade 1; resolves by day 38 | cabozantinib continued (DM017); undecidable: DM026 | parameter (A1) |
| 37 | C2D9 | adverse event | alanine_aminotransferase_increased | grade 2; resolves by day 38 | cabozantinib continued (DM017) | parameter (A1) |
| 37 | C2D9 | laboratory | ALT | 4.27 x ULN (grade 2) | during alanine_aminotransferase_increased | assumption (A5) |
| 47 | C2D19 | adverse event | fistula | grade 2; resolves by day 48 | cabozantinib discontinued (DM006) | parameter (A1) |
| 47 | EOT | disposition | end of treatment | adverse event (all agents discontinued) |  | protocol |
| 48 | C2D20 | adverse event | urinary_tract_infection | grade 2; resolves by day 49 | after treatment | parameter (A1) |
| 49 | C2D21 | adverse event | acneiform_eruptions | grade 1; resolves by day 50 | after treatment | parameter (A1) |
| 54 | C2D26 | adverse event | depression_dominant | grade 1; resolves by day 55 | after treatment | parameter (A1) |
| 69 | C3D13 | adverse event | vaginal_discharge | grade 1; resolves by day 70 | after treatment | parameter (A1) |
| 75 | C3D19 | adverse event | white_blood_cell_decreased | grade 2; resolves by day 76 | after treatment | parameter (A1) |
| 75 | C3D19 | laboratory | White blood cell count | 2.23 10^9/L (grade 2) | during white_blood_cell_decreased | assumption (A5) |
