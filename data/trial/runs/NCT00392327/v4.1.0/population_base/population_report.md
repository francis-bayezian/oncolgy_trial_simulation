# Source population (population-1.0.0)

10000 simulated patients (seed 20260927); mean age 10.6 years, range 3.0-21.7.

## Variables with a distribution

- **demographic:age** from simulation_parameters_v3 (age): [3.0, 22.0]
- **demographic:ethnicity** from protocol_projection (categorical_given_sex) facts ['F076', 'F077', 'F079', 'F080', 'F082', 'F083']: {"female": {"hispanic_or_latino": 0.11464968152866242, "not_hispanic_or_latino": 0.8789808917197452, "unknown_or_not_reported": 0.006369426751592357}, "male": {"hispanic_or_latino": 0.102880658436214, "not_hispanic_or_latino": 0.8930041152263375, "unknown_or_not_reported": 0.00411522633744856}}
- **demographic:race** from protocol_projection (categorical_given_sex) facts ['F088', 'F089', 'F091', 'F092', 'F094', 'F095', 'F097', 'F098', 'F100', 'F101', 'F103', 'F104', 'F106', 'F107']: {"female": {"american_indian_or_alaska_native": 0.012738853503184714, "asian": 0.03184713375796178, "black_or_african_american": 0.05732484076433121, "native_hawaiian_or_other_pacific_islander": 0.006369426751592357, "white": 0.8726114649681529, "other": 0.012738853503184714, "unknown_or_not_reporte
- **demographic:sex** from protocol_projection (categorical): {"female": 0.3925, "male": 0.6075}
- **var:tumor_location** from protocol_facts (categorical) facts ['F019']: {"Medulloblastoma": 0.7128378378378378, "__not_stated__": 0.28716216216216217}
- **umls:C0543478** from protocol_facts (threshold_share) facts ['F068']: {"op": ">=", "value": 1.5, "unit": "cm2"}; p_meets 0.342 (CCG-99701)

## Unresolved variables (38): unknown for every patient

- umls:C0001899
- umls:C0005437
- umls:C0005821
- umls:C0007591
- umls:C0011900
- umls:C0019046
- umls:C0019638
- umls:C0023671
- umls:C0032976
- umls:C0037943
- umls:C0038874
- umls:C0242192
- umls:C0600061
- umls:C0699749
- umls:C0812399
- umls:C0948762
- umls:C1336538
- umls:C1550320
- umls:C1711202
- umls:C2828358
- umls:C3665472
- umls:C4697811
- umls:C5444850
- var:agreement_not_to_breast_feed
- var:anti_seizure_medications
- var:dissemination_status
- var:effective_contraceptive_method_agreement
- var:karnofsky_performance_level
- var:laboratory_values
- var:lansky_performance_scale
- var:menarchal_status
- var:positive_csf_cytology
- var:postoperative_head_mri
- var:postoperative_spinal_tap
- var:prior_therapy_status
- var:radioisotope_gfr
- var:reproductive_potential
- var:spinal_subarachnoid_metastases_documentation

## Fact bindings

- [USABLE] votes ['FAITHFUL', 'FAITHFUL', 'FAITHFUL']: fact F019 is the share of patients whose tumor location (var:tumor_location) is 'Medulloblastoma' (characteristic_distribution: 'patients'; level 'medulloblastoma'; value 211 of 296 (211) patients [read as proportion 0.7128]; at 'As of Amendment #2'; populatio
- [REVIEW_REQUIRED] votes ['FAITHFUL', 'FAITHFUL', 'FAITHFUL']: fact F021 is the share of patients whose Supratentorial Embryonal Tumor, Not Otherwise Specified (umls:C1336538) is 'supratentorial PNET' (characteristic_distribution: 'enrolled patients'; level 'supratentorial PNET'; value less than 30% [read as proportion 0. - issues: ['the fact states a bound (less than), not a value to sample from']
- [USABLE] votes ['FAITHFUL', 'FAITHFUL', 'FAITHFUL']: fact F068 is the share of patients whose Residual Tumor meets 'residual tumor measuring at least 1.5 cm2', the variable used in the rule condition 'residual greater than 1.5 cm2' of ST1 (characteristic_distribution: 'residual tumor'; level 'residual tumor meas
- [USABLE] votes ['FAITHFUL', 'FAITHFUL', 'FAITHFUL']: fact F076 is the number of patients with sex = 'female' AND ethnicity = 'hispanic_or_latino' (enrollment_projection: 'Females'; level 'Hispanic or Latino'; value 18 patients; population 'Females'; source this_protocol_projection (Expected Accrual by Sex and Ra
- [USABLE] votes ['FAITHFUL', 'FAITHFUL', 'FAITHFUL']: fact F077 is the number of patients with sex = 'male' AND ethnicity = 'hispanic_or_latino' (enrollment_projection: 'Males'; level 'Hispanic or Latino'; value 25 patients; population 'Males'; source this_protocol_projection (Expected Accrual by Sex and Race/Eth
- [USABLE] votes ['FAITHFUL', 'FAITHFUL', 'FAITHFUL']: fact F079 is the number of patients with sex = 'female' AND ethnicity = 'not_hispanic_or_latino' (enrollment_projection: 'Females'; level 'Not Hispanic or Latino'; value 138 patients; population 'Females'; source this_protocol_projection (Expected Accrual by S
- [USABLE] votes ['FAITHFUL', 'FAITHFUL', 'FAITHFUL']: fact F080 is the number of patients with sex = 'male' AND ethnicity = 'not_hispanic_or_latino' (enrollment_projection: 'Males'; level 'Not Hispanic or Latino'; value 217 patients; population 'Males'; source this_protocol_projection (Expected Accrual by Sex and
- [USABLE] votes ['FAITHFUL', 'FAITHFUL', 'FAITHFUL']: fact F082 is the number of patients with sex = 'female' AND ethnicity = 'unknown_or_not_reported' (enrollment_projection: 'Females'; level 'Unknown'; value 1 patients; population 'Females'; source this_protocol_projection (Expected Accrual by Sex and Race/Ethn
- [USABLE] votes ['FAITHFUL', 'FAITHFUL', 'FAITHFUL']: fact F083 is the number of patients with sex = 'male' AND ethnicity = 'unknown_or_not_reported' (enrollment_projection: 'Males'; level 'Unknown'; value 1 patients; population 'Males'; source this_protocol_projection (Expected Accrual by Sex and Race/Ethnicity 
- [USABLE] votes ['FAITHFUL', 'FAITHFUL', 'FAITHFUL']: fact F088 is the number of patients with sex = 'female' AND race = 'american_indian_or_alaska_native' (enrollment_projection: 'Females'; level 'American Indian or Alaskan Native'; value 2 patients; population 'Females'; source this_protocol_projection (Expecte
- [USABLE] votes ['FAITHFUL', 'FAITHFUL', 'FAITHFUL']: fact F089 is the number of patients with sex = 'male' AND race = 'american_indian_or_alaska_native' (enrollment_projection: 'Males'; level 'American Indian or Alaskan Native'; value 2 patients; population 'Males'; source this_protocol_projection (Expected Accr
- [USABLE] votes ['FAITHFUL', 'FAITHFUL', 'FAITHFUL']: fact F091 is the number of patients with sex = 'female' AND race = 'asian' (enrollment_projection: 'Females'; level 'Asian'; value 5 patients; population 'Females'; source this_protocol_projection (Expected Accrual by Sex and Race/Ethnicity for the Additional 
- [USABLE] votes ['FAITHFUL', 'FAITHFUL', 'FAITHFUL']: fact F092 is the number of patients with sex = 'male' AND race = 'asian' (enrollment_projection: 'Males'; level 'Asian'; value 7 patients; population 'Males'; source this_protocol_projection (Expected Accrual by Sex and Race/Ethnicity for the Additional 100))
- [USABLE] votes ['FAITHFUL', 'FAITHFUL', 'FAITHFUL']: fact F094 is the number of patients with sex = 'female' AND race = 'black_or_african_american' (enrollment_projection: 'Females'; level 'Black or African American'; value 9 patients; population 'Females'; source this_protocol_projection (Expected Accrual by Se
- [USABLE] votes ['FAITHFUL', 'FAITHFUL', 'FAITHFUL']: fact F095 is the number of patients with sex = 'male' AND race = 'black_or_african_american' (enrollment_projection: 'Males'; level 'Black or African American'; value 17 patients; population 'Males'; source this_protocol_projection (Expected Accrual by Sex and
- [USABLE] votes ['FAITHFUL', 'FAITHFUL', 'FAITHFUL']: fact F097 is the number of patients with sex = 'female' AND race = 'native_hawaiian_or_other_pacific_islander' (enrollment_projection: 'Females'; level 'Native Hawaiian or other Pacific Islander'; value 1 patients; population 'Females'; source this_protocol_pr
- [USABLE] votes ['FAITHFUL', 'FAITHFUL', 'FAITHFUL']: fact F098 is the number of patients with sex = 'male' AND race = 'native_hawaiian_or_other_pacific_islander' (enrollment_projection: 'Males'; level 'Native Hawaiian or other Pacific Islander'; value 2 patients; population 'Males'; source this_protocol_projecti
- [USABLE] votes ['FAITHFUL', 'FAITHFUL', 'FAITHFUL']: fact F100 is the number of patients with sex = 'female' AND race = 'white' (enrollment_projection: 'Females'; level 'White'; value 137 patients; population 'Females'; source this_protocol_projection (Expected Accrual by Sex and Race/Ethnicity for the Additiona
- [USABLE] votes ['FAITHFUL', 'FAITHFUL', 'FAITHFUL']: fact F101 is the number of patients with sex = 'male' AND race = 'white' (enrollment_projection: 'Males'; level 'White'; value 209 patients; population 'Males'; source this_protocol_projection (Expected Accrual by Sex and Race/Ethnicity for the Additional 100)
- [USABLE] votes ['FAITHFUL', 'FAITHFUL', 'FAITHFUL']: fact F103 is the number of patients with sex = 'female' AND race = 'other' (enrollment_projection: 'Females'; level 'Other'; value 2 patients; population 'Females'; source this_protocol_projection (Expected Accrual by Sex and Race/Ethnicity for the Additional 
- [USABLE] votes ['FAITHFUL', 'FAITHFUL', 'FAITHFUL']: fact F104 is the number of patients with sex = 'male' AND race = 'other' (enrollment_projection: 'Males'; level 'Other'; value 4 patients; population 'Males'; source this_protocol_projection (Expected Accrual by Sex and Race/Ethnicity for the Additional 100))
- [USABLE] votes ['FAITHFUL', 'FAITHFUL', 'FAITHFUL']: fact F106 is the number of patients with sex = 'female' AND race = 'unknown_or_not_reported' (enrollment_projection: 'Females'; level 'Not Reported'; value 1 patients; population 'Females'; source this_protocol_projection (Expected Accrual by Sex and Race/Ethn
- [USABLE] votes ['FAITHFUL', 'FAITHFUL', 'FAITHFUL']: fact F107 is the number of patients with sex = 'male' AND race = 'unknown_or_not_reported' (enrollment_projection: 'Males'; level 'Not Reported'; value 2 patients; population 'Males'; source this_protocol_projection (Expected Accrual by Sex and Race/Ethnicity 
