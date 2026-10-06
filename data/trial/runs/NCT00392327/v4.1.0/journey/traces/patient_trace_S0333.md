# Patient trace S0333 (arm ARM2)

Simulated patient. Each row names how it was generated: protocol (StudySpec rule or schedule), evidence (registry), parameter (fitted asset), assumption (listed in journey_summary.json).

| Day | Visit | Category | Item | Result | Clinical consequence | Basis |
| ---: | --- | --- | --- | --- | --- | --- |
| -7 | SCREENING | screening | eligibility | ELIGIBLE | 0 criteria not checkable with generated variables | protocol (A13) |
| -7 | SCREENING | baseline | demographics | age 13.36, male, white |  | evidence |
| -7 | SCREENING | laboratory | Absolute neutrophil count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -7 | SCREENING | laboratory | Platelet count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -7 | SCREENING | laboratory | Hemoglobin | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -7 | SCREENING | laboratory | ALT | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -7 | SCREENING | laboratory | Creatinine | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| 1 | C1D1 | treatment | start vincristine | 1.5 mg/m2/day | first dose | protocol |
| 1 | C1D1 | treatment | start carboplatin | 35 mg/m2/day | first dose | protocol |
| 1 | C1D1 | treatment | start cisplatin | 75 mg/m2 | first dose | protocol |
| 2 | C1D2 | treatment | start cyclophosphamide | 1000 mg/m2 | first dose | protocol |
| 7 | C1D7 | adverse event | hypoalbuminemia | grade 1; resolves by day 8 | no protocol rule applies | parameter (A1) |
| 9 | C1D9 | adverse event | alopecia | grade 1; resolves by day 10 | no protocol rule applies | parameter (A1) |
| 10 | C1D10 | adverse event | neutrophils | grade 3 serious; resolves by day 12 | no protocol rule applies | parameter (A1) |
| 12 | C1D12 | adverse event | stomatitis | grade 1; resolves by day 13 | no protocol rule applies | parameter (A1) |
| 13 | C1D13 | adverse event | edema | grade 2; resolves by day 14 | no protocol rule applies | parameter (A1) |
| 13 | C1D13 | adverse event | blurred_vision | grade 1; resolves by day 14 | no protocol rule applies | parameter (A1) |
| 15 | C1D15 | adverse event | sensory_neuropathy | grade 2; resolves by day 16 | no protocol rule applies | parameter (A1) |
| 17 | C1D17 | adverse event | neutrophils | grade 1; resolves by day 18 | no protocol rule applies | parameter (A1) |
| 19 | C1D19 | adverse event | hemoglobin_normal_12_16_gm | grade 3 serious; resolves by day 21 | no protocol rule applies | parameter (A1) |
| 20 | C1D20 | adverse event | catheter_related_infection | grade 1; resolves by day 21 | no protocol rule applies | parameter (A1) |
| 21 | C1D21 | adverse event | weight_loss | grade 2; resolves by day 22 | no protocol rule applies | parameter (A1) |
| 37 | C2D9 | adverse event | fever | grade 2; resolves by day 38 | no protocol rule applies | parameter (A1) |
| 40 | C2D12 | adverse event | platelets | grade 3 serious; resolves by day 42 | cyclophosphamide reduced to reduced x1 (level not stated) from day 40 (DM008); undecidable: DM007 | parameter (A1) |
| 41 | C2D13 | adverse event | hypertriglyceridemia | grade 1; resolves by day 42 | no protocol rule applies | parameter (A1) |
| 41 | C2D13 | adverse event | hyperglycemia | grade 2; resolves by day 42 | no protocol rule applies | parameter (A1) |
| 45 | C2D17 | adverse event | anemia | grade 2; resolves by day 46 | no protocol rule applies | parameter (A1) |
| 45 | C2D17 | laboratory | Hemoglobin | 9.18 g/dL (grade 2) | during anemia | assumption (A5) |
| 48 | C2D20 | adverse event | peripheral_motor_neuropathy | grade 1; resolves by day 49 | no protocol rule applies | parameter (A1) |
| 48 | C2D20 | adverse event | headache | grade 3 serious; resolves by day 50 | no protocol rule applies | parameter (A1) |
| 52 | C2D24 | adverse event | dizziness | grade 1; resolves by day 53 | no protocol rule applies | parameter (A1) |
| 55 | C2D27 | adverse event | white_blood_cell_count_decreased | grade 3 serious; resolves by day 57 | no protocol rule applies | parameter (A1) |
| 55 | C2D27 | laboratory | White blood cell count | 1.3 10^9/L (grade 3) | during white_blood_cell_count_decreased | assumption (A5) |
| 56 | C2D28 | adverse event | neutrophil_count_decreased | grade 2; resolves by day 57 | no protocol rule applies | parameter (A1) |
| 56 | C2D28 | laboratory | Absolute neutrophil count | 1.41 10^9/L (grade 2) | during neutrophil_count_decreased | assumption (A5) |
| 58 | C3D2 | adverse event | dysgeusia | grade 2; resolves by day 59 | no protocol rule applies | parameter (A1) |
| 60 | C3D4 | adverse event | coughing | grade 1; resolves by day 61 | no protocol rule applies | parameter (A1) |
| 60 | C3D4 | adverse event | hyponatremia | grade 1; resolves by day 61 | no protocol rule applies | parameter (A1) |
| 60 | C3D4 | adverse event | lymphocyte_count_decreased | grade 1; resolves by day 61 | no protocol rule applies | parameter (A1) |
| 61 | C3D5 | adverse event | decreased_platelet_count | grade 3 serious; resolves by day 63 | cyclophosphamide reduced to reduced x2 (level not stated) from day 61 (DM008); undecidable: DM007 | parameter (A1) |
| 70 | C3D14 | adverse event | neuropathy_-_motor | grade 2; resolves by day 71 | no protocol rule applies | parameter (A1) |
| 70 | C3D14 | adverse event | decreased_platelet_count | grade 1; resolves by day 71 | cyclophosphamide reduced to reduced x3 (level not stated) from day 70 (DM008); undecidable: DM007 | parameter (A1) |
| 75 | C3D19 | adverse event | hemoglobin_normal_12_16_gm | grade 1; resolves by day 76 | no protocol rule applies | parameter (A1) |
| 76 | C3D20 | adverse event | neutrophils/granulocytes_(anc/agc) | grade 1; resolves by day 77 | no protocol rule applies | parameter (A1) |
| 78 | C3D22 | adverse event | arthralgia | grade 1; resolves by day 79 | no protocol rule applies | parameter (A1) |
| 79 | C3D23 | adverse event | neuropathy_-_sensory | grade 1; resolves by day 80 | no protocol rule applies | parameter (A1) |
| 79 | C3D23 | adverse event | anxiety | grade 1; resolves by day 80 | no protocol rule applies | parameter (A1) |
| 81 | C3D25 | adverse event | seizures | grade 2; resolves by day 82 | no protocol rule applies | parameter (A1) |
| 86 | C4D2 | adverse event | hypesthesia | grade 2; resolves by day 87 | no protocol rule applies | parameter (A1) |
| 87 | C4D3 | adverse event | nausea | grade 2; resolves by day 88 | no protocol rule applies | parameter (A1) |
| 90 | C4D6 | adverse event | allergic_rhinitis_disorder | grade 1; resolves by day 91 | no protocol rule applies | parameter (A1) |
| 94 | C4D10 | adverse event | alanine_aminotransferase_increased | grade 3 serious; resolves by day 96 | no protocol rule applies | parameter (A1) |
| 94 | C4D10 | laboratory | ALT | 7.02 x ULN (grade 3) | during alanine_aminotransferase_increased | assumption (A5) |
| 96 | C4D12 | adverse event | hypernatremia | grade 2; resolves by day 97 | no protocol rule applies | parameter (A1) |
| 98 | C4D14 | adverse event | sleeplessness | grade 2; resolves by day 99 | no protocol rule applies | parameter (A1) |
| 100 | C4D16 | adverse event | anorexia | grade 2; resolves by day 101 | no protocol rule applies | parameter (A1) |
| 107 | C4D23 | adverse event | vomiting | grade 1; resolves by day 108 | no protocol rule applies | parameter (A1) |
| 109 | C4D25 | adverse event | neutropenia | grade 1; resolves by day 110 | no protocol rule applies | parameter (A1) |
| 109 | C4D25 | laboratory | Absolute neutrophil count | 1.9 10^9/L (grade 1) | during neutropenia | assumption (A5) |
| 112 | C4D28 | adverse event | alanine_aminotransferase_increased | grade 2; resolves by day 113 | no protocol rule applies | parameter (A1) |
| 112 | C4D28 | laboratory | ALT | 3.26 x ULN (grade 2) | during alanine_aminotransferase_increased | assumption (A5) |
| 116 | C5D4 | adverse event | rhinitis | grade 2; resolves by day 117 | no protocol rule applies | parameter (A1) |
| 118 | C5D6 | adverse event | hydrocephalus | grade 3 serious; resolves by day 120 | no protocol rule applies | parameter (A1) |
| 122 | C5D10 | adverse event | pain_other | grade 1; resolves by day 123 | no protocol rule applies | parameter (A1) |
| 126 | C5D14 | adverse event | diarrhea | grade 2; resolves by day 127 | no protocol rule applies | parameter (A1) |
| 128 | C5D16 | adverse event | thrombosis | grade 3 serious; resolves by day 130 | no protocol rule applies | parameter (A1) |
| 140 | C5D28 | adverse event | upper_respiratory_infections | grade 2; resolves by day 141 | no protocol rule applies | parameter (A1) |
| 143 | C6D3 | adverse event | leukocytes_(total_wbc) | grade 2; resolves by day 144 | no protocol rule applies | parameter (A1) |
| 144 | C6D4 | adverse event | dyspnea | grade 2; resolves by day 145 | no protocol rule applies | parameter (A1) |
| 149 | C6D9 | adverse event | neuropathy-motor | grade 2; resolves by day 150 | no protocol rule applies | parameter (A1) |
| 154 | C6D14 | adverse event | muscle_weakness | grade 1; resolves by day 155 | no protocol rule applies | parameter (A1) |
| 154 | C6D14 | adverse event | sweating | grade 2; resolves by day 155 | no protocol rule applies | parameter (A1) |
| 155 | C6D15 | adverse event | constipation | grade 2; resolves by day 156 | no protocol rule applies | parameter (A1) |
| 157 | C6D17 | adverse event | leukocytes | grade 2; resolves by day 158 | no protocol rule applies | parameter (A1) |
| 159 | C6D19 | adverse event | hypokalemia | grade 3 serious; resolves by day 161 | no protocol rule applies | parameter (A1) |
| 162 | C6D22 | adverse event | dry_skin | grade 2; resolves by day 163 | no protocol rule applies | parameter (A1) |
| 168 | C6D28 | adverse event | hypophosphatemia | grade 2; resolves by day 175 | no protocol rule applies | parameter (A1) |
| 168 | EOT | disposition | end of treatment | completed planned treatment |  | protocol |
| 171 | unscheduled | adverse event | depression_dominant | grade 1; resolves by day 178 | after treatment | parameter (A1) |
| 172 | unscheduled | adverse event | fatigue | grade 2; resolves by day 179 | after treatment | parameter (A1) |
| 174 | unscheduled | adverse event | leukopenia | grade 2; resolves by day 181 | after treatment | parameter (A1) |
| 174 | unscheduled | laboratory | White blood cell count | 2.54 10^9/L (grade 2) | during leukopenia | assumption (A5) |
| 177 | unscheduled | adverse event | myalgia | grade 2; resolves by day 184 | after treatment | parameter (A1) |
| 179 | unscheduled | adverse event | hypercholesterolemia | grade 1; resolves by day 186 | after treatment | parameter (A1) |
| 179 | unscheduled | adverse event | hypocalcemia | grade 2; resolves by day 186 | after treatment | parameter (A1) |
| 181 | unscheduled | adverse event | thrombosis/thrombus/embolism | grade 3 serious; resolves by day 195 | after treatment | parameter (A1) |
| 183 | unscheduled | adverse event | fever | grade 3 serious; resolves by day 197 | after treatment | parameter (A1) |
| 184 | unscheduled | adverse event | hyperuricemia | grade 1; resolves by day 191 | after treatment | parameter (A1) |
| 185 | unscheduled | adverse event | platelets | grade 2; resolves by day 192 | after treatment | parameter (A1) |
| 185 | unscheduled | adverse event | headache | grade 1; resolves by day 192 | after treatment | parameter (A1) |
| 187 | unscheduled | adverse event | gastrointestinal | grade 1; resolves by day 194 | after treatment | parameter (A1) |
| 190 | unscheduled | adverse event | hypokalemia | grade 1; resolves by day 197 | after treatment | parameter (A1) |
| 195 | unscheduled | adverse event | seizures | grade 3 serious; resolves by day 209 | after treatment | parameter (A1) |
