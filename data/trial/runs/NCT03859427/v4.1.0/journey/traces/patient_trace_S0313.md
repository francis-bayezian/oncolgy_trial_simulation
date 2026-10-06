# Patient trace S0313 (arm ARM1)

Simulated patient. Each row names how it was generated: protocol (StudySpec rule or schedule), evidence (registry), parameter (fitted asset), assumption (listed in journey_summary.json).

| Day | Visit | Category | Item | Result | Clinical consequence | Basis |
| ---: | --- | --- | --- | --- | --- | --- |
| -28 | SCREENING | screening | eligibility | ELIGIBLE | 0 criteria not checkable with generated variables | protocol (A13) |
| -28 | SCREENING | baseline | demographics | age 37.96, male, white |  | evidence |
| -28 | SCREENING | laboratory | Absolute neutrophil count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | Platelet count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | Hemoglobin | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | ALT | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -28 | SCREENING | laboratory | Creatinine | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| 1 | C1D1 | treatment | start carfilzomib | 20 mg/m2 | first dose; then 56 mg/m2 (the protocol's target dose) | protocol |
| 1 | C1D1 | treatment | start lenalidomide | 25 mg | first dose | protocol |
| 1 | C1D1 | treatment | start dexamethasone | 40 mg | first dose | protocol |
| 1 | C1D1 | treatment | carfilzomib | 2/3 planned administrations | interrupted or discontinued | protocol |
| 3 | C1D3 | adverse event | hypokalemia | grade 1; resolves by day 4 | no protocol rule applies | parameter (A1) |
| 4 | C1D4 | adverse event | back_pain | grade 2; resolves by day 5 | no protocol rule applies | parameter (A1) |
| 7 | C1D7 | adverse event | hypertriglyceridemia | grade 1; resolves by day 8 | no protocol rule applies | parameter (A1) |
| 7 | C1D7 | adverse event | influenza | grade 1; resolves by day 8 | no protocol rule applies | parameter (A1) |
| 8 | C1D8 | adverse event | anemia | grade 2; resolves by day 9 | no protocol rule applies | parameter (A1) |
| 8 | C1D8 | laboratory | Hemoglobin | 9.63 g/dL (grade 2) | during anemia | assumption (A5) |
| 10 | C1D10 | adverse event | bronchitis | grade 3 serious; resolves by day 12 | no protocol rule applies | parameter (A1) |
| 12 | C1D12 | adverse event | dizziness | grade 2; resolves by day 13 | no protocol rule applies | parameter (A1) |
| 12 | C1D12 | adverse event | sepsis | grade 3 serious; resolves by day 14 | no protocol rule applies | parameter (A1) |
| 15 | C1D15 | adverse event | deep_vein_thrombosis | grade 3 serious; resolves by day 17 | no protocol rule applies | parameter (A1) |
| 15 | C1D15 | adverse event | hypertension | grade 1; resolves by day 16 | carfilzomib held until day 16 (DM034) | parameter (A1) |
| 17 | C1D17 | adverse event | rash_erythematous_macules_or_papules | grade 2; resolves by day 18 | no protocol rule applies | parameter (A1) |
| 19 | C1D19 | adverse event | neuropathy:_sensory | grade 1; resolves by day 20 | no protocol rule applies | parameter (A1) |
| 25 | C2D1 | adverse event | coughing | grade 1; resolves by day 29 | no protocol rule applies | parameter (A1) |
| 29 | TA1 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 30 | C2D2 | adverse event | sensory_neuropathy | grade 1; resolves by day 31 | no protocol rule applies | parameter (A1) |
| 30 | C2D2 | adverse event | non_cardiac_chest_pain | grade 1; resolves by day 31 | no protocol rule applies | parameter (A1) |
| 32 | C2D4 | adverse event | hypocalcemia | grade 1; resolves by day 33 | no protocol rule applies | parameter (A1) |
| 32 | C2D4 | adverse event | anorexia | grade 2; resolves by day 33 | no protocol rule applies | parameter (A1) |
| 38 | C2D10 | adverse event | neuropathy-motor | grade 2; resolves by day 39 | carfilzomib held until day 39 (DM030) | parameter (A1) |
| 39 | C2D11 | adverse event | hypercholesterolemia | grade 2; resolves by day 40 | no protocol rule applies | parameter (A1) |
| 43 | C2D15 | adverse event | nausea | grade 2; resolves by day 44 | no protocol rule applies | parameter (A1) |
| 46 | C2D18 | adverse event | fever | grade 2; resolves by day 47 | no protocol rule applies | parameter (A1) |
| 47 | C2D19 | adverse event | hypertension adverse events | grade 2; resolves by day 48 | carfilzomib held until day 48 (DM034) | parameter (A1) |
| 50 | C2D22 | adverse event | dyspnea | grade 1; resolves by day 57 | carfilzomib held until day 57 (DM032) | parameter (A1) |
| 57 | C3D1 | treatment | carfilzomib | 2/3 planned administrations | interrupted or discontinued | protocol |
| 57 | TA2 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 62 | C3D6 | adverse event | hypertension_variable | grade 2; resolves by day 63 | carfilzomib held until day 63 (DM034) | parameter (A1) |
| 62 | C3D6 | adverse event | peripheral_nervous_system_diseases | grade 1; resolves by day 63 | no protocol rule applies | parameter (A1) |
| 64 | C3D8 | adverse event | neuropathy-sensory | grade 2; resolves by day 65 | carfilzomib held until day 65 (DM030) | parameter (A1) |
| 64 | C3D8 | adverse event | lower_respiratory_tract_infection | grade 3 serious; resolves by day 66 | carfilzomib held until day 66 (DM028) | parameter (A1) |
| 64 | C3D8 | adverse event | hyperglycemia | grade 3 serious; resolves by day 66 | no protocol rule applies | parameter (A1) |
| 66 | C3D10 | adverse event | rash/desquamation | grade 1; resolves by day 67 | no protocol rule applies | parameter (A1) |
| 66 | C3D10 | adverse event | acute renal failure adverse events | grade 1; resolves by day 67 | no protocol rule applies | parameter (A1) |
| 67 | C3D11 | adverse event | respiratory_tract_infections | grade 3 serious; resolves by day 69 | carfilzomib held until day 69 (DM028) | parameter (A1) |
| 68 | C3D12 | adverse event | falls | grade 2; resolves by day 69 | no protocol rule applies | parameter (A1) |
| 68 | C3D12 | adverse event | thrombosis/thrombus/embolism | grade 3 serious; resolves by day 70 | no protocol rule applies | parameter (A1) |
| 70 | C3D14 | adverse event | pneumonia | grade 2; resolves by day 71 | no protocol rule applies | parameter (A1) |
| 72 | C3D16 | adverse event | bone_pain | grade 2; resolves by day 73 | no protocol rule applies | parameter (A1) |
| 72 | C3D16 | adverse event | dysgeusia | grade 1; resolves by day 73 | no protocol rule applies | parameter (A1) |
| 76 | C3D20 | adverse event | potassium,_serum-low_(hypokalemia) | grade 2; resolves by day 77 | no protocol rule applies | parameter (A1) |
| 78 | C3D22 | adverse event | pain | grade 1; resolves by day 85 | no protocol rule applies | parameter (A1) |
| 79 | C4D1 | adverse event | arthralgia | grade 2; resolves by day 85 | no protocol rule applies | parameter (A1) |
| 80 | C4D1 | adverse event | hemoglobin_normal_12_16_gm | grade 2; resolves by day 85 | no protocol rule applies | parameter (A1) |
| 81 | C4D1 | adverse event | thrombocytopenia | grade 3 serious; resolves by day 86 | carfilzomib held until day 86 (DM011); undecidable: DM010 | parameter (A1) |
| 81 | C4D1 | laboratory | Platelet count | 45.67 10^9/L (grade 3) | during thrombocytopenia | assumption (A5) |
| 82 | C4D1 | adverse event | weight_loss | grade 2; resolves by day 85 | no protocol rule applies | parameter (A1) |
| 85 | C4D1 | treatment | carfilzomib | 2/3 planned administrations | interrupted or discontinued | protocol |
| 85 | TA3 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 87 | C4D3 | adverse event | decrease_in_appetite | grade 1; resolves by day 88 | no protocol rule applies | parameter (A1) |
| 88 | C4D4 | adverse event | thrombocytopenia | grade 2; resolves by day 89 | carfilzomib held until day 89 (DM011); undecidable: DM010 | parameter (A1) |
| 88 | C4D4 | laboratory | Platelet count | 53.1 10^9/L (grade 2) | during thrombocytopenia | assumption (A5) |
| 88 | C4D4 | adverse event | hypertension | grade 2; resolves by day 89 | carfilzomib held until day 89 (DM034) | parameter (A1) |
| 90 | C4D6 | adverse event | decreased_platelet_count | grade 1; resolves by day 91 | carfilzomib held until day 91 (DM011); undecidable: DM010 | parameter (A1) |
| 91 | C4D7 | adverse event | neutrophil_count_decreased | grade 2; resolves by day 92 | no protocol rule applies | parameter (A1) |
| 91 | C4D7 | laboratory | Absolute neutrophil count | 1.25 10^9/L (grade 2) | during neutrophil_count_decreased | assumption (A5) |
| 92 | C4D8 | adverse event | cataract | grade 2; resolves by day 93 | no protocol rule applies | parameter (A1) |
| 92 | C4D8 | adverse event | dry_skin | grade 1; resolves by day 93 | no protocol rule applies | parameter (A1) |
| 98 | C4D14 | adverse event | neuropathic_pain | grade 1; resolves by day 99 | no protocol rule applies | parameter (A1) |
| 100 | C4D16 | adverse event | upper_respiratory_infections | grade 2; resolves by day 101 | no protocol rule applies | parameter (A1) |
| 101 | C4D17 | adverse event | lower_respiratory_tract_infection | grade 2; resolves by day 102 | no protocol rule applies | parameter (A1) |
| 101 | C4D17 | adverse event | neuralgia | grade 1; resolves by day 102 | no protocol rule applies | parameter (A1) |
| 104 | C4D20 | adverse event | upper_respiratory_infections | grade 3 serious; resolves by day 106 | carfilzomib held until day 106 (DM028) | parameter (A1) |
| 105 | C4D21 | adverse event | sleeplessness | grade 1; resolves by day 106 | no protocol rule applies | parameter (A1) |
| 110 | C5D1 | adverse event | constipation | grade 1; resolves by day 113 | no protocol rule applies | parameter (A1) |
| 110 | EOT | disposition | end of treatment | adverse event (registry discontinuation rate) |  | evidence (A14) |
| 111 | C5D1 | adverse event | urinary_tract_infection | grade 3 serious; resolves by day 114 | after treatment | parameter (A1) |
| 116 | C5D4 | adverse event | fever | grade 3 serious; resolves by day 118 | after treatment | parameter (A1) |
| 117 | C5D5 | adverse event | pain_in_limb | grade 2; resolves by day 118 | after treatment | parameter (A1) |
| 119 | C5D7 | adverse event | diarrhea | grade 2; resolves by day 120 | after treatment | parameter (A1) |
| 120 | C5D8 | adverse event | headache | grade 2; resolves by day 121 | after treatment | parameter (A1) |
| 122 | C5D10 | adverse event | leukopenia | grade 1; resolves by day 123 | after treatment | parameter (A1) |
| 122 | C5D10 | laboratory | White blood cell count | 3.53 10^9/L (grade 1) | during leukopenia | assumption (A5) |
| 123 | C5D11 | adverse event | asthenia | grade 2; resolves by day 124 | after treatment | parameter (A1) |
| 124 | C5D12 | adverse event | vomiting | grade 1; resolves by day 125 | after treatment | parameter (A1) |
| 124 | C5D12 | adverse event | dyspepsia | grade 1; resolves by day 125 | after treatment | parameter (A1) |
| 126 | C5D14 | adverse event | nasopharyngitis | grade 1; resolves by day 127 | after treatment | parameter (A1) |
| 130 | C5D18 | adverse event | neutropenia | grade 1; resolves by day 131 | after treatment | parameter (A1) |
| 130 | C5D18 | laboratory | Absolute neutrophil count | 1.79 10^9/L (grade 1) | during neutropenia | assumption (A5) |
| 140 | C6D1 | adverse event | spasm | grade 2; resolves by day 141 | after treatment | parameter (A1) |
