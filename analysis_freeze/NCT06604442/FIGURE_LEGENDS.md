# Figure legends (for the manuscript; the figures themselves carry no captions)

**Figure 1. From protocol to an executable, patient-level virtual trial.**
- **(A)** Protocol elements extracted into executable form: eligibility (13 criteria), the evaluable target (52), two paired PSMA PET scans 1-10 days apart, and the primary endpoint (paired difference in urinary bladder SUVmean).
- **(B)** The patient-level virtual trial. A candidate population is screened against the criteria; enrolled participants receive both exposures; each participant carries a longitudinal record. The inset shows one participant's screening, scans and reporting window.
- **(C)** The scientific questions addressed in Figures 2-5.

**Figure 2. Eligibility pressure and screening burden (100 virtual trials).**
- **(A)** Left: population characterisation, the eligible share of the 10,000 generated candidates. Right: operational burden, the number screened in random order until 52 eligible participants are found, the enrolled and the analysable pairs. These are two separate calculations, not one funnel. Median with the 10th-90th percentile.
- **(B, C)** Counterfactual feasibility: the change in eligible share (B) and in patients screened to reach 52 (C) when each of the three criteria excluding the most candidates is removed in turn. Median and 10th-90th percentile over 50 virtual trials.
- Criteria the generated candidates cannot carry were resolved by calibration to registry screen-pass rates. Their exclusion rates are therefore calibrated, not criterion-specific evidence, and removing a criterion is not a recommendation.

**Figure 3. Recruitment: predictive distribution and the observed trial.**
- **(A)** Prespecified predictive distribution of the time to enrol 52 participants. It combines the uncertainty of the historical accrual rate (similar completed prostate cancer trials; 10 centres as stated in the protocol) with Poisson arrivals. Squares mark the model's probabilities of completion by 12, 24, 36 and 60 months.
- **(B)** Median and 10th-90th percentile for the prespecified distribution and for fixed accrual rates at the model's 10th, 50th and 90th percentiles.
- The star and dashed line mark NCT06604442 (about 8 months, October 2024 to June 2025, 9 sites). It falls at the 8th percentile of the prespecified distribution.

**Figure 4. Operating characteristics of the primary analysis.**
- **What is shown:** probability that the two-sided paired Wilcoxon signed-rank test (alpha 0.05) is significant with the comparator higher, by true mean paired difference and analysable sample size. The SD of paired differences is 25.2, as implied by the protocol's power statement; 4,000 simulated trials per grid point.
- **Markers:** the diamond marks the protocol design (N = 52, mean difference 10; success probability 0.787). The dotted line marks N = 52, which is a grid point.
- **No observed value is plotted:** the surface is indexed by the true mean paired difference, while the completed trial reports a median paired difference (15.1).
- **Type I error:** at a true difference of 0 the two-sided rejection rate is 0.049 (Supplementary Figure S2).

**Figure 5. Can external evidence reconstruct a masked comparator?**
- **(A)** Design of the experiment inside each of 100 virtual trials:
  - the index scan (flotufolastat) is observed;
  - the comparator (piflufolastat) is masked;
  - a synthetic comparator is generated from published evidence only;
  - the paired difference is compared with the held-out comparator.
- **(B)** Held-out true versus synthetic-comparator paired difference, one point per virtual trial. The dashed line is identity.
- **(C)** Error in the paired difference (mean; 10th-90th percentile), with mean absolute error, root mean squared error and 95% interval coverage.
- **The three comparator models:**
  - *Independent (P2):* comparator from a published cohort independent of the simulated truth (SUVmax-based, converted to SUVmean).
  - *Self-consistency (P1):* comparator from the same evidence that generated the simulated truth. Agreement is expected by construction and is not independent validation.
  - *Reverse independent:* P1 comparator against a P2-generated truth.
- Results were unchanged for within-patient correlations of 0.3-0.7 (Supplementary Figure S4).

**Figure 6. Benchmark against the completed NCT06604442 (native units).**
- **Common elements:** distributions are from the simulation, built from prespecified, outcome-independent computational inputs. The open circle and bar are the median and 10th-90th percentile; stars are the published NCT06604442 values.
- **(A)** Months to enrol 52 participants, prespecified predictive distribution. The observed value is at the 8th percentile.
- **(B)** Median paired difference in bladder SUVmean across 100 virtual trials:
  - with per-scan levels from pre-result literature;
  - under the protocol's design assumption.
  - Observed 15.1.
- **(C)** Synthetic comparator from the P1 and P2 evidence:
  - upper panel: its level, as median piflufolastat bladder SUVmean per virtual trial (P1 25.9; P2 43.9; observed 29.0);
  - lower panel: the paired difference it produces against flotufolastat (P1 11.9; P2 30.4; observed 15.1).
- **(D)** Participants without an analysable pair across virtual trials. Observed 11.3% (7 of 62 dosed).
- This is a retrospective comparison using prespecified, outcome-independent computational inputs.

**Supplementary Figure S1. One synthetic participant's longitudinal record.**
- Screening, piflufolastat scan (day 1), flotufolastat scan (day 10) and the end of the 30-day reporting window, with the simulated bladder SUVmean of each scan.
- Participant S0001 of virtual trial 1, age 56. The two exposure records (S0001-P1, S0001-P2) belong to one person; paired difference 5.4.

**Supplementary Figure S2. Effect-size curve at N = 52.**
- Two-sided rejection rate and positive-direction success (significant with the comparator higher) from the same simulated trials; 10,000 trials per point, 95% Monte Carlo intervals.
- Dotted lines mark 0.05 and 0.80.

**Supplementary Figure S3. Exclusion by criterion across 100 virtual trials.**
- Share of generated candidates excluded by each eligibility criterion.
- Except age (EL001), the criteria are resolved by calibration to registry screen-pass rates, so their similar exclusion rates reflect calibration rather than criterion-specific evidence.

**Supplementary Figure S4. Synthetic comparator and the within-patient correlation.**
- Bias (A) and 95% interval coverage (B) of the paired difference for the independent (P2) and self-consistency (P1) comparators.
- The held-out truth was generated with within-patient log-scale correlations of 0.3, 0.5 and 0.7.
