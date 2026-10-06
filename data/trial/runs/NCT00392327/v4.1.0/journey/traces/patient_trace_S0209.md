# Patient trace S0209 (arm ARM1)

Simulated patient. Each row names how it was generated: protocol (StudySpec rule or schedule), evidence (registry), parameter (fitted asset), assumption (listed in journey_summary.json).

| Day | Visit | Category | Item | Result | Clinical consequence | Basis |
| ---: | --- | --- | --- | --- | --- | --- |
| -7 | SCREENING | screening | eligibility | ELIGIBLE | 0 criteria not checkable with generated variables | protocol (A13) |
| -7 | SCREENING | baseline | demographics | age 10.69, male, white |  | evidence |
| -7 | SCREENING | laboratory | Absolute neutrophil count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -7 | SCREENING | laboratory | Platelet count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -7 | SCREENING | laboratory | Hemoglobin | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -7 | SCREENING | laboratory | ALT | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -7 | SCREENING | laboratory | Creatinine | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| 1 | C1D1 | treatment | start vincristine | 1.5 mg/m2/day | first dose | protocol |
| 1 | C1D1 | treatment | start cisplatin | 75 mg/m2 | first dose | protocol |
| 2 | C1D2 | treatment | start cyclophosphamide | 1000 mg/m2 | first dose | protocol |
| 2 | C1D2 | adverse event | hyperuricemia | grade 1; resolves by day 3 | no protocol rule applies | parameter (A1) |
| 5 | C1D5 | adverse event | blurred_vision | grade 1; resolves by day 6 | no protocol rule applies | parameter (A1) |
| 7 | C1D7 | adverse event | hypesthesia | grade 2; resolves by day 8 | no protocol rule applies | parameter (A1) |
| 11 | C1D11 | adverse event | neuropathy_-_motor | grade 1; resolves by day 12 | no protocol rule applies | parameter (A1) |
| 12 | C1D12 | adverse event | peripheral_motor_neuropathy | grade 2; resolves by day 13 | no protocol rule applies | parameter (A1) |
| 14 | C1D14 | adverse event | anxiety | grade 2; resolves by day 15 | no protocol rule applies | parameter (A1) |
| 31 | C2D3 | adverse event | decreased_platelet_count | grade 3 serious; resolves by day 33 | cyclophosphamide reduced to reduced x1 (level not stated) from day 31 (DM008); undecidable: DM007 | parameter (A1) |
| 32 | C2D4 | adverse event | seizures | grade 3 serious; resolves by day 34 | no protocol rule applies | parameter (A1) |
| 35 | C2D7 | adverse event | constipation | grade 1; resolves by day 36 | no protocol rule applies | parameter (A1) |
| 38 | C2D10 | adverse event | myalgia | grade 2; resolves by day 39 | no protocol rule applies | parameter (A1) |
| 44 | C2D16 | adverse event | upper_respiratory_infections | grade 2; resolves by day 45 | no protocol rule applies | parameter (A1) |
| 45 | C2D17 | adverse event | hypocalcemia | grade 2; resolves by day 46 | no protocol rule applies | parameter (A1) |
| 46 | C2D18 | adverse event | edema | grade 1; resolves by day 47 | no protocol rule applies | parameter (A1) |
| 51 | C2D23 | adverse event | anorexia | grade 2; resolves by day 52 | no protocol rule applies | parameter (A1) |
| 51 | C2D23 | adverse event | hyponatremia | grade 1; resolves by day 52 | no protocol rule applies | parameter (A1) |
| 51 | C2D23 | adverse event | hyperglycemia | grade 1; resolves by day 52 | no protocol rule applies | parameter (A1) |
| 54 | C2D26 | adverse event | stomatitis | grade 2; resolves by day 55 | no protocol rule applies | parameter (A1) |
| 58 | C3D2 | adverse event | decreased_platelet_count | grade 2; resolves by day 59 | cyclophosphamide reduced to reduced x2 (level not stated) from day 58 (DM008); undecidable: DM007 | parameter (A1) |
| 59 | C3D3 | adverse event | fever | grade 1; resolves by day 60 | no protocol rule applies | parameter (A1) |
| 59 | C3D3 | adverse event | headache | grade 3 serious; resolves by day 61 | no protocol rule applies | parameter (A1) |
| 61 | C3D5 | adverse event | hemoglobin_normal_12_16_gm | grade 2; resolves by day 62 | no protocol rule applies | parameter (A1) |
| 62 | C3D6 | adverse event | arthralgia | grade 2; resolves by day 63 | no protocol rule applies | parameter (A1) |
| 62 | C3D6 | adverse event | hemoglobin_normal_12_16_gm | grade 3 serious; resolves by day 64 | no protocol rule applies | parameter (A1) |
| 63 | C3D7 | adverse event | muscle_weakness | grade 2; resolves by day 64 | no protocol rule applies | parameter (A1) |
| 67 | C3D11 | adverse event | depression_dominant | grade 1; resolves by day 68 | no protocol rule applies | parameter (A1) |
| 68 | C3D12 | adverse event | dizziness | grade 2; resolves by day 69 | no protocol rule applies | parameter (A1) |
| 70 | C3D14 | adverse event | pain_other | grade 1; resolves by day 71 | no protocol rule applies | parameter (A1) |
| 70 | C3D14 | adverse event | white_blood_cell_count_decreased | grade 3 serious; resolves by day 72 | no protocol rule applies | parameter (A1) |
| 70 | C3D14 | laboratory | White blood cell count | 1.03 10^9/L (grade 3) | during white_blood_cell_count_decreased | assumption (A5) |
| 73 | C3D17 | adverse event | platelets | grade 3 serious; resolves by day 75 | cyclophosphamide reduced to reduced x3 (level not stated) from day 73 (DM008); undecidable: DM007 | parameter (A1) |
| 76 | C3D20 | adverse event | nausea | grade 2; resolves by day 77 | no protocol rule applies | parameter (A1) |
| 80 | C3D24 | adverse event | alanine_aminotransferase_increased | grade 3 serious; resolves by day 82 | no protocol rule applies | parameter (A1) |
| 80 | C3D24 | laboratory | ALT | 11.1 x ULN (grade 3) | during alanine_aminotransferase_increased | assumption (A5) |
| 82 | C3D26 | adverse event | dry_skin | grade 1; resolves by day 83 | no protocol rule applies | parameter (A1) |
| 86 | C4D2 | adverse event | rash_erythematous_macules_or_papules | grade 2; resolves by day 87 | no protocol rule applies | parameter (A1) |
| 86 | C4D2 | adverse event | thrombosis/thrombus/embolism | grade 3 serious; resolves by day 88 | no protocol rule applies | parameter (A1) |
| 89 | C4D5 | adverse event | platelets | grade 2; resolves by day 90 | cyclophosphamide reduced to reduced x4 (level not stated) from day 89 (DM008); undecidable: DM007 | parameter (A1) |
| 107 | C4D23 | adverse event | hypercholesterolemia | grade 1; resolves by day 108 | no protocol rule applies | parameter (A1) |
| 113 | C5D1 | adverse event | sleeplessness | grade 2; resolves by day 114 | no protocol rule applies | parameter (A1) |
| 113 | C5D1 | adverse event | gastrointestinal | grade 2; resolves by day 114 | no protocol rule applies | parameter (A1) |
| 115 | C5D3 | adverse event | hypernatremia | grade 2; resolves by day 116 | no protocol rule applies | parameter (A1) |
| 119 | C5D7 | adverse event | hypophosphatemia | grade 1; resolves by day 120 | no protocol rule applies | parameter (A1) |
| 127 | C5D15 | adverse event | alanine_aminotransferase_increased | grade 2; resolves by day 128 | no protocol rule applies | parameter (A1) |
| 127 | C5D15 | laboratory | ALT | 4.15 x ULN (grade 2) | during alanine_aminotransferase_increased | assumption (A5) |
| 127 | C5D15 | adverse event | sweating | grade 2; resolves by day 128 | no protocol rule applies | parameter (A1) |
| 129 | C5D17 | adverse event | hypokalemia | grade 1; resolves by day 130 | no protocol rule applies | parameter (A1) |
| 130 | C5D18 | adverse event | sensory_neuropathy | grade 1; resolves by day 131 | no protocol rule applies | parameter (A1) |
| 136 | C5D24 | adverse event | hypoalbuminemia | grade 1; resolves by day 137 | no protocol rule applies | parameter (A1) |
| 145 | C6D5 | adverse event | fatigue | grade 1; resolves by day 146 | no protocol rule applies | parameter (A1) |
| 149 | C6D9 | adverse event | vomiting | grade 1; resolves by day 150 | no protocol rule applies | parameter (A1) |
| 152 | C6D12 | adverse event | weight_loss | grade 1; resolves by day 153 | no protocol rule applies | parameter (A1) |
| 154 | C6D14 | adverse event | allergic_rhinitis_disorder | grade 1; resolves by day 155 | no protocol rule applies | parameter (A1) |
| 158 | C6D18 | adverse event | dyspnea | grade 1; resolves by day 159 | no protocol rule applies | parameter (A1) |
| 159 | C6D19 | adverse event | seizures | grade 2; resolves by day 160 | no protocol rule applies | parameter (A1) |
| 159 | C6D19 | adverse event | anemia | grade 1; resolves by day 160 | no protocol rule applies | parameter (A1) |
| 159 | C6D19 | laboratory | Hemoglobin | 10.54 g/dL (grade 1) | during anemia | assumption (A5) |
| 161 | C6D21 | adverse event | thrombosis | grade 3 serious; resolves by day 163 | no protocol rule applies | parameter (A1) |
| 162 | C6D22 | adverse event | neuropathy-motor | grade 2; resolves by day 163 | no protocol rule applies | parameter (A1) |
| 163 | C6D23 | adverse event | diarrhea | grade 1; resolves by day 164 | no protocol rule applies | parameter (A1) |
| 164 | C6D24 | adverse event | neutrophil_count_decreased | grade 1; resolves by day 165 | no protocol rule applies | parameter (A1) |
| 164 | C6D24 | laboratory | Absolute neutrophil count | 1.89 10^9/L (grade 1) | during neutrophil_count_decreased | assumption (A5) |
| 165 | C6D25 | adverse event | headache | grade 2; resolves by day 166 | no protocol rule applies | parameter (A1) |
| 165 | C6D25 | adverse event | neutrophils | grade 3 serious; resolves by day 167 | no protocol rule applies | parameter (A1) |
| 168 | EOT | disposition | end of treatment | completed planned treatment |  | protocol |
| 173 | unscheduled | adverse event | neutropenia | grade 1; resolves by day 180 | after treatment | parameter (A1) |
| 173 | unscheduled | laboratory | Absolute neutrophil count | 1.67 10^9/L (grade 1) | during neutropenia | assumption (A5) |
| 177 | unscheduled | adverse event | alopecia | grade 2; resolves by day 184 | after treatment | parameter (A1) |
| 178 | unscheduled | adverse event | rhinitis | grade 2; resolves by day 185 | after treatment | parameter (A1) |
| 179 | unscheduled | adverse event | dysgeusia | grade 2; resolves by day 186 | after treatment | parameter (A1) |
| 182 | unscheduled | adverse event | leukocytes | grade 2; resolves by day 189 | after treatment | parameter (A1) |
| 188 | unscheduled | adverse event | fever | grade 3 serious; resolves by day 202 | after treatment | parameter (A1) |
| 192 | unscheduled | adverse event | leukopenia | grade 1; resolves by day 199 | after treatment | parameter (A1) |
| 192 | unscheduled | laboratory | White blood cell count | 3.53 10^9/L (grade 1) | during leukopenia | assumption (A5) |
| 193 | unscheduled | adverse event | leukocytes_(total_wbc) | grade 2; resolves by day 200 | after treatment | parameter (A1) |
| 194 | unscheduled | adverse event | neutropenia | grade 3 serious; resolves by day 208 | after treatment | parameter (A1) |
| 194 | unscheduled | laboratory | Absolute neutrophil count | 0.95 10^9/L (grade 3) | during neutropenia | assumption (A5) |
| 195 | unscheduled | adverse event | catheter_related_infection | grade 2; resolves by day 202 | after treatment | parameter (A1) |
| 198 | unscheduled | adverse event | coughing | grade 2; resolves by day 205 | after treatment | parameter (A1) |
