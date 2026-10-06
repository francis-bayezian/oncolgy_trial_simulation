# Patient trace S0006 (arm ARM1)

Simulated patient. Each row names how it was generated: protocol (StudySpec rule or schedule), evidence (registry), parameter (fitted asset), assumption (listed in journey_summary.json).

| Day | Visit | Category | Item | Result | Clinical consequence | Basis |
| ---: | --- | --- | --- | --- | --- | --- |
| -1 | SCREENING | screening | eligibility | ELIGIBLE | 0 criteria not checkable with generated variables | protocol |
| -1 | SCREENING | baseline | demographics | age 76.31, male, white |  | evidence |
| -1 | SCREENING | laboratory | Absolute neutrophil count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -1 | SCREENING | laboratory | Platelet count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -1 | SCREENING | laboratory | Hemoglobin | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -1 | SCREENING | laboratory | ALT | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -1 | SCREENING | laboratory | Creatinine | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| 1 | C1D1 | treatment | start cyclophosphamide | 1.6 mg/kg/day | first dose | protocol |
| 1 | C1D1 | treatment | start tapa_pulsed_dendritic_cells | 1 dc | first dose | protocol |
| 1 | C1D1 | adverse event | decrease_in_appetite | grade 2; resolves by day 2 | no protocol rule applies | parameter (A1) |
| 2 | C1D2 | adverse event | fever | grade 3 serious; resolves by day 4 | no protocol rule applies | parameter (A1) |
| 4 | C1D4 | adverse event | alopecia | grade 1; resolves by day 5 | no protocol rule applies | parameter (A1) |
| 5 | C1D5 | adverse event | xerostomia | grade 2; resolves by day 8 | no protocol rule applies | parameter (A1) |
| 12 | C2D5 | adverse event | constipation | grade 2; resolves by day 15 | no protocol rule applies | parameter (A1) |
| 12 | C2D5 | adverse event | hyperglycemia | grade 2; resolves by day 15 | no protocol rule applies | parameter (A1) |
| 15 | C3D1 | adverse event | dysgeusia | grade 1; resolves by day 16 | no protocol rule applies | parameter (A1) |
| 20 | unscheduled | adverse event | aspartate_aminotransferase_increased | grade 1; resolves by day 27 | no protocol rule applies | parameter (A1) |
| 20 | unscheduled | laboratory | AST | 1.13 x ULN (grade 1) | during aspartate_aminotransferase_increased | assumption (A5) |
| 21 | EOT | disposition | end of treatment | completed planned treatment |  | protocol |
| 22 | unscheduled | adverse event | anorexia | grade 2; resolves by day 29 | after treatment | parameter (A1) |
| 33 | unscheduled | adverse event | asthenia | grade 1; resolves by day 40 | after treatment | parameter (A1) |
| 37 | unscheduled | adverse event | headache | grade 1; resolves by day 44 | after treatment | parameter (A1) |
| 43 | unscheduled | adverse event | anemia | grade 1; resolves by day 50 | after treatment | parameter (A1) |
| 43 | unscheduled | laboratory | Hemoglobin | 10.56 g/dL (grade 1) | during anemia | assumption (A5) |
| 44 | unscheduled | adverse event | febrile_neutropenia | grade 1; resolves by day 51 | after treatment | parameter (A1) |
| 44 | unscheduled | laboratory | Absolute neutrophil count | 1.82 10^9/L (grade 1) | during febrile_neutropenia | assumption (A5) |
| 45 | unscheduled | adverse event | alanine_aminotransferase_increased | grade 1; resolves by day 52 | after treatment | parameter (A1) |
| 45 | unscheduled | laboratory | ALT | 1.63 x ULN (grade 1) | during alanine_aminotransferase_increased | assumption (A5) |
| 45 | unscheduled | adverse event | rash_erythematous_macules_or_papules | grade 1; resolves by day 52 | after treatment | parameter (A1) |
| 46 | unscheduled | adverse event | edema | grade 1; resolves by day 53 | after treatment | parameter (A1) |
| 51 | unscheduled | adverse event | leukocytes | grade 1; resolves by day 58 | after treatment | parameter (A1) |
