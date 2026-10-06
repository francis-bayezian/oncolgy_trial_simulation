# Patient trace S0015 (arm ARM1)

Simulated patient. Each row names how it was generated: protocol (StudySpec rule or schedule), evidence (registry), parameter (fitted asset), assumption (listed in journey_summary.json).

| Day | Visit | Category | Item | Result | Clinical consequence | Basis |
| ---: | --- | --- | --- | --- | --- | --- |
| -1 | SCREENING | screening | eligibility | ELIGIBLE | 0 criteria not checkable with generated variables | protocol |
| -1 | SCREENING | baseline | demographics | age 55.5, male, white |  | evidence |
| -1 | SCREENING | laboratory | Absolute neutrophil count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -1 | SCREENING | laboratory | Platelet count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -1 | SCREENING | laboratory | Hemoglobin | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -1 | SCREENING | laboratory | ALT | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -1 | SCREENING | laboratory | Creatinine | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| 1 | C1D1 | treatment | start cyclophosphamide | 1.6 mg/kg/day | first dose | protocol |
| 1 | C1D1 | treatment | start tapa_pulsed_dendritic_cells | 1 dc | first dose | protocol |
| 7 | C2D1 | adverse event | arthralgia | grade 2; resolves by day 8 | no protocol rule applies | parameter (A1) |
| 11 | C2D4 | adverse event | anemia | grade 2; resolves by day 12 | no protocol rule applies | parameter (A1) |
| 11 | C2D4 | laboratory | Hemoglobin | 9.2 g/dL (grade 2) | during anemia | assumption (A5) |
| 12 | C2D5 | adverse event | dysgeusia | grade 2; resolves by day 15 | no protocol rule applies | parameter (A1) |
| 16 | C3D2 | adverse event | decrease_in_appetite | grade 1; resolves by day 17 | no protocol rule applies | parameter (A1) |
| 16 | C3D2 | adverse event | alopecia | grade 2; resolves by day 17 | no protocol rule applies | parameter (A1) |
| 17 | C3D3 | adverse event | dyspnea | grade 1; resolves by day 18 | no protocol rule applies | parameter (A1) |
| 17 | C3D3 | adverse event | edema | grade 2; resolves by day 18 | no protocol rule applies | parameter (A1) |
| 18 | C3D4 | adverse event | pain | grade 1; resolves by day 19 | no protocol rule applies | parameter (A1) |
| 20 | unscheduled | adverse event | aspartate_aminotransferase_increased | grade 2; resolves by day 27 | no protocol rule applies | parameter (A1) |
| 20 | unscheduled | laboratory | AST | 4.99 x ULN (grade 2) | during aspartate_aminotransferase_increased | assumption (A5) |
| 20 | unscheduled | adverse event | febrile_neutropenia | grade 1; resolves by day 27 | no protocol rule applies | parameter (A1) |
| 20 | unscheduled | laboratory | Absolute neutrophil count | 1.81 10^9/L (grade 1) | during febrile_neutropenia | assumption (A5) |
| 21 | EOT | disposition | end of treatment | completed planned treatment |  | protocol |
| 22 | unscheduled | adverse event | fever | grade 1; resolves by day 29 | after treatment | parameter (A1) |
| 23 | unscheduled | adverse event | vomiting | grade 2; resolves by day 30 | after treatment | parameter (A1) |
| 26 | unscheduled | adverse event | abdominal_pain | grade 2; resolves by day 33 | after treatment | parameter (A1) |
| 28 | unscheduled | adverse event | headache | grade 2; resolves by day 35 | after treatment | parameter (A1) |
| 34 | unscheduled | adverse event | xerostomia | grade 1; resolves by day 41 | after treatment | parameter (A1) |
| 37 | unscheduled | adverse event | asthenia | grade 1; resolves by day 44 | after treatment | parameter (A1) |
| 37 | unscheduled | adverse event | hyperglycemia | grade 1; resolves by day 44 | after treatment | parameter (A1) |
| 38 | unscheduled | adverse event | rash_erythematous_macules_or_papules | grade 2; resolves by day 45 | after treatment | parameter (A1) |
| 40 | unscheduled | adverse event | decreased_platelet_count | grade 1; resolves by day 47 | after treatment | parameter (A1) |
| 45 | unscheduled | adverse event | fatigue | grade 2; resolves by day 52 | after treatment | parameter (A1) |
| 46 | unscheduled | adverse event | white_blood_cell_count_decreased | grade 1; resolves by day 53 | after treatment | parameter (A1) |
| 46 | unscheduled | laboratory | White blood cell count | 3.83 10^9/L (grade 1) | during white_blood_cell_count_decreased | assumption (A5) |
| 47 | unscheduled | adverse event | constipation | grade 2; resolves by day 54 | after treatment | parameter (A1) |
| 47 | unscheduled | adverse event | diarrhea | grade 2; resolves by day 54 | after treatment | parameter (A1) |
| 47 | unscheduled | adverse event | peripheral_edema | grade 2; resolves by day 54 | after treatment | parameter (A1) |
| 48 | unscheduled | adverse event | anorexia | grade 1; resolves by day 55 | after treatment | parameter (A1) |
