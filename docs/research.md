# Research basis and evaluation contract

Research checked on 26 October 2026. Repository documentation is evidence of an
upstream capability or claim, not a local reproduction. Experiment artifacts in
this project establish what ReflexFoundry actually ran. This review identifies a
useful implementation scope; it does not establish scientific priority.

## What already exists

| Foundation | Observed capability and implication |
| --- | --- |
| [Laya](https://github.com/NandhaKishorM/laya) | Open typed decisions using a non-generative encoder and decision head. Its runtime already includes routing, calibration, abstention, hooks and evaluation. These are dependencies, not ReflexFoundry inventions. |
| [Laya training source](https://github.com/NandhaKishorM/laya/blob/main/laya/train.py) | Native `TrainConfig`/`finetune` supports cross-entropy or RLCD training, frozen encoders, option shuffling, explicit evaluation data, and typed rows containing `state`, `questions` and `gold` or `expected`. Use the existing implementation when compatible rather than cloning its training loop. |
| [Laya model card](https://huggingface.co/convaiinnovations/laya) | The English model uses a 421M-parameter ModernBERT-large backbone. Default context and checkpoint-specific limits matter. Published latency and accuracy figures apply to upstream conditions, not this project's workloads. |
| [Laya-MLX](https://github.com/mizorewww/laya-mlx) | Native Apple Silicon inference, including typed decisions and host integrations. Its README identifies an upstream compatibility revision; use tested compatible versions. The published millisecond timings are not a promise for cold startup or arbitrary coding inputs. |
| [stuntd](https://github.com/bladedevoff/stuntd) | Already discovers typed call sites, trains per-site frozen-Laya heads, measures holdout agreement, calibrates abstention, shadows, samples live checks, demotes and retrains. It also supports independently verified gold rows. A collect/train/shadow/deploy loop alone is therefore not an original contribution. |
| [jevals](https://github.com/openlayer-ai/jevals) | Provides trace evaluations and guardrails through typed decision models, including local Laya. A model grading its own decisions is insufficient independent evidence for this project. Prefer executable task checks where available. |
| [ReflexBench](https://github.com/brida-ai/reflexbench) | Separates semantics, calibration, option-order sensitivity, cardinality, failures, latency boundaries and policy value. Its [methodology](https://github.com/brida-ai/reflexbench/blob/main/METHODOLOGY.md) freezes cases and manifests before inference and separates model quality from deterministic policy effects. Borrow the evaluation discipline, not its scores. |
| [Jev description](https://laya.studio/glossary/jev) | A hosted, closed-weight typed decision API using `/v1/systemone`. Laya Studio describes a third-party product and is not its vendor. Hosted performance or pricing does not establish local benefit. No hosted comparator is required for the free local workflow. |
| [Codex](https://github.com/openai/codex) | The integration surface is explicit CLI/skill interaction and observable outputs. Native permissions and tool execution remain authoritative. No hidden deliberation or private internal state is needed. |

## Findings that change the design

[Fast Models, Slow Evidence](https://arxiv.org/abs/2610.02267), Jiawei Li,
October 2026, compares Laya and Jev with paired inputs and audits its own
evaluation. The paper reports option-order sensitivity, difficulty with many
similar choices, and weak zero-shot model routing. More consequentially, it
identifies inflated deployment conclusions caused by omitted screening cost,
confusing decision accuracy with final task quality, and selecting thresholds on
the evaluated examples. These are external findings, not measurements by
ReflexFoundry. The actionable response is to specialize a small candidate set,
reserve independent evaluation tasks, include every fallback and startup cost,
and refuse deployment when final outcomes do not support it.

The proposed contribution is **outcome-aware decision compilation**: identify
repeated, bounded decisions; train local typed policies; and authorize selective
use only when independent complete-workflow evidence supports both quality and
economics. It is a concrete tool and experimental method for Codex workflows,
not a claim to have invented selective prediction, calibration, distillation,
model routing or automated rollback.

## Statistical and learning foundations

- [On Calibration of Modern Neural Networks](https://proceedings.mlr.press/v70/guo17a.html),
  Guo et al., ICML 2017, studies confidence miscalibration and temperature scaling.
  Fit temperature only on calibration examples. Calibrated probabilities still
  do not prove end-to-end benefit or survive arbitrary distribution shift.
- [SelectiveNet](https://proceedings.mlr.press/v97/geifman19a.html), Geifman and
  El-Yaniv, ICML 2019, jointly learns prediction and rejection. The relevant
  comparison is a risk-versus-coverage curve: error among accepted decisions
  against the fraction accepted. Always-abstain may be safe but provides no
  useful delegation.
- [Learn then Test](https://arxiv.org/abs/2110.01052), Angelopoulos et al.,
  revised 2022, casts risk calibration as hypothesis testing. Trying many
  thresholds and choosing the best empirical result needs simultaneous-error
  control or a fresh confirmation split; a single unadjusted interval after
  threshold search is not a guarantee.
- [Conformal Risk Control](https://arxiv.org/abs/2208.02814), Angelopoulos et al.,
  revised June 2025, extends conformal prediction to monotone losses. Its
  assumptions and loss structure must actually hold before using its name as a
  guarantee. A simple empirical threshold in this project is not automatically
  a conformal method.
- [Learning to Route LLMs from Bandit Feedback](https://arxiv.org/abs/2510.07429),
  Wei et al., October 2025, treats deployment feedback as partial: generally only
  the selected action's outcome is observed. Unchosen candidate quality cannot
  be invented from these logs. Controlled experiments may execute all candidates;
  observational logs must record which outcomes are actually known.
- [WISERouter](https://arxiv.org/abs/2607.23765), Li et al., July 2026, formulates
  workload-budget routing as a contextual bandit and includes coding benchmarks.
  Cost-sensitive adaptive policy selection is existing work. ReflexFoundry can
  begin with offline held-out selection and avoid unnecessary online exploration.
- [ORACLE](https://arxiv.org/abs/2607.22465v4), Raj et al., October 2026 revision,
  studies task-appropriate verifier feedback and concurrent routing. Search
  indexes may still label earlier versions TRACE-ROUTER; cite the inspected
  version. Outcome feedback and verifier-aware agent routing are already active
  research topics, not an unoccupied novelty claim.
- [Routing Should Pay for Itself](https://arxiv.org/abs/2609.37402), Lai et al.,
  September 2026, explicitly includes supervision expenditure and deployment
  break-even volume. ReflexFoundry must likewise report training, collection,
  loading and inference costs rather than only warm decision latency.

## Confirmatory evaluation design

Use two initial decision families: a test subset to run next, and a context
retrieval source to inspect next. Both are suggestions within an existing
workflow. They do not authorize a command, suppress required final checks, or
replace an agent's permission judgment.

1. Freeze typed input fields, candidate meanings, fallback, cost budget and task
   grader before training. Give candidates stable semantic IDs; hash the complete
   specification and catalog. Catalog changes invalidate the deployment evidence.
2. Separate training, calibration and final test groups. Prefer repository-level
   separation; keep variants of the same bug or task in one group. Hash and
   deduplicate records before splitting. Do not tune after viewing final results.
3. Use task outcomes as labels or rewards when available. A proposed subset is
   successful only if the complete declared coding workflow meets its independent
   success criterion. Matching the original agent is a separate diagnostic.
4. Run paired task inputs and fixed budgets for: original workflow/no delegation,
   simple deterministic heuristic, ordinary untuned Laya, trained always-delegate,
   and trained selective delegation. Include a teacher-agreement-only ablation
   when outcome-aware training is claimed. Disclose omitted baselines explicitly.
5. Measure real wall time for collection, serialization, model loading, inference,
   fallback, downstream actions, independent verification and failures. Report cold
   and warm behavior separately. Do not translate subscription usage or wall time
   into unsupported dollar savings or energy savings.
6. Freeze the abstention threshold on calibration data. Report accepted count,
   covered error, full-workflow success, fallback rate and unnecessary fallback.
   Reject a candidate with insufficient accepted evidence. A high confidence
   threshold with almost no coverage is not a practical improvement.
7. Repeat trials, randomize execution order and preserve per-task raw outcomes.
   Report paired differences and uncertainty, with repository/task groups as the
   independent sampling unit. Repeated timing trials of the same task do not
   create independent correctness samples. Small fixtures cannot establish broad
   generalization to public repositories or ordinary agent use.
8. Stress reversed/random candidate order, similar descriptions, candidate count,
   unseen catalogs, truncated input, changed repositories and cold startup. Keep
   results separate from the primary distribution. Disable rather than silently
   extrapolate beyond the policy's recorded boundaries.
9. Start every policy in shadow mode. Promotion requires explicit opt-in and
   recorded held-out outcome evidence. Monitor independently observed outcomes,
   uncertainty, drift, latency and catalog identity. Revert on a material
   regression or invalid evidence. Never let a learned policy approve sensitive
   actions, credentials, destructive operations or permissions.

Synthetic or controlled coding fixtures are useful executable tests and honest
demonstrations. Label them as such. They do not substitute for held-out real
repositories or a live Codex task trial. A negative result, including an inference
overhead larger than the saved work, is a valid result and blocks promotion.

## What the executed studies do and do not establish

Both stage studies compare original actions, a deterministic heuristic, untuned
Laya, adapted always-delegation and adapted selective delegation. Untuned versus
adapted is an adaptation ablation; always versus selective isolates the gate.
The proposed teacher-agreement-only training ablation was **not executed**:
these controlled datasets do not contain original-agent teacher labels. The
studies do not isolate a causal benefit of outcome-aware supervision over
imitation, and no such improvement is established.

Forward and reverse order are all permutations of the supported two-choice
catalogs and were measured. Similar-description perturbations and larger-choice
catalogs were not separately evaluated as model-quality studies. Catalog change,
truncation and domain-refusal checks are engineering guards; they do not prove
model reliability under broad distribution shift.

The native Codex study has two independently verified repairs, no complete
matched comparison, and no captured agent usage totals. Its successful shadow
run refused inference because the frozen artifact binding was stale. Completing
the remaining old launch could at most add a refusal-path observation; it would
not by itself establish an operating compiled-policy comparison or model-usage
benefit. A valid future native study needs fixed matching model/runtime
artifacts, actual inference evidence, documented usage accounting and a bounded
comparison protocol. The original four-process cap still applies to that study.
Its blocked launch must not be retried without the pending scoped user authority
accepted by the same review control. These stage results do not complete the
full flagship end-to-end agent demonstration.

## Diagram generation feasibility

[PaperVizAgent](https://github.com/google-research/papervizagent) provides
candidate generation and image refinement through a Streamlit workflow. Its
documented setup asks for hosted model API keys. No free, subscription-compatible
execution path was established in this review, so it is not a dependency or a
reason to configure credentials. Original SVG/Mermaid diagrams and plots produced
from executed experiment records are a simpler reproducible route. Do not imply
PaperVizAgent generated project assets unless it actually ran.

## Attribution and scope of claims

See [third-party notices](../THIRD_PARTY_NOTICES.md) for license boundaries.
Published upstream benchmark numbers must retain their original provenance and
must never appear as ReflexFoundry measurements. Model cards, policy manifests
and release notes should identify the exact checkpoint, runtime version,
training-data provenance and measured experiment scope.
