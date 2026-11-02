# ReflexFoundry amended native comparison

**AMENDED PARTIAL COMPARISON: 20 RESULTS, 19 VALID**

20/20 actual results; 19 protocol-valid; 19 independently successful repairs; 11 valid model-inference observations; 15/16 valid pairs.

Trials 19 and 20 are a reviewed continuation after the phase-A halt and a publication/time gap, not an uninterrupted preregistered study. Trial 18 remains an invalid timeout of unknown cause, without retry or imputed usage. All combined estimates are post-amendment and descriptive. Compare each arm with its matching original-agent cohorts, not unequal-cohort arm means.

## Matched-cohort comparisons

Each candidate is compared only with the original-agent observations for the same task and repeat. The ordinary-Laya arm has three usable pairs; the other arms have four. Do not compare unequal-cohort arm means as an effect estimate. Negative deltas are smaller observed values, not causal savings. Cached tokens are already included within input.

| Arm | Matched pairs | Original CLI s | Candidate CLI s | CLI delta s | Original pipeline s | Candidate pipeline s | Pipeline delta s | Input delta | Cached subset delta | Output delta |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| deterministic-heuristic | 4/4 | 39.43 | 39.37 | -0.06 | 51.76 | 48.60 | -3.16 | +8,234 | -4,544 | +60.5 |
| ordinary-laya | 3/4 | 39.45 | 75.13 | +35.68 | 49.27 | 85.49 | +36.22 | +147,014.66666666666 | +143,872 | +374.6666666666667 |
| trained-always | 4/4 | 39.43 | 71.41 | +31.98 | 51.76 | 78.23 | +26.47 | +162,310.75 | +144,384 | +363.25 |
| selective-shadow | 4/4 | 39.43 | 87.26 | +47.83 | 51.76 | 99.01 | +47.25 | +195,815.5 | +182,112 | +419.5 |

## Amendment identity and historical source scope

Original phase: observations1–18, verified against all 135 registered file hashes. Only the two registered absent preflight files may be resolved from the fixed continuation supplement. The four named publication-only extras remain outside that historical manifest and are disclosed by hash in JSON.

Continuation phase: `reviewed-continuation-01`, indices19/20. Amendment SHA-256 `2851023e7a647d9d32d65966c10063f60573c8d1d80477f2b07c309fd7a7dcfd`; review SHA-256 `6663ad88ac0920ccfe49ca02bef789e7418a1349476bd36094a90021f238b59b`; driver SHA-256 `795acd32764313fb7d4afde9114c9c9e45211bc5b6d36d75f581ad9d7c185d9f`.

Historical continuation observer checkout: `10f342d0d52b26f99a54948324c96d3efa2a8a80`. This is the source closure recorded and independently reviewed at amendment time, not a requirement that today's installed code equal that historical snapshot. The driver is hashed as evidence and is never executed by this analyzer.

Historical phase-A eighteen-attempt summary only; not a lagging combined-study summary.

## Descriptive arm summaries (unequal cohorts; not an effect estimate)

These absolute means retain each arm's available cohort and must not be ranked as an improvement comparison. Only protocol-valid observations contribute. Success denominators show valid observations, with planned counts separately visible.

| Arm | Completed / planned | Valid | Independent successes / valid | CLI mean s | Pipeline mean s | Input mean | Cached subset mean | Output mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| original-agent | 4/4 | 4 | 4/4 | 39.43 | 51.76 | 175,897.75 | 158,496 | 577.25 |
| deterministic-heuristic | 4/4 | 4 | 4/4 | 39.37 | 48.60 | 184,131.75 | 153,952 | 637.75 |
| ordinary-laya | 4/4 | 3 | 3/3 | 75.13 | 85.49 | 334,020.6666666667 | 313,088 | 943.6666666666666 |
| trained-always | 4/4 | 4 | 4/4 | 71.41 | 78.23 | 338,208.5 | 302,880 | 940.5 |
| selective-shadow | 4/4 | 4 | 4/4 | 87.26 | 99.01 | 371,713.25 | 340,608 | 996.75 |

## Every planned observation

Missing results are missing, even if a start was reserved. A started record alone is not proof of a live process. On protocol failure, raw metrics remain visible here and are excluded from comparison estimates.

| Index | Repository task | Repeat | Arm | Status | Independent success | CLI s | Pipeline s | Input | Cached subset | Output |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | funcy-first | 1 | original-agent | protocol-valid | True | 43.12 | 49.64 | 175,934 | 158,336 | 503 |
| 2 | funcy-first | 1 | deterministic-heuristic | protocol-valid | True | 44.48 | 47.35 | 208,718 | 172,416 | 645 |
| 3 | funcy-first | 1 | ordinary-laya | protocol-valid | True | 71.49 | 81.10 | 343,389 | 320,128 | 908 |
| 4 | funcy-first | 1 | trained-always | protocol-valid | True | 74.22 | 76.91 | 338,195 | 299,776 | 1,096 |
| 5 | funcy-first | 1 | selective-shadow | protocol-valid | True | 65.11 | 73.49 | 345,983 | 323,456 | 950 |
| 6 | cachetools-getitem | 1 | selective-shadow | protocol-valid | True | 80.79 | 92.03 | 323,147 | 302,336 | 789 |
| 7 | cachetools-getitem | 1 | trained-always | protocol-valid | True | 46.69 | 48.36 | 237,333 | 200,832 | 639 |
| 8 | cachetools-getitem | 1 | ordinary-laya | protocol-valid | True | 48.41 | 51.67 | 231,660 | 213,632 | 649 |
| 9 | cachetools-getitem | 1 | deterministic-heuristic | protocol-valid | True | 25.63 | 30.49 | 112,537 | 96,128 | 509 |
| 10 | cachetools-getitem | 1 | original-agent | protocol-valid | True | 31.50 | 42.55 | 148,108 | 130,304 | 578 |
| 11 | funcy-first | 2 | selective-shadow | protocol-valid | True | 135.02 | 157.62 | 517,475 | 476,800 | 1,281 |
| 12 | funcy-first | 2 | trained-always | protocol-valid | True | 103.53 | 121.61 | 418,671 | 379,392 | 1,133 |
| 13 | funcy-first | 2 | ordinary-laya | protocol-valid | True | 105.50 | 123.70 | 427,013 | 405,504 | 1,274 |
| 14 | funcy-first | 2 | deterministic-heuristic | protocol-valid | True | 49.42 | 70.17 | 244,182 | 208,896 | 853 |
| 15 | funcy-first | 2 | original-agent | protocol-valid | True | 43.75 | 55.62 | 236,976 | 219,008 | 626 |
| 16 | cachetools-getitem | 2 | original-agent | protocol-valid | True | 39.35 | 59.22 | 142,573 | 126,336 | 602 |
| 17 | cachetools-getitem | 2 | deterministic-heuristic | protocol-valid | True | 37.94 | 46.41 | 171,090 | 138,368 | 544 |
| 18 | cachetools-getitem | 2 | ordinary-laya | protocol-failed | False | 181.32 | 209.33 | unavailable | unavailable | unavailable |
| 19 | cachetools-getitem | 2 | trained-always | protocol-valid | True | 61.19 | 66.05 | 358,635 | 331,520 | 894 |
| 20 | cachetools-getitem | 2 | selective-shadow | protocol-valid | True | 68.12 | 72.89 | 300,248 | 259,840 | 967 |

## Every planned pair

All deltas are candidate minus the original-agent observation for the same repository task and repeat. The same original observation is shared by four arm comparisons. A negative time or token delta is a smaller observed value, without causal interpretation.

| Repository task | Repeat | Arm | Original / candidate indices | Pair status | Success delta | CLI delta s | Pipeline delta s | Input delta | Cached subset delta | Output delta |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| funcy-first | 1 | deterministic-heuristic | 1 / 2 | valid | +0 | +1.36 | -2.29 | +32,784 | +14,080 | +142 |
| funcy-first | 1 | ordinary-laya | 1 / 3 | valid | +0 | +28.37 | +31.46 | +167,455 | +161,792 | +405 |
| funcy-first | 1 | trained-always | 1 / 4 | valid | +0 | +31.10 | +27.27 | +162,261 | +141,440 | +593 |
| funcy-first | 1 | selective-shadow | 1 / 5 | valid | +0 | +21.99 | +23.85 | +170,049 | +165,120 | +447 |
| funcy-first | 2 | deterministic-heuristic | 15 / 14 | valid | +0 | +5.68 | +14.55 | +7,206 | -10,112 | +227 |
| funcy-first | 2 | ordinary-laya | 15 / 13 | valid | +0 | +61.75 | +68.08 | +190,037 | +186,496 | +648 |
| funcy-first | 2 | trained-always | 15 / 12 | valid | +0 | +59.79 | +65.99 | +181,695 | +160,384 | +507 |
| funcy-first | 2 | selective-shadow | 15 / 11 | valid | +0 | +91.27 | +102.00 | +280,499 | +257,792 | +655 |
| cachetools-getitem | 1 | deterministic-heuristic | 10 / 9 | valid | +0 | -5.87 | -12.06 | -35,571 | -34,176 | -69 |
| cachetools-getitem | 1 | ordinary-laya | 10 / 8 | valid | +0 | +16.91 | +9.12 | +83,552 | +83,328 | +71 |
| cachetools-getitem | 1 | trained-always | 10 / 7 | valid | +0 | +15.19 | +5.80 | +89,225 | +70,528 | +61 |
| cachetools-getitem | 1 | selective-shadow | 10 / 6 | valid | +0 | +49.29 | +49.48 | +175,039 | +172,032 | +211 |
| cachetools-getitem | 2 | deterministic-heuristic | 16 / 17 | valid | +0 | -1.41 | -12.82 | +28,517 | +12,032 | -58 |
| cachetools-getitem | 2 | ordinary-laya | 16 / 18 | candidate:protocol-failed | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| cachetools-getitem | 2 | trained-always | 16 / 19 | valid | +0 | +21.84 | +6.83 | +216,062 | +205,184 | +292 |
| cachetools-getitem | 2 | selective-shadow | 16 / 20 | valid | +0 | +28.77 | +13.67 | +157,675 | +133,504 | +365 |

## Interpretation and boundaries

- Two actual repositories, one supplied repair mutation per repository and two correlated repetitions. Repeated arm comparisons share original-agent baselines; they are not independent task samples.
- Descriptive observations only. No significance test, causal superiority, population reliability, monetary saving, energy saving or subscription-allowance estimate is established.
- Input tokens already include cached input tokens. Cached tokens are shown as a subset and are never added to input tokens. Reported counters are not monetary cost.
- Agent-side mandatory validation was requested and may be described in the final answer. Exact internal check execution and ordering were not retained or enforced by the observer. The separate post-run focused/full/contract results are directly observed.
- CLI wall time includes the native process and observer collection. Pipeline wall time additionally includes the three independent checks. Readiness hashing and subsequent postcondition audit are separate, with all-in attempt time also retained. Host load and operating-system/service caches are uncontrolled.
- Protocol-failed and missing observations remain explicit. They provide no paired estimate. Raw measurements on a failed-protocol observation may be displayed but are excluded from arm summaries and paired deltas.
- The trained policy remains withheld. Always-delegate is a controlled read-only experimental comparator, not production deployment. Selective shadow retains the failed policy's fallback.
- Trials 19 and 20 are a reviewed continuation after the phase-A halt and a publication/time gap, not an uninterrupted preregistered study. Trial 18 remains an invalid timeout of unknown cause, without retry or imputed usage. All combined estimates are post-amendment and descriptive. Compare each arm with its matching original-agent cohorts, not unequal-cohort arm means.

## Source identity

Observer checkout: `84e55fbd75ab98dde07a9c94ca02ffa1d98245c2`. Preparation checkout: `1ddf3e4f3f2281bb5cbb6b72655774390eecd242`.

The plan freezes four observer files and the full per-case runtime. Imported observer dependencies are recorded separately in native-v2-execution-provenance.json; that record is not retroactive preregistration. This JSON report includes the exact SHA-256 of every read input.

Trials1–18 come only from the immutable original phase. Trials19/20 come only from the separately reviewed continuation. The original eighteen-attempt summary remains historical phase-A evidence, not an accumulating or lagging combined summary. Trial18 remains invalid with unavailable usage. No fully protocol-valid or uninterrupted study is claimed.
