# Patient trace S0316 (arm ARM1)

Simulated patient. Each row names how it was generated: protocol (StudySpec rule or schedule), evidence (registry), parameter (fitted asset), assumption (listed in journey_summary.json).

| Day | Visit | Category | Item | Result | Clinical consequence | Basis |
| ---: | --- | --- | --- | --- | --- | --- |
| -28 | SCREENING | screening | eligibility | ELIGIBLE | 0 criteria not checkable with generated variables | protocol (A13) |
| -28 | SCREENING | baseline | demographics | age 61.2, female, white |  | evidence |
| -28 | SCREENING | laboratory | Absolute neutrophil count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | Platelet count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | Hemoglobin | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | ALT | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | Creatinine | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| 1 | C1D1 | treatment | start carfilzomib | 20 mg/m2 | first dose; then 56 mg/m2 (the protocol's target dose) | protocol |
| 1 | C1D1 | treatment | start lenalidomide | 25 mg | first dose | protocol |
| 1 | C1D1 | treatment | start dexamethasone | 40 mg | first dose | protocol |
| 2 | C1D2 | adverse event | spasm | grade 2; resolves by day 3 | no protocol rule applies | parameter (A1) |
| 5 | C1D5 | adverse event | atrial_fibrillation | grade 3 serious; resolves by day 7 | no protocol rule applies | parameter (A1) |
| 8 | C1D8 | adverse event | headache | grade 1; resolves by day 9 | no protocol rule applies | parameter (A1) |
| 9 | C1D9 | adverse event | hypertension_variable | grade 1; resolves by day 10 | carfilzomib held until day 10 (DM034) | parameter (A1) |
| 21 | C1D21 | adverse event | upper_respiratory_infections | grade 3 serious; resolves by day 29 | carfilzomib held until day 29 (DM028) | parameter (A1) |
| 23 | C2D1 | adverse event | bone_pain | grade 1; resolves by day 29 | no protocol rule applies | parameter (A1) |
| 28 | C2D1 | adverse event | respiratory_tract_infections | grade 3 serious; resolves by day 30 | carfilzomib held until day 30 (DM028) | parameter (A1) |
| 29 | C2D1 | treatment | carfilzomib | 2/3 planned administrations | interrupted or discontinued | protocol |
| 29 | TA1 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 32 | C2D4 | adverse event | potassium,_serum-low_(hypokalemia) | grade 1; resolves by day 33 | no protocol rule applies | parameter (A1) |
| 33 | C2D5 | adverse event | lower_respiratory_tract_infection | grade 3 serious; resolves by day 35 | carfilzomib held until day 35 (DM028) | parameter (A1) |
| 35 | C2D7 | adverse event | neutrophil_count_decreased | grade 1; resolves by day 36 | no protocol rule applies | parameter (A1) |
| 35 | C2D7 | laboratory | Absolute neutrophil count | 1.79 10^9/L (grade 1) | during neutrophil_count_decreased | assumption (A5) |
| 38 | C2D10 | adverse event | sepsis | grade 3 serious; resolves by day 40 | no protocol rule applies | parameter (A1) |
| 44 | C2D16 | adverse event | upper_respiratory_infections | grade 2; resolves by day 45 | no protocol rule applies | parameter (A1) |
| 48 | C2D20 | adverse event | constipation | grade 2; resolves by day 49 | no protocol rule applies | parameter (A1) |
| 48 | C2D20 | adverse event | influenza | grade 2; resolves by day 49 | no protocol rule applies | parameter (A1) |
| 51 | C3D1 | adverse event | neutropenia | grade 1; resolves by day 57 | no protocol rule applies | parameter (A1) |
| 51 | C3D1 | laboratory | Absolute neutrophil count | 1.73 10^9/L (grade 1) | during neutropenia | assumption (A5) |
| 53 | C3D1 | adverse event | pain | grade 1; resolves by day 57 | no protocol rule applies | parameter (A1) |
| 55 | C3D1 | adverse event | thrombocytopenia | grade 3 serious; resolves by day 58 | carfilzomib held until day 58 (DM011); undecidable: DM010 | parameter (A1) |
| 55 | C3D1 | laboratory | Platelet count | 29.89 10^9/L (grade 3) | during thrombocytopenia | assumption (A5) |
| 57 | C3D1 | treatment | carfilzomib | 2/3 planned administrations | interrupted or discontinued | protocol |
| 57 | TA2 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 78 | C3D22 | adverse event | sleeplessness | grade 2; resolves by day 85 | no protocol rule applies | parameter (A1) |
| 85 | C4D1 | treatment | carfilzomib | 2/3 planned administrations | interrupted or discontinued | protocol |
| 85 | TA3 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 89 | C4D5 | adverse event | hypertension | grade 1; resolves by day 90 | carfilzomib held until day 90 (DM034) | parameter (A1) |
| 90 | C4D6 | adverse event | pneumonia | grade 1; resolves by day 91 | no protocol rule applies | parameter (A1) |
| 91 | C4D7 | adverse event | pulmonary_embolism | grade 3 serious; resolves by day 93 | carfilzomib held until day 93 (DM035) | parameter (A1) |
| 100 | C4D16 | adverse event | falls | grade 2; resolves by day 101 | no protocol rule applies | parameter (A1) |
| 104 | C4D20 | adverse event | bronchitis | grade 3 serious; resolves by day 106 | no protocol rule applies | parameter (A1) |
| 108 | C5D1 | adverse event | thrombocytopenia | grade 1; resolves by day 113 | carfilzomib held until day 113 (DM011); undecidable: DM010 | parameter (A1) |
| 108 | C5D1 | laboratory | Platelet count | 78.26 10^9/L (grade 1) | during thrombocytopenia | assumption (A5) |
| 109 | C5D1 | adverse event | hyperglycemia | grade 2; resolves by day 113 | no protocol rule applies | parameter (A1) |
| 113 | C5D1 | adverse event | hypocalcemia | grade 1; resolves by day 114 | no protocol rule applies | parameter (A1) |
| 113 | TA4 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 114 | C5D2 | adverse event | hypotension | grade 3 serious; resolves by day 116 | no protocol rule applies | parameter (A1) |
| 121 | C5D9 | adverse event | hypercholesterolemia | grade 2; resolves by day 122 | no protocol rule applies | parameter (A1) |
| 125 | C5D13 | adverse event | acute renal failure adverse events | grade 2; resolves by day 126 | no protocol rule applies | parameter (A1) |
| 132 | C5D20 | adverse event | hypokalemia | grade 1; resolves by day 133 | no protocol rule applies | parameter (A1) |
| 133 | C5D21 | adverse event | rash/desquamation | grade 1; resolves by day 134 | no protocol rule applies | parameter (A1) |
| 137 | C6D1 | adverse event | non_cardiac_chest_pain | grade 1; resolves by day 141 | no protocol rule applies | parameter (A1) |
| 140 | C6D1 | adverse event | decrease_in_appetite | grade 2; resolves by day 141 | no protocol rule applies | parameter (A1) |
| 141 | C6D1 | adverse event | cardiac_failure_secondary_to_chest_deformity | grade 3 serious; resolves by day 143 | no protocol rule applies | parameter (A1) |
| 141 | TA5 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 145 | C6D5 | adverse event | peripheral_edema | grade 2; resolves by day 146 | no protocol rule applies | parameter (A1) |
| 146 | C6D6 | adverse event | nausea | grade 2; resolves by day 147 | no protocol rule applies | parameter (A1) |
| 146 | C6D6 | adverse event | dehydration | grade 3 serious; resolves by day 148 | no protocol rule applies | parameter (A1) |
| 153 | C6D13 | adverse event | hypertension adverse events | grade 2; resolves by day 154 | carfilzomib held until day 154 (DM034) | parameter (A1) |
| 156 | C6D16 | adverse event | dizziness | grade 2; resolves by day 157 | no protocol rule applies | parameter (A1) |
| 156 | C6D16 | adverse event | dyspepsia | grade 2; resolves by day 157 | no protocol rule applies | parameter (A1) |
| 160 | C6D20 | adverse event | pain_in_limb | grade 2; resolves by day 161 | no protocol rule applies | parameter (A1) |
| 163 | C7D1 | adverse event | syncope | grade 3 serious; resolves by day 170 | no protocol rule applies | parameter (A1) |
| 166 | C7D1 | adverse event | dysgeusia | grade 2; resolves by day 169 | no protocol rule applies | parameter (A1) |
| 167 | C7D1 | adverse event | gastroenteritis | grade 2; resolves by day 169 | no protocol rule applies | parameter (A1) |
| 169 | TA6 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 170 | C7D2 | adverse event | rash_erythematous_macules_or_papules | grade 1; resolves by day 171 | no protocol rule applies | parameter (A1) |
| 175 | C7D7 | adverse event | hypertriglyceridemia | grade 1; resolves by day 176 | no protocol rule applies | parameter (A1) |
| 177 | C7D9 | adverse event | leukopenia | grade 2; resolves by day 178 | no protocol rule applies | parameter (A1) |
| 177 | C7D9 | laboratory | White blood cell count | 2.06 10^9/L (grade 2) | during leukopenia | assumption (A5) |
| 181 | C7D13 | adverse event | asthenia | grade 1; resolves by day 182 | no protocol rule applies | parameter (A1) |
| 192 | C8D1 | adverse event | fever | grade 3 serious; resolves by day 198 | no protocol rule applies | parameter (A1) |
| 197 | TA7 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 201 | C8D5 | adverse event | musculoskeletal_chest_pain | grade 1; resolves by day 202 | no protocol rule applies | parameter (A1) |
| 204 | C8D8 | adverse event | deep_vein_thrombosis | grade 3 serious; resolves by day 206 | no protocol rule applies | parameter (A1) |
| 205 | C8D9 | adverse event | febrile_neutropenia | grade 3 serious; resolves by day 207 | no protocol rule applies | parameter (A1) |
| 205 | C8D9 | laboratory | Absolute neutrophil count | 0.94 10^9/L (grade 3) | during febrile_neutropenia | assumption (A5) |
| 208 | C8D12 | adverse event | neuropathy-sensory | grade 2; resolves by day 209 | carfilzomib held until day 209 (DM030) | parameter (A1) |
| 211 | C8D15 | adverse event | thrombosis/thrombus/embolism | grade 1; resolves by day 212 | no protocol rule applies | parameter (A1) |
| 216 | C8D20 | adverse event | neuropathy-motor | grade 1; resolves by day 217 | no protocol rule applies | parameter (A1) |
| 217 | C8D21 | adverse event | fever | grade 1; resolves by day 218 | no protocol rule applies | parameter (A1) |
| 218 | C8D22 | adverse event | cataract | grade 2; resolves by day 225 | no protocol rule applies | parameter (A1) |
| 219 | C9D1 | adverse event | peripheral_nervous_system_diseases | grade 2; resolves by day 225 | no protocol rule applies | parameter (A1) |
| 222 | C9D1 | adverse event | anorexia | grade 2; resolves by day 225 | no protocol rule applies | parameter (A1) |
| 225 | TA8 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 230 | C9D6 | adverse event | neuralgia | grade 2; resolves by day 231 | no protocol rule applies | parameter (A1) |
| 233 | C9D9 | adverse event | neuropathy:_sensory | grade 2; resolves by day 234 | carfilzomib held until day 234 (DM030) | parameter (A1) |
| 248 | C10D1 | adverse event | pneumonia | grade 3 serious; resolves by day 254 | no protocol rule applies | parameter (A1) |
| 253 | TA9 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 266 | C10D14 | adverse event | vomiting | grade 2; resolves by day 267 | no protocol rule applies | parameter (A1) |
| 269 | C10D17 | adverse event | sensory_neuropathy | grade 1; resolves by day 270 | no protocol rule applies | parameter (A1) |
| 275 | C11D1 | adverse event | decreased_platelet_count | grade 2; resolves by day 281 | carfilzomib held until day 281 (DM011); undecidable: DM010 | parameter (A1) |
| 276 | C11D1 | adverse event | hypoalbuminemia | grade 2; resolves by day 281 | no protocol rule applies | parameter (A1) |
| 276 | C11D1 | adverse event | urinary_tract_infection | grade 3 serious; resolves by day 282 | carfilzomib held until day 282 (DM028) | parameter (A1) |
| 281 | C11D1 | treatment | carfilzomib | 2/3 planned administrations | interrupted or discontinued | protocol |
| 281 | TA10 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 286 | C11D6 | adverse event | platelets | grade 2; resolves by day 287 | carfilzomib held until day 287 (DM011); undecidable: DM010 | parameter (A1) |
| 287 | C11D7 | adverse event | kidney_failure_acute | grade 3 serious; resolves by day 289 | no protocol rule applies | parameter (A1) |
| 294 | C11D14 | adverse event | dry_skin | grade 1; resolves by day 295 | no protocol rule applies | parameter (A1) |
| 297 | C11D17 | adverse event | back_pain | grade 2; resolves by day 298 | no protocol rule applies | parameter (A1) |
| 309 | C12D1 | treatment | carfilzomib | 2/3 planned administrations | interrupted or discontinued | protocol |
| 309 | TA11 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 311 | C12D3 | adverse event | coughing | grade 2; resolves by day 312 | no protocol rule applies | parameter (A1) |
| 315 | C12D7 | adverse event | arthralgia | grade 2; resolves by day 316 | no protocol rule applies | parameter (A1) |
| 320 | C12D12 | adverse event | hyperglycemia | grade 3 serious; resolves by day 322 | no protocol rule applies | parameter (A1) |
| 323 | C12D15 | adverse event | hypertension | grade 2; resolves by day 324 | carfilzomib held until day 324 (DM034) | parameter (A1) |
| 333 | TA12 | adverse event | accidental_overdose | grade 3 serious; resolves by day 365 | no protocol rule applies | parameter (A1) |
| 336 | EOT | disposition | end of treatment | completed planned treatment |  | protocol |
| 337 | TA12 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 342 | TA13 | adverse event | dyspnea | grade 3 serious; resolves by day 393 | after treatment | parameter (A1) |
| 343 | TA13 | adverse event | dyspnea | grade 1; resolves by day 365 | after treatment | parameter (A1) |
| 343 | TA13 | adverse event | lower_respiratory_tract_infection | grade 2; resolves by day 365 | after treatment | parameter (A1) |
| 349 | TA13 | adverse event | respiratory_tract_infections | grade 1; resolves by day 365 | after treatment | parameter (A1) |
| 352 | TA13 | adverse event | diarrhea | grade 1; resolves by day 365 | after treatment | parameter (A1) |
| 354 | TA13 | adverse event | anemia | grade 1; resolves by day 365 | after treatment | parameter (A1) |
| 354 | TA13 | laboratory | Hemoglobin | 11.24 g/dL (grade 1) | during anemia | assumption (A5) |
| 356 | TA13 | adverse event | edema:_limb | grade 1; resolves by day 365 | after treatment | parameter (A1) |
| 359 | TA13 | adverse event | fatigue | grade 2; resolves by day 365 | after treatment | parameter (A1) |
| 362 | TA13 | adverse event | nasopharyngitis | grade 1; resolves by day 365 | after treatment | parameter (A1) |
| 366 | TA14 | adverse event | thrombosis/thrombus/embolism | grade 3 serious; resolves by day 421 | after treatment | parameter (A1) |
