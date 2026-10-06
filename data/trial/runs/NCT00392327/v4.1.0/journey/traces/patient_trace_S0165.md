# Patient trace S0165 (arm ARM2)

Simulated patient. Each row names how it was generated: protocol (StudySpec rule or schedule), evidence (registry), parameter (fitted asset), assumption (listed in journey_summary.json).

| Day | Visit | Category | Item | Result | Clinical consequence | Basis |
| ---: | --- | --- | --- | --- | --- | --- |
| -7 | SCREENING | screening | eligibility | ELIGIBLE | 0 criteria not checkable with generated variables | protocol (A13) |
| -7 | SCREENING | baseline | demographics | age 16.69, male, white |  | evidence |
| -7 | SCREENING | laboratory | Absolute neutrophil count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -7 | SCREENING | laboratory | Platelet count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -7 | SCREENING | laboratory | Hemoglobin | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -7 | SCREENING | laboratory | ALT | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -7 | SCREENING | laboratory | Creatinine | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| 1 | C1D1 | treatment | start vincristine | 1.5 mg/m2/day | first dose | protocol |
| 1 | C1D1 | treatment | start carboplatin | 35 mg/m2/day | first dose | protocol |
| 1 | C1D1 | treatment | start cisplatin | 75 mg/m2 | first dose | protocol |
| 2 | C1D2 | treatment | start cyclophosphamide | 1000 mg/m2 | first dose | protocol |
| 7 | C1D7 | adverse event | nausea | grade 1; resolves by day 8 | no protocol rule applies | parameter (A1) |
| 13 | C1D13 | adverse event | fatigue | grade 1; resolves by day 14 | no protocol rule applies | parameter (A1) |
| 34 | C2D6 | adverse event | thrombocytopenia | grade 2; resolves by day 35 | cyclophosphamide reduced to reduced x1 (level not stated) from day 34 (DM008); undecidable: DM007 | parameter (A1) |
| 34 | C2D6 | laboratory | Platelet count | 74.73 10^9/L (grade 2) | during thrombocytopenia | assumption (A5) |
| 38 | C2D10 | adverse event | decreased_platelet_count | grade 2; resolves by day 39 | cyclophosphamide reduced to reduced x2 (level not stated) from day 38 (DM008); undecidable: DM007 | parameter (A1) |
| 39 | C2D11 | adverse event | anorexia | grade 1; resolves by day 40 | no protocol rule applies | parameter (A1) |
| 50 | C2D22 | adverse event | weight_loss | grade 1; resolves by day 51 | no protocol rule applies | parameter (A1) |
| 55 | C2D27 | adverse event | neutropenia | grade 2; resolves by day 56 | no protocol rule applies | parameter (A1) |
| 55 | C2D27 | laboratory | Absolute neutrophil count | 1.45 10^9/L (grade 2) | during neutropenia | assumption (A5) |
| 69 | C3D13 | adverse event | dizziness | grade 1; resolves by day 70 | no protocol rule applies | parameter (A1) |
| 76 | C3D20 | adverse event | neutrophil_count_decreased | grade 2; resolves by day 77 | no protocol rule applies | parameter (A1) |
| 76 | C3D20 | laboratory | Absolute neutrophil count | 1.11 10^9/L (grade 2) | during neutrophil_count_decreased | assumption (A5) |
| 100 | C4D16 | adverse event | hypertriglyceridemia | grade 2; resolves by day 101 | no protocol rule applies | parameter (A1) |
| 106 | C4D22 | adverse event | platelets | grade 3 serious; resolves by day 108 | cyclophosphamide reduced to reduced x3 (level not stated) from day 106 (DM008); undecidable: DM007 | parameter (A1) |
| 112 | C4D28 | adverse event | platelets | grade 2; resolves by day 113 | cyclophosphamide reduced to reduced x4 (level not stated) from day 112 (DM008); undecidable: DM007 | parameter (A1) |
| 124 | C5D12 | adverse event | hemoglobin_normal_12_16_gm | grade 2; resolves by day 125 | no protocol rule applies | parameter (A1) |
| 127 | C5D15 | adverse event | muscle_weakness | grade 2; resolves by day 128 | no protocol rule applies | parameter (A1) |
| 132 | C5D20 | adverse event | myalgia | grade 2; resolves by day 133 | no protocol rule applies | parameter (A1) |
| 168 | EOT | disposition | end of treatment | completed planned treatment |  | protocol |
| 170 | unscheduled | adverse event | neuropathy_-_sensory | grade 2; resolves by day 177 | after treatment | parameter (A1) |
| 188 | unscheduled | adverse event | anxiety | grade 1; resolves by day 195 | after treatment | parameter (A1) |
| 197 | unscheduled | adverse event | hyperkalemia | grade 2; resolves by day 204 | after treatment | parameter (A1) |
