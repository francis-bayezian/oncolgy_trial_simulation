# Patient trace S0051 (arm ARM2)

Simulated patient. Each row names how it was generated: protocol (StudySpec rule or schedule), evidence (registry), parameter (fitted asset), assumption (listed in journey_summary.json).

| Day | Visit | Category | Item | Result | Clinical consequence | Basis |
| ---: | --- | --- | --- | --- | --- | --- |
| -8 | SCREENING | screening | eligibility | ELIGIBLE | 0 criteria not checkable with generated variables | protocol (A13) |
| -8 | SCREENING | baseline | demographics | age 26.81, female, white |  | evidence |
| -8 | SCREENING | laboratory | Absolute neutrophil count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -8 | SCREENING | laboratory | Platelet count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -8 | SCREENING | laboratory | Hemoglobin | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -8 | SCREENING | laboratory | ALT | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -8 | SCREENING | laboratory | Creatinine | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| 1 | C1D1 | treatment | start sunitinib | 37.5 mg | first dose | protocol |
| 3 | C1D3 | adverse event | hypertension | grade 1; resolves by day 4 | no protocol rule applies | parameter (A1) |
| 38 | C2D10 | adverse event | weight_loss | grade 2; resolves by day 39 | no protocol rule applies | parameter (A1) |
| 57 | TA1 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 85 | C4D1 | treatment | sunitinib | 27/28 planned administrations | interrupted or discontinued | protocol |
| 95 | C4D11 | adverse event | white_blood_cell_decreased | grade 2; resolves by day 96 | no protocol rule applies | parameter (A1) |
| 95 | C4D11 | laboratory | White blood cell count | 2.73 10^9/L (grade 2) | during white_blood_cell_decreased | assumption (A5) |
| 106 | C4D22 | adverse event | alanine_aminotransferase_increased | grade 2; resolves by day 107 | sunitinib held until day 107 (DM037) | parameter (A1) |
| 106 | C4D22 | laboratory | ALT | 3.27 x ULN (grade 2) | during alanine_aminotransferase_increased | assumption (A5) |
| 110 | C4D26 | adverse event | palmar_plantar_erythrodysesthesia_syndrome | grade 1; resolves by day 111 | sunitinib continued (DM034) | parameter (A1) |
| 113 | TA2 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 116 | C5D4 | adverse event | skin discoloration | grade 1; resolves by day 117 | no protocol rule applies | parameter (A1) |
| 169 | TA3 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 175 | C7D7 | adverse event | lymphocyte_count_decreased | grade 1; resolves by day 176 | no protocol rule applies | parameter (A1) |
| 183 | C7D15 | adverse event | hoarseness | grade 2; resolves by day 184 | no protocol rule applies | parameter (A1) |
| 200 | C8D4 | adverse event | fever | grade 2; resolves by day 201 | sunitinib continued (DM026) | parameter (A1) |
| 216 | C8D20 | adverse event | left ventricular systolic dysfunction | grade 2; resolves by day 217 | no protocol rule applies | parameter (A1) |
| 220 | C8D24 | adverse event | abdominal_pain | grade 2; resolves by day 221 | no protocol rule applies | parameter (A1) |
| 225 | TA4 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 261 | C10D9 | adverse event | maculopapular_lesion | grade 2; resolves by day 262 | no protocol rule applies | parameter (A1) |
| 281 | TA5 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 337 | C13D1 | treatment | sunitinib | 27/28 planned administrations | interrupted or discontinued | protocol |
| 337 | TA6 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 351 | C13D15 | adverse event | aspartate_aminotransferase_increased | grade 1; resolves by day 352 | sunitinib held until day 352 (DM037) | parameter (A1) |
| 351 | C13D15 | laboratory | AST | 1.91 x ULN (grade 1) | during aspartate_aminotransferase_increased | assumption (A5) |
| 367 | C14D3 | adverse event | proteinuria | grade 1; resolves by day 368 | no protocol rule applies | parameter (A1) |
| 393 | TA7 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 416 | C15D24 | adverse event | lipase | grade 2; resolves by day 417 | no protocol rule applies | parameter (A1) |
| 449 | TA8 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 457 | C17D9 | adverse event | hypocalcemia | grade 1; resolves by day 458 | no protocol rule applies | parameter (A1) |
| 505 | TA9 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 535 | C20D3 | adverse event | hypokalemia | grade 1; resolves by day 536 | no protocol rule applies | parameter (A1) |
| 561 | TA10 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 592 | C22D4 | adverse event | flatulence | grade 1; resolves by day 593 | no protocol rule applies | parameter (A1) |
| 604 | C22D16 | adverse event | pain | grade 1; resolves by day 605 | no protocol rule applies | parameter (A1) |
| 617 | TA11 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 655 | C24D11 | adverse event | decreased_platelet_count | grade 1; resolves by day 656 | sunitinib continued (DM023) | parameter (A1) |
| 655 | C24D11 | adverse event | rash/desquamation | grade 2; resolves by day 656 | no protocol rule applies | parameter (A1) |
| 656 | C24D12 | adverse event | voice_disturbance | grade 1; resolves by day 657 | no protocol rule applies | parameter (A1) |
| 673 | TA12 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 675 | C25D3 | adverse event | upper_respiratory_infections | grade 2; resolves by day 676 | no protocol rule applies | parameter (A1) |
| 717 | C26D17 | adverse event | hand-foot syndrome | grade 1; resolves by day 718 | sunitinib continued (DM034) | parameter (A1) |
| 729 | TA13 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 730 | EOT | disposition | end of treatment | end of simulated follow-up |  | protocol |
