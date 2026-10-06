# Patient trace S0027 (arm ARM2)

Simulated patient. Each row names how it was generated: protocol (StudySpec rule or schedule), evidence (registry), parameter (fitted asset), assumption (listed in journey_summary.json).

| Day | Visit | Category | Item | Result | Clinical consequence | Basis |
| ---: | --- | --- | --- | --- | --- | --- |
| -8 | SCREENING | screening | eligibility | ELIGIBLE | 0 criteria not checkable with generated variables | protocol (A13) |
| -8 | SCREENING | baseline | demographics | age 23.55, male, white |  | evidence |
| -8 | SCREENING | laboratory | Absolute neutrophil count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -8 | SCREENING | laboratory | Platelet count | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -8 | SCREENING | laboratory | Hemoglobin | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -8 | SCREENING | laboratory | ALT | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| -8 | SCREENING | laboratory | Creatinine | within normal limits (value not simulated: no evidence) |  | assumption (A10) |
| 1 | C1D1 | treatment | start sunitinib | 37.5 mg | first dose | protocol |
| 4 | C1D4 | adverse event | hoarseness | grade 1; resolves by day 5 | no protocol rule applies | parameter (A1) |
| 19 | C1D19 | adverse event | weight_loss | grade 2; resolves by day 20 | no protocol rule applies | parameter (A1) |
| 57 | TA1 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 67 | C3D11 | adverse event | maculopapular_lesion | grade 1; resolves by day 68 | no protocol rule applies | parameter (A1) |
| 113 | TA2 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 169 | C7D1 | treatment | sunitinib | 27/28 planned administrations | interrupted or discontinued | protocol |
| 169 | TA3 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 183 | C7D15 | adverse event | blood_bilirubin_increased | grade 2; resolves by day 184 | sunitinib held until day 184 (DM037) | parameter (A1) |
| 183 | C7D15 | laboratory | Total bilirubin | 1.98 x ULN (grade 2) | during blood_bilirubin_increased | assumption (A5) |
| 225 | TA4 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 281 | C11D1 | treatment | sunitinib | 27/28 planned administrations | interrupted or discontinued | protocol |
| 281 | TA5 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 289 | C11D9 | adverse event | alanine_aminotransferase_increased | grade 2; resolves by day 290 | sunitinib held until day 290 (DM037) | parameter (A1) |
| 289 | C11D9 | laboratory | ALT | 4.24 x ULN (grade 2) | during alanine_aminotransferase_increased | assumption (A5) |
| 302 | C11D22 | adverse event | headache | grade 1; resolves by day 303 | no protocol rule applies | parameter (A1) |
| 337 | TA6 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 393 | TA7 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 416 | C15D24 | adverse event | white_blood_cell_decreased | grade 2; resolves by day 417 | no protocol rule applies | parameter (A1) |
| 416 | C15D24 | laboratory | White blood cell count | 2.11 10^9/L (grade 2) | during white_blood_cell_decreased | assumption (A5) |
| 449 | TA8 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 469 | C17D21 | adverse event | liposarcoma_well_differentiated | grade 1; resolves by day 470 | no protocol rule applies | parameter (A1) |
| 475 | C17D27 | adverse event | vomiting | grade 1; resolves by day 476 | no protocol rule applies | parameter (A1) |
| 489 | C18D13 | adverse event | decreased_platelet_count | grade 1; resolves by day 490 | sunitinib continued (DM023) | parameter (A1) |
| 505 | TA9 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 556 | C20D24 | adverse event | pain | grade 2; resolves by day 557 | no protocol rule applies | parameter (A1) |
| 561 | TA10 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 588 | C21D28 | adverse event | lipase | grade 1; resolves by day 589 | no protocol rule applies | parameter (A1) |
| 588 | C21D28 | adverse event | hypocalcemia | grade 1; resolves by day 589 | no protocol rule applies | parameter (A1) |
| 617 | TA11 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 660 | C24D16 | adverse event | hypokalemia | grade 1; resolves by day 661 | no protocol rule applies | parameter (A1) |
| 673 | TA12 | tumour assessment | RECIST / protocol response criteria | no progression (response category not simulated) | continue | protocol (A7) |
| 701 | C26D1 | treatment | sunitinib | 27/28 planned administrations | interrupted or discontinued | protocol |
| 706 | C26D6 | adverse event | creatinine_increased | grade 2; resolves by day 707 | no protocol rule applies | parameter (A1) |
| 706 | C26D6 | laboratory | Creatinine | 2.59 x ULN (grade 2) | during creatinine_increased | assumption (A5) |
| 721 | C26D21 | adverse event | upper_respiratory_infections | grade 1; resolves by day 722 | no protocol rule applies | parameter (A1) |
| 727 | C26D27 | adverse event | aspartate_aminotransferase_increased | grade 2; resolves by day 728 | sunitinib held until day 728 (DM037) | parameter (A1) |
| 727 | C26D27 | laboratory | AST | 4.27 x ULN (grade 2) | during aspartate_aminotransferase_increased | assumption (A5) |
| 729 | TA13 | tumour assessment | RECIST / protocol response criteria | progressive disease | progression detected: treatment ends | protocol (A7) |
| 729 | EOT | disposition | end of treatment | disease progression |  | protocol |
| 730 | C27D2 | adverse event | Bleeding events | grade 2; resolves by day 737 | after treatment | parameter (A1) |
| 731 | unscheduled | adverse event | stomatitis | grade 1; resolves by day 738 | after treatment | parameter (A1) |
| 744 | unscheduled | adverse event | other serious adverse events (not individually predicted) | grade 3 serious; resolves by day 758 | after treatment | parameter (A1) |
| 751 | unscheduled | adverse event | hyperglycemia | grade 2; resolves by day 758 | after treatment | parameter (A1) |
