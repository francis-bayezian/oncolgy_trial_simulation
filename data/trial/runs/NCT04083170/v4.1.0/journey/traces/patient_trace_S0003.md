# Patient trace S0003 (arm ARM1)

Simulated patient. Each row names how it was generated: protocol (StudySpec rule or schedule), evidence (registry), parameter (fitted asset), assumption (listed in journey_summary.json).

| Day | Visit | Category | Item | Result | Clinical consequence | Basis |
| ---: | --- | --- | --- | --- | --- | --- |
| -1 | SCREENING | screening | eligibility | ELIGIBLE | 0 criteria not checkable with generated variables | protocol |
| -1 | SCREENING | baseline | demographics | age 40.05, female, white |  | evidence |
| -1 | SCREENING | laboratory | Absolute neutrophil count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -1 | SCREENING | laboratory | Platelet count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -1 | SCREENING | laboratory | Hemoglobin | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -1 | SCREENING | laboratory | ALT | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -1 | SCREENING | laboratory | Creatinine | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| 1 | C1D1 | treatment | start intrathecal_therapy | dose not compiled | first dose | protocol |
| 1 | C1D1 | treatment | start intrathecal_methotrexate | dose not compiled | first dose | protocol |
| 1 | EOT | disposition | end of treatment | completed planned procedures |  | protocol |
| 3 | unscheduled | adverse event | coughing | grade 1; resolves by day 10 | after treatment | parameter (A1) |
| 5 | unscheduled | adverse event | epistaxis | grade 1; resolves by day 12 | after treatment | parameter (A1) |
| 6 | unscheduled | adverse event | fever | grade 2; resolves by day 13 | after treatment | parameter (A1) |
| 6 | unscheduled | adverse event | dyspnea | grade 3 serious; resolves by day 20 | after treatment | parameter (A1) |
| 7 | unscheduled | adverse event | anemia | grade 1; resolves by day 14 | after treatment | parameter (A1) |
| 7 | unscheduled | laboratory | Hemoglobin | 10.96 g/dL (grade 1) | during anemia | assumption (A5) |
| 11 | unscheduled | adverse event | inflammatory_disease_of_mucous_membrane | grade 1; resolves by day 18 | after treatment | parameter (A1) |
| 14 | unscheduled | adverse event | asthenia | grade 2; resolves by day 21 | after treatment | parameter (A1) |
| 18 | unscheduled | adverse event | abdominal_pain | grade 2; resolves by day 25 | after treatment | parameter (A1) |
| 24 | unscheduled | adverse event | alanine_aminotransferase_increased | grade 1; resolves by day 31 | after treatment | parameter (A1) |
| 24 | unscheduled | laboratory | ALT | 2.84 x ULN (grade 1) | during alanine_aminotransferase_increased | assumption (A5) |
| 31 | unscheduled | adverse event | headache | grade 2; resolves by day 38 | after treatment | parameter (A1) |
