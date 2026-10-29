# First executed study: delegation did not pay for itself

The first ReflexFoundry policy was genuinely trained, but it **must not deploy**. In this controlled validation workload, cold model startup and prediction cost exceeded the possible test savings. A simple file-based heuristic was both faster and more reliable than always delegating to the trained model.

## Evidence and scope

Source: [`benchmarks/run-001/report.json`](../benchmarks/run-001/report.json), read on 26 October 2026, SHA-256 `d6215d2e2a4999d8204923f507e1d85e8c22065774286ac771f0a6f6149022fa`. The report's model digest is `ae0ff4ce5c6844d33a0b7f54b6ee5bf908bb6b11207e8de6b6fe155c6b8d0c74`; its dataset digest is `2328703487e2cd108e690a15f269c58ba5b302b539dede2c199750cfe42b47df`.

The experiment uses generated Python repositories, candidate patches and separate public-contract grader code. An outcome is correct when the chosen validation action correctly accepts or rejects a patch. These numbers concern that stage, not autonomous coding-task success. The code defining the tasks, raw timing records, predictions and report are the reproduction evidence.

The dataset contains 160 training records, 60 external calibration records, 60 promotion records and 80 locked test records. Laya's trainer uses 136 training examples for optimization and a 24-example internal calibration slice, all drawn from the training split. Four frozen-encoder training epochs took about 101.7 seconds in this run. The internal trainer's calibration metrics are in-sample and do not establish held-out quality. External results below are separate.

The base is `convaiinnovations/laya` at revision `7b928d828b7b0e022f929d9bd2e44165aa270148`. Evaluation used native MLX inference. The generated groups share a narrow grammar: there are only six promotion repository groups and eight locked-test groups. That is insufficient diversity for broad deployment claims or a strong independent safety guarantee.

## Locked-test comparison

| Policy | Correct outcomes / 80 | Validation errors | Accounted mean ms per task | Fallback |
| --- | --- | --- | --- | --- |
| Original full suite | 80 | 0 | 97.5 | Not applicable |
| Deterministic heuristic | 80 | 0 | 88.8 | Not applicable |
| Always focused | 49 | 31 | 87.5 | Not applicable |
| Ordinary untuned Laya | 71 | 9 | 2,655.2 | No selective gate |
| Trained always-delegation | 74 | 6 | 4,111.6 | No selective gate |
| Trained selective delegation | 80 | 0 | 4,119.3 | 100% |

Numbers are rounded from the report. The same recorded candidate action outcomes are used for every policy. MLX model loading was measured as 2,241.8 ms for the trained model and 2,347.9 ms for the untuned model. The trained policy also incurs 1,548.7 ms of measured artifact-integrity screening, for 3,790.5 ms of loading plus screening charged on every modeled trained-policy CLI request. The ordinary Laya comparator is an unguarded model baseline, without the trained policy's artifact-screening lifecycle. The implementation starts a model for each CLI `decide` call; the cost model does not assume an unimplemented persistent warm service. The table combines measured loading, integrity screening, prediction and candidate-action times. It excludes interpreter startup, module imports and complete CLI/agent process wall time. The preserved report's “Cold CLI” label names this retrospective model, not a separately timed CLI process.

Training, benchmark collection and independent grading are preparation costs beyond this per-decision table. They make full-lifecycle economics less favorable. Monetary cost is unmeasured; no subscription, token, energy or dollar saving follows from this experiment.

## Why the gate refused

The report records five reasons:

1. Calibration has insufficient safe delegation evidence.
2. Independent promotion accepted-risk bound failed.
3. Promotion has no reliable net time improvement including startup.
4. The simple heuristic dominates the candidate.
5. The locked test does not confirm outcome and time benefit.

No calibration candidate was accepted under the configured cold latency budget. The external threshold became `1.01`, representing no supported delegation. Selective test correctness therefore came entirely from running the original fallback. It is not evidence that learned decisions were perfect.

Reversing the candidate order changed the trained model's answer on 28.75% of locked-test inputs. The report records six incorrect always-delegate decisions. It also records 74 unnecessary fallbacks, defined as cases where the ungated model's proposal happened to lead to a correct validation outcome. That diagnostic does not override the failed cost, stability and evidence gates.

The paired repository-group bootstrap interval for original-minus-selective accounted time was approximately **[-4,042.2, -4,001.3] ms per task**. Negative values mean the selective workflow cost more time. The task-success difference interval was [0, 0] because all selective requests used the original fallback. These are descriptive intervals for this limited workload, not guarantees under distribution shift.

## What this supports

The experiment establishes that the pipeline can train and evaluate a local Laya policy and refuse one that does not improve the declared workflow. It demonstrates why inference, startup, a strong heuristic and independent outcomes all belong in the comparison.

It does not show that local decision models are universally uneconomic, that a warm persistent implementation would win, or that a different workload would benefit. Those are new hypotheses requiring new evidence. Longer genuinely expensive repeated decisions, realistic unseen repositories, richer task diversity and a separately implemented persistent runtime are possible future experiments, not current capabilities or promised gains.

## Reproduce the published fixture sizes

The full CLI benchmark defaults to the published 160/60/60/80 split sizes. For explicit control over those same sizes, the equivalent public Python benchmark function is:

```bash
python - <<'PY'
from pathlib import Path
from reflexfoundry.benchmark import generate
generate(
    Path("runs/published-study"),
    {"train": 160, "calibration": 60, "promotion": 60, "test": 80},
    repeats=3,
)
PY

reflex train --workspace runs/published-study \
  --base models/base --output models/published-study-v1 --epochs 4
reflex evaluate --workspace runs/published-study \
  --policy models/published-study-v1 --base models/base --backend mlx
```

Install the training and Apple extras and download the pinned base as described in the [quickstart](quickstart.md) first. Choose fresh output directories. Replace MLX with `--backend torch` on other platforms; that changes the runtime conditions and cannot reproduce the Apple timing values. Host load, device and upstream runtime behavior affect timings; preserving the protocol does not promise bit-identical measurements.
