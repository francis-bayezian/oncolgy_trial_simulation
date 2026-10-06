# Source population (population-1.0.0)

10000 simulated patients (seed 20260927); mean age 61.5 years, range 10.3-103.4.

## Variables with a distribution

- **demographic:age** from simulation_parameters_v3 (age): [null, null]
- **demographic:sex** from simulation_parameters_v3 (categorical): {"female": 0.4282089662230335, "male": 0.5717910337769665}
- **demographic:race** from simulation_parameters_v3 (categorical): {"white": 0.7232170423159957, "asian": 0.10934371543573077, "unknown_or_not_reported": 0.0473942592007075, "black_or_african_american": 0.10170297163083374, "american_indian_or_alaska_native": 0.0060512680541228315, "more_than_one_race": 0.0091214646465875, "native_hawaiian_or_other_pacific_islander
- **demographic:ethnicity** from simulation_parameters_v3 (categorical): {"not_hispanic_or_latino": 0.9025806125645696, "hispanic_or_latino": 0.07169426712547758, "unknown_or_not_reported": 0.025725120309952856}
- **umls:C1420583** from protocol_facts (unresolved) facts ['F002', 'F011', 'F015']: null

## Unresolved variables (51): unknown for every patient

- umls:C0001899
- umls:C0005437
- umls:C0005821
- umls:C0006147
- umls:C0010294
- umls:C0019046
- umls:C0023671
- umls:C0027950
- umls:C0032961
- umls:C0038317
- umls:C0151375
- umls:C0242957
- umls:C0370231
- umls:C0476474
- umls:C0517627
- umls:C0540036
- umls:C0744827
- umls:C4721806
- var:ability_to_provide_informed_consent
- var:active_autoimmune_disease
- var:active_immunosuppressive_therapy
- var:active_infectious_process
- var:active_ischemic_heart_disease
- var:active_second_invasive_malignancy
- var:ast
- var:available_potentially_curative_therapeutic_option
- var:birth_control_use_or_agreement
- var:contraindications_to_cyp_imiquimod_allergy
- var:expected_survival
- var:female_reproductive_capacity
- var:geographic_conditions_preventing_follow_up_or_compliance
- var:histologic_confirmation
- var:hiv_history
- var:karnofsky_performance_status
- var:known_allergy_to_cyp_or_imiquimod
- var:leukapheresis_consent
- var:measurable_or_evaluable_disease
- var:myocardial_infarction_history_within_six_months
- var:non_physiologic_systemic_steroids
- var:organ_transplant_history
- var:participation_intent
- var:positive_fish_results
- var:previous_therapy_toxicity_grade
- var:psychological_conditions_preventing_follow_up_or_compliance
- var:recist_confirmed_progressive_or_refractory_sm
- var:reproductive_capacity
- var:sexual_partner_birth_control_use
- var:sm_disease_state
- var:tapa_assay_method
- var:tapa_expression_count
- var:willingness_to_provide_whole_blood

## Fact bindings

- [USABLE] votes ['FAITHFUL', 'FAITHFUL', 'FAITHFUL']: fact F002 is the share of patients whose TAPBP gene (umls:C1420583) is 'Ropporin' (characteristic_distribution: 'Ropporin expression'; level 'tumor cells derived from the bone marrow'; value 6 of 16 (37.5%) [read as proportion 0.375]; population 'patients with
- [USABLE] votes ['FAITHFUL', 'FAITHFUL', 'FAITHFUL']: fact F003 is the share of patients whose TAPBP gene (umls:C1420583) is 'Ropporin' (characteristic_distribution: 'Ropporin expression'; level 'cases of CLL'; value 6 of 14 (43%) [read as proportion 0.4286]; population 'tumor cells derived from the bone marrow';
- [USABLE] votes ['FAITHFUL', 'FAITHFUL', 'FAITHFUL']: fact F004 is the share of patients whose TAPBP gene (umls:C1420583) is 'Ropporin' (characteristic_distribution: 'Ropporin expression'; level 'cases of acute myeloid leukemia'; value 2 of 11 (18%) [read as proportion 0.1818]; population 'tumor cells derived fro
- [USABLE] votes ['FAITHFUL', 'FAITHFUL', 'FAITHFUL']: fact F011 is the share of patients whose TAPBP gene (umls:C1420583) is 'PTTG-1' (characteristic_distribution: 'PTTG-1 is expressed at the transcriptional level'; level 'being expressed'; value 63% [read as proportion 0.63]; population 'MM patients'; source pub
- [USABLE] votes ['FAITHFUL', 'FAITHFUL', 'FAITHFUL']: fact F015 is the share of patients whose TAPBP gene (umls:C1420583) is 'Span-xb' (characteristic_distribution: 'Using RT-PCR, we have detected Span-xb transcripts'; level 'patients with AML'; value 50% [read as proportion 0.5]; population 'patients with AML'; 
