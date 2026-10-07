# Synthetic comparator experiment: NCT06604442 (base v4.1.0)

Index exposure visible; comparator exposure masked and replaced by a synthetic comparator from a frozen model of allowed inputs only; then the held-out comparator is revealed. This is INTERNAL simulation validation: the truth is itself simulated from pre-result evidence, so agreement here is not proof that a synthetic comparator can replace a real one.

## SCA-A: primary: comparator from an independent allowed source

Truth: `literature` source. Comparator model: lognormal from P2 (pre-start, independent) (median 45.1, sigma 0.936); no access to the masked values.

| Quantity | Value |
| --- | --- |
| comparator median, true (p10 / p50 / p90 over trials) | 23.4 / 26.1 / 28.9 |
| comparator median, synthetic | 36.4 / 43.9 / 53.8 |
| paired contrast, true | 9.7 / 11.9 / 14.6 |
| paired contrast, synthetic comparator | 28.1 / 30.4 / 32.3 |
| mean signed bias | +18.31 |
| median absolute error | 18.19 |
| RMSE | 18.46 |
| 95% interval covers the true contrast | 0/100 |
| same inferential conclusion | 100/100 |

## SCA-B: self-consistency bound (same evidence; within-patient link unknown)

Truth: `literature` source. Comparator model: lognormal from P1 (same evidence as the truth) (median 25.7, sigma 0.536); no access to the masked values.

| Quantity | Value |
| --- | --- |
| comparator median, true (p10 / p50 / p90 over trials) | 23.4 / 26.1 / 28.9 |
| comparator median, synthetic | 22.8 / 25.9 / 29.2 |
| paired contrast, true | 9.7 / 11.9 / 14.6 |
| paired contrast, synthetic comparator | 10.3 / 11.9 / 13.5 |
| mean signed bias | -0.03 |
| median absolute error | 1.29 |
| RMSE | 2.16 |
| 95% interval covers the true contrast | 93/100 |
| same inferential conclusion | 100/100 |

## SCA-R: reverse check: truth from P2, comparator from P1

Truth: `prestart` source. Comparator model: lognormal from P1 (pre-results, independent of P2) (median 25.7, sigma 0.536); no access to the masked values.

| Quantity | Value |
| --- | --- |
| comparator median, true (p10 / p50 / p90 over trials) | 38.2 / 46.2 / 55.2 |
| comparator median, synthetic | 22.7 / 26.1 / 28.7 |
| paired contrast, true | 23.1 / 32.2 / 40.2 |
| paired contrast, synthetic comparator | 10.3 / 11.9 / 13.4 |
| mean signed bias | -20.07 |
| median absolute error | 19.69 |
| RMSE | 21.44 |
| 95% interval covers the true contrast | 0/100 |
| same inferential conclusion | 99/100 |

