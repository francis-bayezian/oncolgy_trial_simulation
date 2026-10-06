# Patient trace S0169 (arm ARM1)

Simulated patient. Each row names how it was generated: protocol (StudySpec rule or schedule), evidence (registry), parameter (fitted asset), assumption (listed in journey_summary.json).

| Day | Visit | Category | Item | Result | Clinical consequence | Basis |
| ---: | --- | --- | --- | --- | --- | --- |
| -28 | SCREENING | screening | eligibility | ELIGIBLE | 0 criteria not checkable with generated variables | protocol (A13) |
| -28 | SCREENING | baseline | demographics | age 62.53, male, white |  | evidence |
| -28 | SCREENING | laboratory | Absolute neutrophil count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | Platelet count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | Hemoglobin | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | ALT | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | Creatinine | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| 1 | C1D1 | treatment | start carfilzomib | 20 mg/m2 | first dose; then 56 mg/m2 (the protocol's target dose) | protocol |
| 1 | C1D1 | treatment | start lenalidomide | 25 mg | first dose | protocol |
| 1 | C1D1 | treatment | start dexamethasone | 40 mg | first dose | protocol |
| 3 | C1D3 | adverse event | abdominal_pain | grade 1; resolves by day 4 | no protocol rule applies | parameter (A1) |
| 3 | C1D3 | adverse event | neuralgia | grade 2; resolves by day 4 | no protocol rule applies | parameter (A1) |
| 4 | C1D4 | adverse event | hypertension_variable | grade 2; resolves by day 5 | carfilzomib held until day 5 (DM034) | parameter (A1) |
| 5 | C1D5 | adverse event | lower_respiratory_tract_infection | grade 2; resolves by day 6 | no protocol rule applies | parameter (A1) |
| 6 | C1D6 | adverse event | potassium,_serum-low_(hypokalemia) | grade 1; resolves by day 7 | no protocol rule applies | parameter (A1) |
| 7 | C1D7 | adverse event | dyspepsia | grade 2; resolves by day 8 | no protocol rule applies | parameter (A1) |
| 9 | C1D9 | adverse event | sensory_neuropathy | grade 1; resolves by day 10 | no protocol rule applies | parameter (A1) |
| 9 | C1D9 | adverse event | fever | grade 1; resolves by day 10 | no protocol rule applies | parameter (A1) |
| 10 | C1D10 | adverse event | weight_loss | grade 2; resolves by day 11 | no protocol rule applies | parameter (A1) |
| 11 | C1D11 | adverse event | upper_respiratory_infections | grade 3 serious; resolves by day 13 | carfilzomib held until day 13 (DM028) | parameter (A1) |
| 12 | C1D12 | adverse event | sleeplessness | grade 2; resolves by day 13 | no protocol rule applies | parameter (A1) |
| 12 | C1D12 | adverse event | asthenia | grade 2; resolves by day 13 | no protocol rule applies | parameter (A1) |
| 12 | C1D12 | adverse event | rash/desquamation | grade 2; resolves by day 13 | no protocol rule applies | parameter (A1) |
| 13 | C1D13 | adverse event | falls | grade 2; resolves by day 14 | no protocol rule applies | parameter (A1) |
| 14 | C1D14 | adverse event | diarrhea | grade 1; resolves by day 15 | no protocol rule applies | parameter (A1) |
| 14 | C1D14 | adverse event | peripheral_nervous_system_diseases | grade 1; resolves by day 15 | no protocol rule applies | parameter (A1) |
| 15 | C1D15 | adverse event | vomiting | grade 2; resolves by day 16 | no protocol rule applies | parameter (A1) |
| 16 | C1D16 | adverse event | non_cardiac_chest_pain | grade 2; resolves by day 17 | no protocol rule applies | parameter (A1) |
| 17 | C1D17 | adverse event | neutropenia | grade 1; resolves by day 18 | no protocol rule applies | parameter (A1) |
| 17 | C1D17 | laboratory | Absolute neutrophil count | 1.94 10^9/L (grade 1) | during neutropenia | assumption (A5) |
| 18 | C1D18 | adverse event | decreased_platelet_count | grade 2; resolves by day 19 | carfilzomib held until day 19 (DM011); undecidable: DM010 | parameter (A1) |
| 20 | C1D20 | adverse event | upper_respiratory_infections | grade 1; resolves by day 21 | no protocol rule applies | parameter (A1) |
| 22 | C1D22 | adverse event | leukopenia | grade 2; resolves by day 29 | no protocol rule applies | parameter (A1) |
| 22 | C1D22 | laboratory | White blood cell count | 2.41 10^9/L (grade 2) | during leukopenia | assumption (A5) |
| 22 | C1D22 | adverse event | cataract | grade 2; resolves by day 29 | no protocol rule applies | parameter (A1) |
| 22 | C1D22 | adverse event | accidental_overdose | grade 3 serious; resolves by day 30 | no protocol rule applies | parameter (A1) |
| 22 | C1D22 | adverse event | dyspnea | grade 3 serious; resolves by day 30 | carfilzomib held until day 30 (DM032) | parameter (A1) |
| 26 | C2D1 | adverse event | dizziness | grade 2; resolves by day 29 | no protocol rule applies | parameter (A1) |
| 26 | C2D1 | adverse event | platelets | grade 1; resolves by day 29 | carfilzomib held until day 29 (DM011); undecidable: DM010 | parameter (A1) |
| 26 | C2D1 | adverse event | edema:_limb | grade 1; resolves by day 29 | no protocol rule applies | parameter (A1) |
| 27 | C2D1 | adverse event | hyperglycemia | grade 3 serious; resolves by day 30 | no protocol rule applies | parameter (A1) |
| 29 | C2D1 | adverse event | hypoalbuminemia | grade 2; resolves by day 30 | no protocol rule applies | parameter (A1) |
| 29 | C2D1 | treatment | carfilzomib | 1/3 planned administrations | interrupted or discontinued | protocol |
| 29 | TA1 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 30 | C2D2 | adverse event | dyspnea | grade 2; resolves by day 31 | carfilzomib held until day 31 (DM032) | parameter (A1) |
| 31 | C2D3 | adverse event | anorexia | grade 1; resolves by day 32 | no protocol rule applies | parameter (A1) |
| 32 | C2D4 | adverse event | neuropathy-sensory | grade 2; resolves by day 33 | carfilzomib held until day 33 (DM030) | parameter (A1) |
| 33 | C2D5 | adverse event | pneumonia | grade 2; resolves by day 34 | no protocol rule applies | parameter (A1) |
| 33 | C2D5 | adverse event | thrombosis/thrombus/embolism | grade 3 serious; resolves by day 35 | no protocol rule applies | parameter (A1) |
| 34 | C2D6 | adverse event | hypertension adverse events | grade 2; resolves by day 35 | carfilzomib held until day 35 (DM034) | parameter (A1) |
| 35 | C2D7 | adverse event | influenza | grade 2; resolves by day 36 | no protocol rule applies | parameter (A1) |
| 36 | C2D8 | adverse event | hypercholesterolemia | grade 1; resolves by day 37 | no protocol rule applies | parameter (A1) |
| 36 | C2D8 | adverse event | hypotension | grade 3 serious; resolves by day 38 | no protocol rule applies | parameter (A1) |
| 36 | C2D8 | adverse event | hypertension | grade 2; resolves by day 37 | carfilzomib held until day 37 (DM034) | parameter (A1) |
| 37 | C2D9 | adverse event | gastroenteritis | grade 1; resolves by day 38 | no protocol rule applies | parameter (A1) |
| 38 | C2D10 | adverse event | respiratory_tract_infections | grade 3 serious; resolves by day 40 | carfilzomib held until day 40 (DM028) | parameter (A1) |
| 39 | C2D11 | adverse event | neuropathy-motor | grade 2; resolves by day 40 | carfilzomib held until day 40 (DM030) | parameter (A1) |
| 39 | C2D11 | adverse event | kidney_failure_acute | grade 3 serious; resolves by day 41 | no protocol rule applies | parameter (A1) |
| 39 | C2D11 | adverse event | kidney_failure | grade 3 serious; resolves by day 41 | no protocol rule applies | parameter (A1) |
| 41 | C2D13 | adverse event | fatigue | grade 2; resolves by day 42 | no protocol rule applies | parameter (A1) |
| 41 | C2D13 | adverse event | dry_skin | grade 2; resolves by day 42 | no protocol rule applies | parameter (A1) |
| 41 | C2D13 | adverse event | bronchitis | grade 3 serious; resolves by day 43 | no protocol rule applies | parameter (A1) |
| 42 | C2D14 | adverse event | decrease_in_appetite | grade 2; resolves by day 43 | no protocol rule applies | parameter (A1) |
| 42 | C2D14 | adverse event | respiratory_tract_infections | grade 1; resolves by day 43 | no protocol rule applies | parameter (A1) |
| 42 | C2D14 | adverse event | neuropathy:_sensory | grade 2; resolves by day 43 | carfilzomib held until day 43 (DM030) | parameter (A1) |
| 45 | EOT | disposition | end of treatment | withdrawal (subject, loss to follow-up or physician decision) |  | evidence |
| 46 | C2D18 | adverse event | rash_erythematous_macules_or_papules | grade 2; resolves by day 47 | after treatment | parameter (A1) |
| 46 | C2D18 | adverse event | hyponatremia | grade 2; resolves by day 47 | after treatment | parameter (A1) |
| 46 | C2D18 | adverse event | lower_respiratory_tract_infection | grade 3 serious; resolves by day 48 | after treatment | parameter (A1) |
| 48 | C2D20 | adverse event | pneumonia | grade 3 serious; resolves by day 50 | after treatment | parameter (A1) |
| 49 | C2D21 | adverse event | constipation | grade 1; resolves by day 50 | after treatment | parameter (A1) |
| 49 | C2D21 | adverse event | spasm | grade 2; resolves by day 50 | after treatment | parameter (A1) |
| 50 | C2D22 | adverse event | hypokalemia | grade 2; resolves by day 57 | after treatment | parameter (A1) |
| 51 | C3D1 | adverse event | hyperglycemia | grade 1; resolves by day 57 | after treatment | parameter (A1) |
| 52 | C3D1 | adverse event | thrombocytopenia | grade 2; resolves by day 57 | after treatment | parameter (A1) |
| 52 | C3D1 | laboratory | Platelet count | 53.17 10^9/L (grade 2) | during thrombocytopenia | assumption (A5) |
| 52 | C3D1 | adverse event | thrombocytopenia | grade 3 serious; resolves by day 58 | after treatment | parameter (A1) |
| 52 | C3D1 | laboratory | Platelet count | 42.5 10^9/L (grade 3) | during thrombocytopenia | assumption (A5) |
| 53 | C3D1 | adverse event | hypertriglyceridemia | grade 2; resolves by day 57 | after treatment | parameter (A1) |
| 54 | C3D1 | adverse event | pain | grade 2; resolves by day 57 | after treatment | parameter (A1) |
| 55 | C3D1 | adverse event | dehydration | grade 3 serious; resolves by day 58 | after treatment | parameter (A1) |
| 60 | C3D4 | adverse event | headache | grade 2; resolves by day 61 | after treatment | parameter (A1) |
| 63 | C3D7 | adverse event | peripheral_edema | grade 2; resolves by day 64 | after treatment | parameter (A1) |
| 63 | C3D7 | adverse event | hypocalcemia | grade 1; resolves by day 64 | after treatment | parameter (A1) |
| 64 | C3D8 | adverse event | coughing | grade 2; resolves by day 65 | after treatment | parameter (A1) |
| 65 | C3D9 | adverse event | neuropathic_pain | grade 2; resolves by day 66 | after treatment | parameter (A1) |
| 68 | C3D12 | adverse event | neutrophil_count_decreased | grade 2; resolves by day 69 | after treatment | parameter (A1) |
| 68 | C3D12 | laboratory | Absolute neutrophil count | 1.26 10^9/L (grade 2) | during neutrophil_count_decreased | assumption (A5) |
| 68 | C3D12 | adverse event | pulmonary_embolism | grade 3 serious; resolves by day 70 | after treatment | parameter (A1) |
| 69 | C3D13 | adverse event | pain_in_limb | grade 1; resolves by day 70 | after treatment | parameter (A1) |
| 71 | C3D15 | adverse event | hypertension | grade 1; resolves by day 72 | after treatment | parameter (A1) |
| 72 | C3D16 | adverse event | back_pain | grade 1; resolves by day 73 | after treatment | parameter (A1) |
| 72 | C3D16 | adverse event | thrombosis/thrombus/embolism | grade 1; resolves by day 73 | after treatment | parameter (A1) |
| 72 | C3D16 | adverse event | bone_pain | grade 1; resolves by day 73 | after treatment | parameter (A1) |
| 73 | C3D17 | adverse event | anemia | grade 2; resolves by day 74 | after treatment | parameter (A1) |
| 73 | C3D17 | laboratory | Hemoglobin | 9.89 g/dL (grade 2) | during anemia | assumption (A5) |
| 73 | C3D17 | adverse event | nasopharyngitis | grade 2; resolves by day 74 | after treatment | parameter (A1) |
