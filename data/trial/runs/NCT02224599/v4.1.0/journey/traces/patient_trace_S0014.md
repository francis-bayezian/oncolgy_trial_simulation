# Patient trace S0014 (arm ARM1)

Simulated patient. Each row names how it was generated: protocol (StudySpec rule or schedule), evidence (registry), parameter (fitted asset), assumption (listed in journey_summary.json).

| Day | Visit | Category | Item | Result | Clinical consequence | Basis |
| ---: | --- | --- | --- | --- | --- | --- |
| -1 | SCREENING | screening | eligibility | ELIGIBLE | 0 criteria not checkable with generated variables | protocol |
| -1 | SCREENING | baseline | demographics | age 65.84, male, white |  | evidence |
| -1 | SCREENING | laboratory | Absolute neutrophil count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -1 | SCREENING | laboratory | Platelet count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -1 | SCREENING | laboratory | Hemoglobin | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -1 | SCREENING | laboratory | ALT | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -1 | SCREENING | laboratory | Creatinine | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| 1 | C1D1 | treatment | start cyclophosphamide | 1.6 mg/kg/day | first dose | protocol |
| 1 | C1D1 | treatment | start tapa_pulsed_dendritic_cells | 1 dc | first dose | protocol |
| 3 | C1D3 | adverse event | decrease_in_appetite | grade 2; resolves by day 4 | no protocol rule applies | parameter (A1) |
| 16 | C3D2 | adverse event | fatigue | grade 2; resolves by day 17 | no protocol rule applies | parameter (A1) |
| 16 | C3D2 | adverse event | diarrhea | grade 2; resolves by day 17 | no protocol rule applies | parameter (A1) |
| 17 | unscheduled | tumour assessment | progression | progressive disease | no tumour assessment schedule resolved: recorded at its true time | assumption |
| 17 | EOT | disposition | end of treatment | disease progression |  | protocol |
| 19 | C3D5 | adverse event | aspartate_aminotransferase_increased | grade 1; resolves by day 26 | after treatment | parameter (A1) |
| 19 | C3D5 | laboratory | AST | 2.28 x ULN (grade 1) | during aspartate_aminotransferase_increased | assumption (A5) |
| 19 | C3D5 | adverse event | xerostomia | grade 1; resolves by day 26 | after treatment | parameter (A1) |
| 20 | unscheduled | adverse event | headache | grade 2; resolves by day 27 | after treatment | parameter (A1) |
| 23 | unscheduled | adverse event | edema | grade 2; resolves by day 30 | after treatment | parameter (A1) |
| 26 | unscheduled | adverse event | alopecia | grade 1; resolves by day 33 | after treatment | parameter (A1) |
| 26 | unscheduled | adverse event | anorexia | grade 2; resolves by day 33 | after treatment | parameter (A1) |
| 26 | unscheduled | adverse event | pneumonia | grade 3 serious; resolves by day 40 | after treatment | parameter (A1) |
| 34 | unscheduled | adverse event | febrile_neutropenia | grade 2; resolves by day 41 | after treatment | parameter (A1) |
| 34 | unscheduled | laboratory | Absolute neutrophil count | 1.44 10^9/L (grade 2) | during febrile_neutropenia | assumption (A5) |
