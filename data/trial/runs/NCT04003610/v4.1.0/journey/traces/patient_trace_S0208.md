# Patient trace S0208 (arm ARM4)

Simulated patient. Each row names how it was generated: protocol (StudySpec rule or schedule), evidence (registry), parameter (fitted asset), assumption (listed in journey_summary.json).

| Day | Visit | Category | Item | Result | Clinical consequence | Basis |
| ---: | --- | --- | --- | --- | --- | --- |
| -35 | SCREENING | screening | eligibility | ELIGIBLE | 0 criteria not checkable with generated variables | protocol (A13) |
| -35 | SCREENING | baseline | demographics | age 50.64, female, unknown_or_not_reported |  | evidence |
| -35 | SCREENING | laboratory | Absolute neutrophil count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -35 | SCREENING | laboratory | Platelet count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -35 | SCREENING | laboratory | Hemoglobin | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -35 | SCREENING | laboratory | ALT | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -35 | SCREENING | laboratory | Creatinine | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| 1 | C1D1 | treatment | start pembrolizumab | 200 mg | first dose | protocol |
| 1 | C1D1 | treatment | start gemcitabine | 1000 mg/m2 | first dose | protocol |
| 1 | C1D1 | treatment | start carboplatin | 5 auc | first dose | protocol |
| 6 | C1D6 | adverse event | anemia | grade 1; resolves by day 7 | no protocol rule applies | parameter (A1) |
| 6 | C1D6 | laboratory | Hemoglobin | 11.79 g/dL (grade 1) | during anemia | assumption (A5) |
| 27 | C2D6 | adverse event | abdominal_pain | grade 2; resolves by day 28 | no protocol rule applies | parameter (A1) |
| 38 | C2D17 | adverse event | neoplasms_benign,_malignant_and_unspecified_(incl_cysts_and_polyps)_-_other,_specify | grade 3 serious; resolves by day 40 | no protocol rule applies | parameter (A1) |
| 45 | C3D3 | adverse event | diarrhea | grade 2; resolves by day 46 | pembrolizumab held until day 46 (DM026) | parameter (A1) |
| 50 | C3D8 | adverse event | hyperglycemia | grade 2; resolves by day 51 | undecidable: DM030 | parameter (A1) |
| 60 | C3D18 | adverse event | headache | grade 2; resolves by day 61 | no protocol rule applies | parameter (A1) |
| 61 | C3D19 | adverse event | thrombocytopenia | grade 1; resolves by day 62 | no protocol rule applies | parameter (A1) |
| 61 | C3D19 | laboratory | Platelet count | 148.97 10^9/L (grade 1) | during thrombocytopenia | assumption (A5) |
| 64 | TA1 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | evidence |
| 75 | C4D12 | adverse event | sensory_neuropathy | grade 1; resolves by day 76 | no protocol rule applies | parameter (A1) |
| 76 | C4D13 | adverse event | palmar_plantar_erythrodysesthesia_syndrome | grade 1; resolves by day 77 | pembrolizumab held until day 77 (DM035) | parameter (A1) |
| 76 | C4D13 | adverse event | creatinine_increased | grade 1; resolves by day 77 | no protocol rule applies | parameter (A1) |
| 76 | C4D13 | laboratory | Creatinine | 1.23 x ULN (grade 1) | during creatinine_increased | assumption (A5) |
| 81 | C4D18 | adverse event | pain | grade 2; resolves by day 82 | no protocol rule applies | parameter (A1) |
| 83 | C4D20 | adverse event | hematuria | grade 2; resolves by day 84 | no protocol rule applies | parameter (A1) |
| 84 | C4D21 | adverse event | hypertension_variable | grade 2; resolves by day 127 | no protocol rule applies | parameter (A1) |
| 84 | EOT | disposition | end of treatment | completed planned treatment |  | protocol |
| 92 | TA2 | adverse event | peripheral_edema | grade 2; resolves by day 127 | after treatment | parameter (A1) |
| 168 | FU1 | follow-up | follow-up visit | attended |  | protocol |
