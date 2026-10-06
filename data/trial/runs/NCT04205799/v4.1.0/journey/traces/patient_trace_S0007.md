# Patient trace S0007 (arm ARM2)

Simulated patient. Each row names how it was generated: protocol (StudySpec rule or schedule), evidence (registry), parameter (fitted asset), assumption (listed in journey_summary.json).

| Day | Visit | Category | Item | Result | Clinical consequence | Basis |
| ---: | --- | --- | --- | --- | --- | --- |
| -28 | SCREENING | screening | eligibility | ELIGIBLE | 0 criteria not checkable with generated variables | protocol (A13) |
| -28 | SCREENING | baseline | demographics | age 67.0, female, white |  | evidence |
| -28 | SCREENING | laboratory | Absolute neutrophil count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | Platelet count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | Hemoglobin | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | ALT | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | Creatinine | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| 1 | C1D1 | treatment | start cabozantinib | 60 mg | first dose | protocol |
| 3 | C1D3 | adverse event | nausea | grade 1; resolves by day 4 | cabozantinib continued (DM017) | parameter (A1) |
| 17 | C1D17 | adverse event | hot_flushes | grade 1; resolves by day 18 | cabozantinib continued (DM017) | parameter (A1) |
| 28 | C1D28 | adverse event | Diarrhea | grade 2; resolves by day 29 | cabozantinib continued (DM017) | parameter (A1) |
| 49 | C2D21 | adverse event | palmar_plantar_erythrodysesthesia_syndrome | grade 1; resolves by day 50 | cabozantinib continued (DM017) | parameter (A1) |
| 50 | C2D22 | adverse event | urinary_tract_infection | grade 2; resolves by day 51 | cabozantinib continued (DM017) | parameter (A1) |
| 55 | C2D27 | adverse event | acneiform_eruptions | grade 1; resolves by day 56 | cabozantinib continued (DM017) | parameter (A1) |
| 85 | TA1 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | assumption (A7) |
| 118 | C5D6 | adverse event | pain_in_limb | grade 1; resolves by day 119 | cabozantinib continued (DM017) | parameter (A1) |
| 121 | C5D9 | adverse event | thrombocytopenia | grade 1; resolves by day 122 | cabozantinib continued (DM012) | parameter (A1) |
| 121 | C5D9 | laboratory | Platelet count | 104.27 10^9/L (grade 1) | during thrombocytopenia | assumption (A5) |
| 141 | C6D1 | adverse event | vaginal_discharge | grade 1; resolves by day 142 | cabozantinib continued (DM017) | parameter (A1) |
| 141 | C6D1 | treatment | cabozantinib | 26/28 planned administrations | interrupted or discontinued | protocol |
| 144 | C6D4 | adverse event | rash/desquamation | grade 2; resolves by day 145 | cabozantinib continued (DM017) | parameter (A1) |
| 152 | C6D12 | adverse event | other serious adverse events (not individually predicted) | grade 3 serious; resolves by day 154 | cabozantinib held until day 154 (DM019) | parameter (A1) |
| 167 | C6D27 | adverse event | dyspnea | grade 1; resolves by day 168 | cabozantinib continued (DM017) | parameter (A1) |
| 169 | TA2 | tumour assessment | RECIST / protocol response criteria | progressive disease | progression detected: treatment ends | assumption (A7) |
| 169 | EOT | disposition | end of treatment | disease progression |  | protocol |
| 190 | C7D22 | adverse event | vomiting | grade 2; resolves by day 191 | after treatment | parameter (A1) |
| 192 | C7D24 | adverse event | leukopenia | grade 1; resolves by day 193 | after treatment | parameter (A1) |
| 192 | C7D24 | laboratory | White blood cell count | 3.49 10^9/L (grade 1) | during leukopenia | assumption (A5) |
