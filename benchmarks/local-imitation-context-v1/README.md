# Local-teacher imitation versus outcome-label training

Executed 29 October 2026 against source snapshot `1ddf3e4f3f2281bb5cbb6b72655774390eecd242`. This is a controlled source-retrieval-stage ablation using the previously published scoped context records. It does not execute Codex or establish full-agent benefit.

## Result

Outcome labels did not improve held-out retrieval success over this local teacher imitation fit. Both heads made **the same 30 test choices**, with 20 independently correct retrieval outcomes and 10 failures on the same cases. Both guarded policies fell back on all 30 test cases and failed promotion. This is a negative single-seed finding, not evidence of equivalence in the broader population.

| Partition | Actual source repository | Outcome head correct | Imitation head correct | Different raw choices |
| --- | --- | ---: | ---: | ---: |
| External calibration | Funcy | 23/30 | 23/30 | 0 |
| Promotion | Blinker | 16/30 | 16/30 | 2 |
| Locked, reused test | cachetools | 20/30 | 20/30 | 0 |

There is only one actual repository in each partition. Query variants share six target groups. No repository-level interval or generalization claim is supported. The cachetools test evidence was already public and used in the prior context study; it is held out from these two fits but is **not a new blind validation sample**.

## What was held constant

Both arms use the same 36 eligible Toolz training inputs, base weights, native Laya trainer, four frozen-encoder epochs, seed 17, option shuffling, soft cross-entropy and identical 31-optimization/5-internal-calibration split. There is one fit per arm and no best-of selection or retuning after test. Actual frozen-backbone verification found all 170 encoder tensors (789,563,392 bytes) identical to the base and to each other. Head hashes differ.

The original training partition has 42 examples; six have no independently successful candidate action. Those six are excluded from BOTH arms, once, before obtaining any teacher label. Consequently this is a label-source comparison conditioned on outcome-based eligibility. It cannot establish the economics of a completely outcome-free data acquisition workflow.

Outcome targets choose the fastest independently successful action from recorded retrieval trials, preserving the product's conservative near-tie rule. On this fixed corpus that rule changes no strict-fastest label. The teacher is the untuned **local Laya** model, queried only on the same 36 training inputs. The canonical first-order teacher choice supplies each imitation target; reversed-order predictions are retained only as a diagnostic. All five order-unstable teacher targets remain in the cohort. The teacher is not Codex, and original-agent distillation remains untested.

Outcome and teacher targets differ on 8/36 examples: outcome counts are 18 symbol/18 search; teacher counts are 26 symbol/10 search. The canonical teacher choices yielded independently successful training retrieval outcomes on 34/36 examples. Both training datasets have their outcomes removed after label construction, so native training cannot silently overwrite the imitation targets with the outcome labels. Calibration, promotion and test rows remain byte-equivalent between arms.

## Measured costs and boundaries

The teacher-label generation phase took 13,435.0 ms. The outcome fit took 106,264.3 ms; imitation fit took 82,186.8 ms. These are observations under uncontrolled concurrent host load, not a causal estimate of training-cost differences.

For each arm, artifact screening plus model construction was measured in three fresh Python subprocesses, with alternating arm order; the median accounted load was 8,697.7 ms for outcome and 7,380.1 ms for imitation. Held-out per-row predictions alternate model order. All timing and both option-order passes are retained. The two trained heads had test order-flip rates of 5/30 each.

The test selective-accounted means were 9,085.9 ms for outcome and 7,747.4 ms for imitation, versus 52.8 ms for original search. These numbers sum previously executed retrieval action time, measured local screening/load, and per-row inference. They are **retrospective stage accounting**, not directly measured CLI or agent process time. Interpreter startup, module imports outside the load timers, complete CLI bookkeeping and full agent work are absent. OS caches and competing CPU work remain uncontrolled. A lower model mean here is not evidence that its label source causes speed improvements. Preparation, grading and training costs are additional; no monetary, token, energy or compute-saving conversion is made.

No calibration threshold met the configured latency/evidence conditions. Both thresholds are 1.01 (unsupported delegation); both reports reject promotion on seven recorded grounds. No product policy was registered or deployed.

## Evidence and reproduction

- `plan.json`: frozen base/source/training contract and exact cohort IDs written before teacher calls or fitting.
- `teacher-training-predictions.json`, `labels.json`: canonical targets, probabilities/order diagnostics and target differences; no held-out teacher queries.
- `records-{outcome,imitation}.jsonl`, `model-*-train.jsonl`: matched examples and native JSONL targets.
- `training-*.json`, `execution.txt`: actual configurations, loss history, fit times and upstream internal-calibration warnings. Internal calibration uses only five items and is not independent quality evidence.
- `startup-probes.json`, `heldout-predictions.json`, `evaluation-*.json`, `comparison.json`, `summary.json`: measured costs, fixed predictions and actual outcome comparison.
- `frozen-encoder-verification.json`: complete frozen-backbone tensor identity.
- [Release model assets](https://github.com/nazeeh111/ReflexFoundry/releases/tag/v0.2.2): the two ablation heads include tokenizer/encoder metadata, manifests and licenses. Base weights are reacquirable from the immutable model revision; full weights are not stored in Git.
- [`scripts/imitation_ablation.py`](../../scripts/imitation_ablation.py) and the two ablation test modules contain the reproduction runner and seven fairness/leakage checks. `raw/` preserves exact executed runner and original report bytes. The metadata-only correction in `reporting-correction.json` fixes inherited wording that overstated CLI coverage; no measurements or choices changed.
- `SHA256SUMS.json`: payload checksums.

The exact original runner is retained under `raw/`. To reproduce its source environment, use a separate checkout of `1ddf3e4`, point `PYTHONPATH` to that checkout's `src`, and run the retained raw runner by its absolute path. The forward reproduction command below uses the current source and its installed free training/Apple extras, a local pinned base checkpoint, and a fresh output path:

```sh
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=src python scripts/imitation_ablation.py run \
  --records benchmarks/context-v1/scoped-v1/records.jsonl \
  --base PATH_TO_LOCAL_BASE --output FRESH_STUDY_DIRECTORY
```

No network access is needed after dependencies and the public base are installed. New fits and timing values can vary by runtime/hardware; this protocol does not promise bit-identical MPS optimization. No native Codex coding process, separately billed API, credential inspection, model/effort override or permission bypass occurred in this study.

The current source finalizes newly trained tokenizer exports before freezing their artifact identity. The original ablation artifacts retain the old native export metadata and their original hashes; they have not been silently converted. [Portable export verification](portable-export-verification.json) reconstructs both original heads exactly and checks an explicit derived copy on actual CPU and MLX loaders. This check changes no training result or policy eligibility.
