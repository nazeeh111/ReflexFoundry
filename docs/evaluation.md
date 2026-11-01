# Evaluation and claims

The question is whether delegating a bounded decision improves the complete declared workflow, after paying for the delegation. Agreement with a teacher or fast warm inference alone cannot answer that question.

## What the fixture experiment measures

The benchmark generates small Python packages with public arithmetic, presentation and consumer contracts. It applies candidate patches, including both correct changes and regressions. Focused checks exercise the changed behavior; full checks also exercise consumers. Separate grader code checks the declared public contracts without importing the candidate test files.

An action's success means that its validation result correctly accepts or rejects the patch according to that grader. A failing test can be a successful validation decision when it correctly rejects a regression. A passing test can be an unsuccessful decision when it accepts a broken patch.

Both actions are executed. Per-action timing trials alternate their execution order and retain raw durations. Reported action duration aggregates those actual trials. There are no artificial sleeps or simulated latency labels.

This is a controlled validation-stage experiment. Candidate patches are supplied by the fixture generator. It is not a measurement of an agent discovering a bug, writing a patch, using private deliberation, or completing an arbitrary real repository issue. The grader is independently implemented code within this project, not an outside evaluator or a proof that every possible contract is covered.

## Data separation

Training, calibration, promotion and locked test examples have separate groups. Training data alone reaches the upstream trainer. Calibration chooses an abstention threshold; promotion checks the fixed candidate. The locked test can veto deployment and must not be used to retune thresholds or select a new model while retaining a held-out claim.

Repository and task-group identity matter. Multiple patch variants from one source, and repeated timings of the same patch, are not independent correctness samples. Group separation and input deduplication reduce leakage; the shared fixture grammar still limits generalization. A numeric suffix that makes text unique does not make the underlying problem independently diverse.

## Baselines

| Policy | Why include it |
| --- | --- |
| Original full suite | The existing bounded workflow with no delegation cost. |
| Deterministic heuristic | A transparent file-based rule that may capture most of the opportunity. |
| Always focused | Shows the cost and correctness consequences of always taking the shortcut. |
| Ordinary Laya | Untuned checkpoint, when supplied through `evaluate --base`. |
| Trained always-delegation | Separates adaptation from the selective gate. |
| Trained selective delegation | Includes uncertainty, option-order stability, budget checks and fallback. |

All policy comparisons use the same recorded action outcomes and declared task criterion. Baseline overheads must match what is actually executed. Hosted Jev is not required, and no hosted comparison is claimed unless separately authorized and actually run.

## Costs and uncertainty

The retrospective stage comparison combines recorded candidate-action outcomes with measured artifact-integrity screening, model loading, both option-order prediction passes, and the selected action or fallback. The measured loading and screening are charged on each modeled request. Interpreter startup and imports outside the model-loading timer are excluded; any library imports inside that timer are included. Complete CLI/agent process wall time is not measured. The table is a sum of measured components, not direct timing of complete cold CLI or live-agent runs. Historical reports retain the original “Cold CLI” execution-contract label; interpret that label using this narrower measurement boundary. Warm inference is a separate diagnostic. Benchmark collection, independent grading and training are preparation costs; they must be reported separately and included in any later full-lifecycle break-even claim.

Reports retain task correctness, false acceptance information where available, fallback, accepted errors, option-order flips, paired timing differences, and uncertainty. Repository-group bootstrap intervals describe measured paired differences. With
fewer than two actual repositories, paired intervals are unavailable and the
promotion gate fails closed. Wilson error bounds have sampling assumptions; repeated or correlated fixtures do not automatically satisfy those assumptions. No interval establishes validity for unseen production workloads.

There is no measured hosted model expenditure in the free local experiment. Wall time is not automatically a dollar, token, compute-energy, or subscription saving. Model calls made during optional integrations must be measured separately before claiming those benefits.

## Promotion and negative results

The gate checks sufficient accepted evidence, task-quality nonregression, a supported net time benefit, comparison against the deterministic heuristic, and the locked test. Shadow mode adds another requirement: successful independent checks of the eligible learned proposal, not successful runs of the original fallback. Explicit opt-in and bounded deployment remain necessary even when evaluation passes.

A strong heuristic may dominate the learned model. Cold startup may cost more than any available test reduction. Confidence may be high on wrong decisions, candidate order may change the answer, and a conservative threshold may abstain on every example. These are results to preserve. A rejected candidate must not deploy merely because it produces predictions quickly on a warm GPU.

## Reproduction and extensions

Use a fresh output directory and retain source version, package versions, hardware, manifest, raw records, predictions, evaluation report and training configuration. Run the [quickstart](quickstart.md) to reproduce the pipeline. Absolute timings will vary across hardware and host load.

Stronger claims need additional evidence: held-out real repositories with meaningful task diversity, naturally occurring coding tasks, repeated independent trials, verifier quality assessment, and clearly accounted collection/training/fallback costs. A live Codex trial should measure task success and latency through documented observable actions, preserving native permissions. The [context retrieval study](context-benchmark.md) provides a separate executable
source-coverage criterion. It has one actual repository per split, so its results
do not support broad delegation or autonomous task-completion claims.

Fresh training versions finalize the pinned runtime's tokenizer-class and special-token metadata before computing the training artifact digest. The manifest records that operation and preserves the upstream configuration. Loading an existing legacy model still cannot silently revise its identity; use an explicit converted version and evaluate it again.
