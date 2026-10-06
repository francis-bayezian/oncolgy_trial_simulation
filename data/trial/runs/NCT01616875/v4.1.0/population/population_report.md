# Source population (population-1.0.0)

10000 simulated patients (seed 20260927); mean age 64.3 years, range 18.4-105.1.

## Variables with a distribution

- **demographic:age** from simulation_parameters_v3 (age): [18.0, null]
- **demographic:sex** from simulation_parameters_v3 (categorical): {"female": 0.22926554873272195, "male": 0.770734451267278}
- **demographic:race** from simulation_parameters_v3 (categorical): {"white": 0.8143167594384816, "asian": 0.060165732338294545, "unknown_or_not_reported": 0.035371990732514645, "black_or_african_american": 0.07697541395407108, "american_indian_or_alaska_native": 0.005739632159130082, "more_than_one_race": 0.005415406074321763, "native_hawaiian_or_other_pacific_isla
- **demographic:ethnicity** from simulation_parameters_v3 (categorical): {"not_hispanic_or_latino": 0.905029651586102, "hispanic_or_latino": 0.063719540240192, "unknown_or_not_reported": 0.03125080817370596}
- **umls:C0699749** from protocol_facts (categorical) facts ['F001']: {"T2 to T4": 0.3, "__not_stated__": 0.7}

## Unresolved variables (38): unknown for every patient

- umls:C0004002
- umls:C0005437
- umls:C0005558
- umls:C0005821
- umls:C0013798
- umls:C0019046
- umls:C0027950
- umls:C0031117
- umls:C0301508
- umls:C0445034
- umls:C0806692
- umls:C1513183
- umls:C1518965
- umls:C1519630
- umls:C5441537
- var:accepted_effective_contraception
- var:active_infection_requiring_systemic_antimicrobial_medication
- var:active_secondary_cancers
- var:active_uncontrolled_gord
- var:alanine_aminotransferase
- var:baseline_egfr
- var:cisplatin_contraindications
- var:ct_imaging
- var:current_strong_cyp3a4_5_inhibitor_treatment
- var:ecog_performance_status
- var:edta_clearance_result
- var:edta_result
- var:formal_edta_clearance_testing
- var:gfr
- var:histologically_confirmed_primary_tcc_of_urinary_bladder
- var:history_of_congestive_heart_failure
- var:other_concurrent_serious_illness_or_medical_conditions
- var:peripheral_neuropathy_grade
- var:reproductive_potential
- var:severe_hypersensitivity_reaction
- var:strong_cyp3a4_5_inducer_treatment
- var:strong_cyp3a4_5_inhibitor_treatment
- var:uncontrolled_diabetes_mellitus

## Fact bindings

- [USABLE] votes ['FAITHFUL', 'FAITHFUL', 'FAITHFUL']: fact F001 is the share of patients whose disease stage (umls:C0699749) is 'T2 to T4' (characteristic_distribution: 'disease invading into the\nmuscle wall of the bladder'; level 'tumour stage T2 or greater'; value 30% [read as proportion 0.3]; population 'case
