# Public-source context retrieval benchmark

The second executable decision family, `context-route-v1`, compares two fixed,
read-only retrieval actions on four pinned public Python repositories. The
retained run contains **132 queries across 24 curated public targets**, with
three measured, alternating-order trials per action and query. No repository
module, build script, test suite, agent, or language model executes in this
benchmark. Only ReflexFoundry's local AST and text algorithms run.

This experiment measures whether retrieved source covers a specified public
implementation and its documented contract. It does not measure coding-task
completion or prove that the retrieved context is sufficient for a repair.

## Sources and observed results

| Split | Public repository and immutable source revision | Queries / target groups | Symbol coverage | Search coverage | Mean symbol / search time |
| --- | --- | --- | --- | --- | --- |
| Train | [Toolz](https://github.com/pytoolz/toolz/tree/451af60dec590a6010e2babdbf391ea8f815122f) | 42 / 6 | 24 / 42 | 18 / 42 | 717.348 / 390.425 ms |
| Calibration | [Funcy](https://github.com/Suor/funcy/tree/a876c7e1cf11e7c746e91fce4632ebfa93865428) | 30 / 6 | 12 / 30 | 18 / 30 | 426.521 / 69.972 ms |
| Promotion | [Blinker](https://github.com/pallets-eco/blinker/tree/c3364059663df1ddce32799d6b1922af89a345f6) | 30 / 6 | 12 / 30 | 20 / 30 | 55.844 / 18.685 ms |
| Locked test | [cachetools](https://github.com/tkem/cachetools/tree/e7104dd52bfe0e3aced6f3439fb6ed4d9c8ff52a) | 30 / 6 | 12 / 30 | 30 / 30 | 123.467 / 52.800 ms |

Each table time is the arithmetic mean of per-query accounted durations from the
executed `scoped-v1` run, before model overhead. Each duration adds the measured
repository source-loading startup to the median of three in-memory retrieval
trials. Every action is charged the same measured startup on each modeled
request. `median_action_ms`, `corpus_startup_ms`, and `trials_ms` retain the
components. This is a retrospective cost model using measured components, not
direct native-CLI or full-agent elapsed time. Grading and repository preparation
are outside the action costs. Host load was not controlled; timing variation
is visible in the raw trials and the results should not be generalized to other
machines. There is no measured full-run elapsed field.

Neither action covered the target for 6 train, 6 calibration, and 5 promotion
queries. These failures remain in the dataset. They have
`oracle.neither_action_succeeded: true`; their `selected: search` is the
conservative fallback, not a successful teacher label. Training excludes these rows from positive labels and records their IDs in the
model manifest. All held-out failures remain in evaluation. Test search covered every target
in this small workload; a learned router still needs to beat that baseline after
paying its own cost.

**There is one actual repository in each split.** Rephrasing a query does not
create an independent task. Each repeated target shares one `task_group`, and
there are only six target groups per split. These data exercise the pipeline,
not a reliable broad deployment decision. The benchmark manifest explicitly
sets `deployment_allowed: false`. Successful query counts cannot override the
independent repository and target-group limits.

## Trained policy comparison

A genuine frozen-encoder Laya head trained for four epochs on 36 usable Toolz
examples (31 optimization,5 internal calibration). Six neither-success records
were excluded from positive supervision. Training took 342.766 seconds on the
shared local host. Internal temperature was not fitted because five items were
below upstream's ten-item minimum; independent external calibration still
controlled delegation. Configuration, labels, hashes and diagnostics are in
[the adapter metadata](../models/adapter-context-v1/).

| Held-out cachetools policy | Covered targets | Accounted mean time | Fallback |
| --- | --- | --- | --- |
| Original search | 30 / 30 | 52.8 ms | 0% |
| Deterministic heuristic | 30 / 30 | 142.7 ms | 0% |
| Always symbol | 12 / 30 | 123.5 ms | 0% |
| Trained always-delegation | 20 / 30 | 16,480.4 ms | 0% |
| Trained selective delegation | 30 / 30 | 16,397.6 ms | 100% |
| Ordinary Laya | 20 / 30 | 5,936.5 ms | 0% |

The heuristic chooses symbol lookup only when the input explicitly provides a
symbol. Every arm uses the same retained action outcomes. Trained arms include
15,218.1ms of measured model startup and artifact screening on every modeled
cold request, plus both option-order inference passes and the selected action.
Ordinary Laya includes its separately measured 4,982.4ms startup and inference.
Loading order, caches and uncontrolled host load limit direct comparisons of
absolute startup costs. These are summed measured components, not repeated full
CLI or live-agent elapsed times. They establish no token, dollar, energy or
subscription savings.

**The policy is withheld.** External calibration produced no eligible
threshold, option order flipped on 5 of 30 test queries, the promotion workload
failed the required accepted-repository evidence, and selective delegation had
no supported net time benefit. Test retrieval coverage was preserved entirely
by fallback. With one actual repository in promotion and test, paired
population intervals are explicitly unavailable. All failing held-out requests
remain in the report. These are controlled public-API queries, not sampled
real-agent coding issues. The separate native Codex comparative trial remains
incomplete and is not replaced by this experiment.

## Fixed actions and independent grading

`symbol` parses the bounded public source corpus with Python's AST parser. If an
explicit `symbol` is provided, it returns the first matching function, class, or
qualified method definition, up to 8,192 bytes. A missing symbol returns no
snippet. Known `changed_files` are searched first. No source is imported.

`search` performs bounded case-insensitive literal and word matching over source
lines. It ranks matching lines, prioritizes known file hints on equal scores,
and returns at most three surrounding source windows, each bounded to 8,192
bytes. It uses no AST and no target annotations. Generic stopwords are fixed in
the implementation.

The separate grader uses hand-curated expectations checked against the pinned
source: public symbol, source file, exact declaration signature, and a distinct
public docstring phrase. A returned snippet succeeds only when it includes both
signature and contract phrase in the expected file. Those expectations never
enter a retriever as labels, line numbers, or oracle metadata. These are controlled, docstring-derived queries, not a sampled distribution of
real agent or user tasks. Some name the public API; others use its documented
description without a symbol. Every accepted request names its public repository, preventing identical common
API requests from crossing partitions. The split validator checks this before
training. Every accepted record has `changed_files: []`;
no oracle source path or declaration signature is supplied as a file hint. Source text is public, so retaining snippets does not collect private
agent transcripts.

Six targets per repository cover sequence helpers, signal connection and
receiver methods, and cache classes/decorators. Seven training variants and
five other variants vary explicit symbols, public descriptions, capitalization,
and symbol availability. They are related views of the same targets, not newly
independent examples or naturally occurring issue reports.

## Reproduce

Use Python 3.11 or newer and the installed ReflexFoundry package. Supply clean
checkouts at the immutable commits above under a single source parent:

```text
/public-source-parent/toolz
/public-source-parent/funcy
/public-source-parent/blinker
/public-source-parent/cachetools
```

Then execute the trusted benchmark, choosing a fresh output directory:

```sh
reflex benchmark --decision context-route-v1 \
  --sources /public-source-parent --output context-rerun --repeats 3
```

The library entry point is:

```python
from pathlib import Path
from reflexfoundry.context_benchmark import generate

parent = Path('/public-source-parent')
records = generate(
    Path('context-rerun'),
    {name: parent / name for name in ('toolz', 'funcy', 'blinker', 'cachetools')},
    repeats=3,
)
```

The generator checks exact Git revisions and tracked cleanliness before reading
package sources. It fetches nothing, installs nothing, and refuses an existing
nonempty output directory. Inputs are bounded to 128 Python files, 4 MiB total,
and 256 KiB per file. Symlinked source files and paths escaping the checkout are
rejected. Package roots include bundled test source when it lives inside the
package; the full corpus and each file's hash are recorded rather than inferred.

## Retained evidence and attribution

The accepted no-file-hints run is in
[`benchmarks/context-v1/scoped-v1`](../benchmarks/context-v1/scoped-v1/).
`records.jsonl` contains the task groups and actual scalar outcomes;
`manifest.json` pins corpus hashes, target expectations, limits, and source
startup measurements. Each `evidence/*.json` preserves actual action order,
three trial timings, returned source snippets, and snippet hashes. Files under
`licenses/` preserve Toolz and Funcy's BSD 3-Clause licenses and Blinker and cachetools'
MIT licenses, including original copyright and permission notices. Those licenses apply to the included source
snippets; ReflexFoundry does not relicense them or claim authorship.

The checkouts were previously downloaded from the linked official repositories
into disposable local storage. The run reads their public source and Git
metadata only. Source checks and independent declaration/contract grading support
these stage-level observations; no local-model savings, paid API comparison,
external adoption, or autonomous-agent result is inferred.

The parent `context-v1/` run and child `no-file-hints/` and `accounted-v1/`
runs are preserved as diagnostic provenance, not training or evaluation inputs.
The parent supplied artificial file hints from target metadata. Removing the
hints still left identical public API requests in Toolz and Funcy; split
validation rejected them. The fresh `scoped-v1/` run names the repository in each
request, supplies no oracle file hints, reruns both actions, and passes the
repository, task-group and input-identity split checks. Earlier timings were
not reassigned to changed requests.

The accepted records SHA-256 is
`8c80ebfe7b11913a5983e8f0826f4ce6f41f32e26c0518cee5f8ef2a46401dfb`.
