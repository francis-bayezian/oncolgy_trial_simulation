# Patient trace S0001 (arm ARM2)

Simulated patient. Each row names how it was generated: protocol (StudySpec rule or schedule), evidence (registry), parameter (fitted asset), assumption (listed in journey_summary.json).

| Day | Visit | Category | Item | Result | Clinical consequence | Basis |
| ---: | --- | --- | --- | --- | --- | --- |
| -8 | SCREENING | screening | eligibility | ELIGIBLE | 0 criteria not checkable with generated variables | protocol (A13) |
| -8 | SCREENING | baseline | demographics | age 21.1, male, white |  | evidence |
| -8 | SCREENING | laboratory | Absolute neutrophil count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -8 | SCREENING | laboratory | Platelet count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -8 | SCREENING | laboratory | Hemoglobin | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -8 | SCREENING | laboratory | ALT | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -8 | SCREENING | laboratory | Creatinine | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| 1 | C1D1 | treatment | start sunitinib | 37.5 mg | first dose | protocol |
| 18 | C1D18 | adverse event | treatment-emergent LVEF values below the lower limit of normal (LLN) | grade 1; resolves by day 19 | no protocol rule applies | parameter (A1) |
| 56 | C2D28 | adverse event | skin discoloration | grade 1; resolves by day 57 | no protocol rule applies | parameter (A1) |
| 57 | TA1 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 68 | C3D12 | adverse event | hoarseness | grade 2; resolves by day 69 | no protocol rule applies | parameter (A1) |
| 113 | TA2 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 119 | C5D7 | adverse event | vomiting | grade 1; resolves by day 120 | no protocol rule applies | parameter (A1) |
| 143 | C6D3 | adverse event | hypocalcemia | grade 2; resolves by day 144 | no protocol rule applies | parameter (A1) |
| 147 | C6D7 | adverse event | fever | grade 2; resolves by day 148 | sunitinib continued (DM026) | parameter (A1) |
| 151 | C6D11 | adverse event | palmar_plantar_erythrodysesthesia_syndrome | grade 2; resolves by day 152 | sunitinib continued (DM034) | parameter (A1) |
| 152 | C6D12 | adverse event | diarrhea | grade 1; resolves by day 153 | no protocol rule applies | parameter (A1) |
| 169 | TA3 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 204 | C8D8 | adverse event | Bleeding events | grade 2; resolves by day 205 | no protocol rule applies | parameter (A1) |
| 225 | TA4 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 233 | C9D9 | adverse event | Hypothyroidism | grade 2; resolves by day 234 | no protocol rule applies | parameter (A1) |
| 253 | C10D1 | treatment | sunitinib | 27/28 planned administrations | interrupted or discontinued | protocol |
| 277 | C10D25 | adverse event | aspartate_aminotransferase_increased | grade 2; resolves by day 278 | sunitinib held until day 278 (DM037) | parameter (A1) |
| 277 | C10D25 | laboratory | AST | 4.1 x ULN (grade 2) | during aspartate_aminotransferase_increased | assumption (A5) |
| 281 | TA5 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 298 | C11D18 | adverse event | flatulence | grade 1; resolves by day 299 | no protocol rule applies | parameter (A1) |
| 309 | C12D1 | adverse event | pain | grade 1; resolves by day 310 | no protocol rule applies | parameter (A1) |
| 323 | C12D15 | adverse event | decreased_platelet_count | grade 1; resolves by day 324 | sunitinib continued (DM023) | parameter (A1) |
| 337 | TA6 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 345 | C13D9 | adverse event | lipase | grade 1; resolves by day 346 | no protocol rule applies | parameter (A1) |
| 348 | C13D12 | adverse event | voice_disturbance | grade 2; resolves by day 349 | no protocol rule applies | parameter (A1) |
| 365 | C14D1 | treatment | sunitinib | 27/28 planned administrations | interrupted or discontinued | protocol |
| 372 | C14D8 | adverse event | alanine_aminotransferase_increased | grade 1; resolves by day 373 | sunitinib held until day 373 (DM037) | parameter (A1) |
| 372 | C14D8 | laboratory | ALT | 1.38 x ULN (grade 1) | during alanine_aminotransferase_increased | assumption (A5) |
| 393 | TA7 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 415 | C15D23 | adverse event | upper_respiratory_infections | grade 1; resolves by day 416 | no protocol rule applies | parameter (A1) |
| 419 | C15D27 | adverse event | skin_and_subcutaneous_tissue_disorders_-_other | grade 2; resolves by day 420 | no protocol rule applies | parameter (A1) |
| 449 | TA8 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 479 | C18D3 | adverse event | dry_skin | grade 2; resolves by day 480 | no protocol rule applies | parameter (A1) |
| 505 | C19D1 | adverse event | hand-foot skin reactions | grade 1; resolves by day 506 | sunitinib continued (DM034) | parameter (A1) |
| 505 | TA9 | tumour assessment | RECIST / protocol response criteria | progressive disease | progression detected: treatment ends | protocol (A7) |
| 505 | EOT | disposition | end of treatment | disease progression |  | protocol |
| 530 | C19D26 | adverse event | diarrhea | grade 1; resolves by day 531 | after treatment | parameter (A1) |
