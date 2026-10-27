# Public repository holdout smoke

Executed on six hand-authored candidate patches in two public repositories:

| Repository | Pinned commit | Original complete suite |
| --- | --- | --- |
| [Toolz](https://github.com/pytoolz/toolz/tree/451af60dec590a6010e2babdbf391ea8f815122f) | `451af60dec590a6010e2babdbf391ea8f815122f` | 192 passed; one Python-version skip |
| [Funcy](https://github.com/Suor/funcy/tree/a876c7e1cf11e7c746e91fce4632ebfa93865428) | `a876c7e1cf11e7c746e91fce4632ebfa93865428` | 295 passed |

Each repository has a behavior-preserving refactor, a mutation caught by its
official focused test, and a shared-helper mutation missed by that focused test.
Every candidate runs the unchanged official full suite and a separately authored
public-contract grader. Focused and full commands run twice in alternating order.
`duration_ms` is the median observed subprocess wall time, including Python and
pytest startup. No artificial sleep or model latency is included.

Full-suite acceptance/rejection matched the independent grader on all six
candidates. Focused tests falsely accepted two shared-helper mutations. These
six deliberately chosen cases demonstrate the failure mode; they do not estimate
its natural prevalence. Two repositories are too few for a strong repository-level
statistical claim. This evaluates validation of supplied patches, not autonomous
coding-task completion or LLM cost savings.

`records.jsonl` preserves all choices and outcomes, `logs/` preserves actual
suite/grader output and repeated timing, and `manifest.json` preserves original
baseline results, commits, record digest and limitations. `licenses/` contains
the BSD-3-Clause notices for both upstream projects. The mutations and grader
sources are in `src/reflexfoundry/external_benchmark.py`.

## Reproduce

Use Python 3.12. The executed environment used pytest 9.1.1, whatever 0.7, and
the pinned Toolz package (version metadata 1.2.0). Funcy's official test requirements
list pytest 7.4.3; this run used the existing newer pytest and its entire suite
passed with warnings treated as errors. No tests were excluded to obtain a pass.

Create clean checkouts at the commits above under a temporary directory, with
subdirectories named `toolz` and `funcy`. Install pytest and whatever into an
isolated environment. Install the pinned Toolz source normally into that same
environment so its official package-version metadata test can find its metadata.
The runner imports candidate code from each temporary repository copy.

From the ReflexFoundry source checkout, using that environment's Python:

```sh
PYTHONPATH=src python -m reflexfoundry.external_benchmark \
  --sources /absolute/path/to/temporary/checkouts \
  --output /absolute/path/to/fresh-results \
  --repeats 2
```

The runner verifies the exact commit and rejects tracked source modifications.
It never fetches repositories, installs dependencies or modifies supplied
checkouts. All candidate modifications occur in disposable temporary copies.
The output directory must be empty so evidence from separate runs cannot mix.

Exploration also checked Boltons: two original socket tests were blocked by the
local sandbox, so it was excluded without bypassing that boundary. More-itertools'
original 929-test suite passed but took 87.6 seconds, so it was excluded from this
bounded smoke study. Neither project's measurements enter the retained six-task
comparison.
