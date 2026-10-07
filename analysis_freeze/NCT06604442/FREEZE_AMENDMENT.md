# Freeze amendment A1 (written 2026-10-07, AFTER the reveal)

This amendment was written after the observed results of NCT06604442 had been read (step 12).
- It does not replace or edit the original freeze files. They are left exactly as they were, with their checksums, in `pre_observed_comparison/` and `step1_baseline/`.
- It corrects their metadata and records the post-reveal analysis changes, so a reader sees both the original record and its corrections.

## 1. Metadata corrections (no computation changed)

**Eligibility seed.** The frozen `freeze_manifest.json` (`seed_scheme`) says eligibility used an "internal fixed seed 20261005". That describes the archived first set, not the final replicates.
- The final 100 replicates (`replicates/`) used a replicate-specific eligibility seed: base + 7, passed by `build-eligibility --seed`.
- The seed scheme actually used, for replicate r with base seed S = 20270000 + 97 r:

| Stage | Seed |
| --- | --- |
| population | S + 0 |
| cohorts | S + 1 |
| safety | S + 2 |
| outputs | S + 3 |
| journey | S + 4 |
| endpoints | S + 5 |
| analysis | S + 6 |
| eligibility | S + 7 |
| screening order | S + 11 |
| paired measurements | S + 13 |
| accrual stress | S + 21 |
| completeness stress | S + 31 |
| synthetic comparator (experiment k) | S + 41 + k |

**Field name.** `protocol.registry_sha256` in the frozen manifest holds the PDF checksum recorded in `data/manifest/protocols.json`, not anything from the registry.
- Read it as "protocols-manifest sha256".
- It equals the PDF's own checksum, as the manifest shows.
- `scripts/freeze_manifest.py` now names it `protocols_manifest_sha256` and records the actual seed scheme for future freezes.

**Wording of "before any observed result".** The frozen files say outputs were fixed "before any observed result of the trial is used/read". The accurate statement is narrower:
- outputs were fixed before any observed result was used as a computational input;
- observed information had been seen before the freeze. See `step1_baseline/disclosures.md`: registry study dates, publication identifiers in search results, and the published aggregates contained in the analysis plan.

## 2. Characterisation of the validation

This is a **retrospective held-out comparison using frozen computational inputs**. It is not blinded and not prospective external validation.
- The firewall shows that no observed outcome entered any generation, recruitment, endpoint or comparator model.
- It does not show that the analysts were unaware of the observed results.

## 3. Post-reveal analysis changes (computed from frozen inputs only; no simulation rerun)

| # | Change | Where |
| --- | --- | --- |
| A1 | The effect-size curve reports **two-sided rejection** (type I error 0.049 at effect 0) separately from **positive-direction success** (0.024 at effect 0). The frozen step-5 curve reported only the latter, so its 0.022 at effect 0 is not a type I error. | `amendments/A1_rejection_vs_success.md` |
| A2 | Recruitment is compared against the **full prespecified accrual uncertainty**: the frozen planning report's enrolment-duration distribution, combining rate uncertainty with Poisson arrivals, frozen before the reveal. The central-rate replicate distribution is kept as a secondary row. Observed ~8 months is at the 8th percentile (inside p5-p95). | `post_reveal/observed_comparison.md`, `tables/`, figures 3 and 6 |
| A3 | The screen-pass comparison (simulated 78.7% vs observed 92.5%) is reported as **contextual only**: the denominators differ (generated candidates vs formally screened patients after any site prescreening). | same |
| A4 | Synthetic comparators are labelled by independence. **SCA-A** is the independent evidence source (P2); it fails on magnitude. **SCA-B** is a self-consistency check, using the same P1 evidence as the simulated truth; its internal agreement is expected and is not validation. Against the real trial, the P1-based comparator median is close (25.9 vs 29.0), but its contrast (11.9 vs 15.1) is outside p5-p95. | same |
