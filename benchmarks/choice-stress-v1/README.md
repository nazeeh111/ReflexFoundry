# Choice wording and redundant-catalog diagnostic

This local study probes the untuned and outcome-trained context heads on twelve
retained public inputs: the first and last lexicographic record ID in each of
six cachetools test target groups. This is exploratory reuse of an existing test
set, with one actual repository. It is not a fresh heldout benchmark.

Before any prediction, `plan.json` freezes the inputs, outcomes, model identities,
script hash, package versions, token limit and tested orders. The same inputs
reach both models. Original model files and native-study preparation remain
unchanged; inference uses disposable CPU model copies.

The three conditions are:

- Original two-choice wording, in both orders.
- Two descriptions with a shared phrasing pattern that preserve the difference
  between named-symbol lookup and repository text search, in both orders.
- Four choices formed by adding one exact semantic alias for each original
  action. Four cyclic rotations place each alias in each position once. They
  cover four of the 24 permutations and do not establish general order stability.

The four-choice condition expands redundant representations of the same two
retrieval actions. It does not test a wider range of distinct tools. The model's
selected individual alias determines the mapped action. Probabilities summed
across equivalent aliases are reported separately and never replace that
selection.

The protocol makes 192 raw predictions: 12 inputs × eight condition/order
combinations × two models. Orders and input variants are repeated measurements,
not 192 independent tasks. Malformed responses, missing explicit truncation
evidence, and truncated requests are retained without retries or replacement
inputs. Per-input summaries retain missing observations and do not report a
population confidence interval.

Any outcome lookup means **previously measured target-context coverage** from
the retained source-retrieval study. The diagnostic runs neither a retrieval
action nor an autonomous repair and does not measure coding success. Per-query
wall times and startup times are local diagnostics under uncontrolled host load,
including concurrent local training; no speed, cost or energy claim follows.
The trained policy's failed promotion is unchanged.

Reproduce with local compatible model directories matching the plan's artifact
identities and the optional training runtime installed:

```sh
PYTHONPATH=src python scripts/choice_stress.py --prepare-only \
  --base /path/to/untuned --trained /path/to/compatible-context-head \
  --output /path/to/fresh-diagnostic
PYTHONPATH=src python scripts/choice_stress.py --run \
  --base /path/to/untuned --trained /path/to/compatible-context-head \
  --output /path/to/fresh-diagnostic
```

The prepared plan refers to the explicit CPU-compatible context artifact described
in [the native-study protocol](../../docs/native-study-v2.md), not a silently
modified original export. Existing ledgers cannot be overwritten or retried by
this script. A stopped attempt stays incomplete and cannot support complete
comparison claims.

## Executed result

All 192 planned predictions completed, with no malformed returns, missing usage
or truncation. The original model files and plan remained unchanged.

| Condition | Orders tested | Untuned: inputs with action flip / 12 | Trained: inputs with action flip / 12 |
| --- | ---: | ---: | ---: |
| Original wording, 2 choices | 2/2 | 1 | 1 |
| Parallel wording, 2 choices | 2/2 | 4 | 4 |
| Exact action aliases, 4 choices | 4/24 | 4 | 3 |

These are descriptive counts on the same twelve retained inputs. The wording
condition left all first-order mapped actions unchanged for both models; its
additional observed instability appeared when order was reversed. The alias
condition changed the first-order action on 3 inputs for untuned Laya and 2 for
the trained head. Its individual winning alias disagreed with the action having
the highest summed probability mass on 5/48 and 4/48 observations, respectively.
Those are repeated observations, not independent tasks. The recorded selection
remains the individual winner.

Using the retained context-coverage lookup, original wording covered 19/24 order
observations for each model, and parallel wording 16/24 for each. The four-choice
condition covered 36/48 untuned and 37/48 trained observations. These counts reuse
the same source-action outcomes and do not establish actual repair quality,
newly executed retrieval success, or a causal training advantage.

Raw predictions are in `observations.jsonl`; `summary.json` preserves per-input
counts, errors, truncation, and the measured experiment duration. No new model
was trained or promoted by this diagnostic.
