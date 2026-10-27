# Contributing

Useful contributions improve a real bounded decision or make the evidence easier to trust. Small reproducible bug reports, independent outcome graders, realistic held-out workloads, and simpler baselines are welcome.

## Development

Use Python 3.11 or newer in a local virtual environment:

```bash
python -m pip install -e '.[dev]'
ruff check src tests
mypy src/reflexfoundry
pytest -q
python -m build
```

Core development does not require model weights or paid APIs. Add `.[train]` for local Laya training or `.[apple]` for optional native MLX inference. Keep temporary downloads and experiment artifacts outside source directories, and use a fresh output path for each experiment.

## Changes and evidence

Explain the problem and resulting behavior. Include a small reproduction and checks appropriate to the change. Test meaningful contracts and failure paths, especially privacy filtering, evidence validation, inference fallback, and lifecycle transitions. Avoid tests that merely copy the implementation.

Preserve unrelated work. Never weaken a gate to make a benchmark look successful. Keep observations, externally reported results, and your own inference distinct. A result that rejects a learned policy can be a valuable contribution.

## New workloads and decision specifications

A proposed decision needs typed allowed inputs, stable candidate meanings, an original-workflow fallback, a cost budget, risk boundaries, and a success criterion independent of the policy. Permission, destructive-action, credential and security-approval decisions are outside the supported scope.

Separate training, calibration, promotion and locked test groups. Keep related tasks and variants in the same group. Retain immutable source versions, licenses, hashes, grader code, raw outcomes and timing trials. Do not turn repeated timing trials into independent correctness samples. Include the original workflow and a strong deterministic heuristic before adding a complicated baseline.

New public-repository benchmarks must establish the pristine baseline before attributing a failure to a patch. Label generated mutations, selected examples and naturally occurring tasks accurately. Report failed and unavailable checks, not just successful runs.

## Data, models and licensing

Share only explicitly authorized, reviewed examples. Do not submit private transcripts, secrets, personal identifiers, proprietary code, or sensitive logs. Synthetic fixtures are preferable for reproducing ingestion bugs. Inspect Lab exports before attaching them.

Every bundled model, dataset, copied source file, font or media asset needs an origin, version, license and required notice. Update [third-party notices](THIRD_PARTY_NOTICES.md) when relevant. The source license does not automatically license upstream weights or external datasets.

Before a pull request, check links and command examples against the current CLI. Use the actual report for numerical figures and keep plot sources with their data provenance. See the [release checklist](docs/release-checklist.md) for publication checks.
