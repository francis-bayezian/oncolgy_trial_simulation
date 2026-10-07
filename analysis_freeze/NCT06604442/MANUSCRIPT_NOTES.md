# Manuscript wording rules (from the review of 2026-10-07)

1. **Design of the validation.**
   - Write "retrospective comparison using prespecified, outcome-independent computational inputs". Describe version locking and checksums once, in Methods or the Supplement.
   - Do not write "blinded", "prospective external validation" or "results unseen until after the model freeze".
   - The firewall shows that observed outcomes were not model inputs. Disclose what was seen (`step1_baseline/disclosures.md`).
2. **Freeze record.** Cite `FREEZE_AMENDMENT.md` for the actual eligibility seed (S + 7) and the meaning of `registry_sha256`. The original freeze files are unchanged.
3. **Recruitment.**
   - Compare the observed ~8 months with the full prespecified accrual uncertainty from the frozen planning report: p10 / p50 / p90 = 9.3 / 37.5 / 151 months. The observed value is at the 8th percentile, inside p5-p95.
   - Also state the central-rate result: 37 months, observed far below it.
   - Also state that the fast fixed-rate scenario was 7.6 / 9.6 / 11.5 months.
4. **Screening.** 78.7% (eligible share of generated candidates) vs 92.5% (dosed among formally screened) is a contextual comparison, not a calibration check. The denominators differ because sites may prescreen before formal screening.
5. **Error rates.** Report the two-sided rejection rate and positive-direction success separately (`amendments/A1_rejection_vs_success.md`).
   - At effect 0: rejection 0.049, success 0.024.
   - Never call 0.022 or 0.024 a type I error.
   - At the design effect both are 0.787.
6. **Synthetic comparator.**
   - **SCA-A (independent P2 evidence):** the headline independent experiment.
     - Internally it fails on magnitude: bias +18.3, coverage 0/100.
     - Against the real trial it overestimates both the comparator (43.9 vs 29.0) and the contrast (30.4 vs 15.1).
     - Its direction and conclusion are right.
   - **SCA-B (same P1 evidence as the simulated truth):** a self-consistency check. Its internal agreement is expected, not validation.
     - Against the real trial its comparator median is close (25.9 vs 29.0).
     - Its contrast (11.9 vs 15.1) is outside the simulated p5-p95 (99th percentile).
   - Publish both. The finding is that a synthetic comparator built from aggregate external evidence gets direction and significance right, while its magnitude is only as good as the match of the external evidence.
