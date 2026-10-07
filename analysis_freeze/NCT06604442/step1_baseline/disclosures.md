# Disclosures: information about NCT06604442 seen during the build (before the freeze)

These were seen. None was used as an input to any generation, recruitment or endpoint model.

- **2026-10-06, while setting the firewall date:** registry study dates were read from ClinicalTrials.gov (status module only):
  - start 2024-12-04;
  - primary completion 2025-08-29;
  - results first posted 2026-05-12.
  - These dates set the evidence cut-off. They also show the conduct period, which belongs to the step 14 feasibility check. No model input was changed after they were seen.
- **The trial's own publication:** its title and identifiers appeared in search results (PMC13121232; doi 10.1007/s00259-025-07732-y; JCO 2026 abstract), and some search summaries displayed headline numbers.
  - The publication was not opened.
  - It is listed as FORBIDDEN in `inputs/SCA_ALLOWED_INPUTS.csv`.
- **The user's plan:** it contains published aggregates of the trial. These are held out as validation targets (step 12); see SCA_ALLOWED_INPUTS.csv X4.
