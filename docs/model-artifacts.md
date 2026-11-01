# Inspect the published research head

The trained Laya heads are reproducible research artifacts. **None earned deployment.** The current materialization command reconstructs published heads with their original metadata and complete identity. The first test-scope head and later context head have distinct versions; the context head's legacy CPU metadata needs an explicit derived copy, described below.

## Obtain the original artifact

Download `reflexfoundry-laya-head-v0.1.0.tar.gz` and `CHECKSUMS.sha256` from the [v0.1.0 release](https://github.com/nazeeh111/ReflexFoundry/releases/tag/v0.1.0). The expected archive SHA-256 is:

```text
18b1ab7ef70700a37d2aa58ee647819644602c5838857054f7b8bf5e48ca688e
```

Compare your download against the release checksums before extracting it into a fresh directory, for example `downloads/adapter-v0.1.0`. On macOS, `shasum -a 256 ARCHIVE` prints its digest; on Linux, use `sha256sum ARCHIVE`. A matching digest establishes which published bytes you downloaded, not that the model is suitable for your task.

The archive contains the trained safe tensor head, trained encoder/tokenizer metadata, calibration configuration, training manifest, internal training report and license notices. Keeping only the head weights is insufficient to reproduce the inference artifact.

## Reconstruct locally

From an installed source checkout, with Git available for the pinned training dependency:

```bash
python -m pip install -e '.[train]'
reflex download --output models/base
reflex materialize --base models/base \
  --head downloads/adapter-v0.1.0/head.safetensors \
  --output models/reconstructed-v0.1.0
```

Use a fresh output directory. Reconstruction verifies the adapter head, pinned base, full reconstructed weights and complete inference identity, including tokenizer and calibration configuration. A mismatch fails before publishing the output directory. No pickle weights are loaded.

The CLI requires the complete inference digest in the manifest. The published v0.1.0 adapter includes it; incomplete or altered exports must be regenerated from their trusted training output. Do not insert a new digest merely to make a mismatched artifact load.

## Inspect and evaluate

The original generated records and report are in [`benchmarks/run-001`](../benchmarks/run-001). A new evaluation can run against a copy of those records in a fresh workspace, with the reconstructed policy and the pinned base:

```bash
reflex evaluate --workspace runs/reproduction \
  --policy models/reconstructed-v0.1.0 --base models/base --backend torch
reflex lab --workspace runs/reproduction --output runs/reproduction/lab.html
```

Copy the original `records.jsonl` into that fresh workspace first. Its training rows must match the provenance manifest. For native Apple Silicon inference, install `.[apple]` and select `--backend mlx`. Different runtimes or host load change timing; record the new report instead of replacing the historical one.

Evaluation registers a policy for inspection, not automatic deployment. The original model has no supported context-retrieval, multilingual, production-repository, or general coding-agent benefit claim. Respect its withheld status, and keep independent verification and native permissions intact.

## Original context head used by the native study

Download [reflexfoundry-context-head-v0.2.0.tar.gz](https://github.com/nazeeh111/ReflexFoundry/releases/download/v0.2.0/reflexfoundry-context-head-v0.2.0.tar.gz) and its [checksums](https://github.com/nazeeh111/ReflexFoundry/releases/download/v0.2.0/CHECKSUMS.sha256). The expected archive SHA-256 is:

```text
5215901136c92ebaff2e921723581e41a1d941ac696f299996fc0b7aba8558c9
```

The verified archive has `head.safetensors` at its root, with the manifest, encoder/tokenizer metadata and notices. Extract it into a fresh directory, then reconstruct using the same pinned base:

```bash
reflex materialize --base models/base \
  --head downloads/context-v1/head.safetensors \
  --output models/reconstructed-context-v1
```

Its original complete inference digest is `23095775f1aabc10c4b1a13179306e7eb98b858782c05bf40c5bc6444d823cc2`. This differs from its full-weight SHA-256: the complete digest also binds tokenizer, encoder and calibration configuration. Do not substitute one digest for the other.

This historical context export uses the `TokenizersBackend` class alias. Current CPU loading refuses a config that upstream would rewrite. From a source checkout, create a separate compatible version explicitly:

```bash
python scripts/native_cpu_artifact.py \
  --source models/reconstructed-context-v1 \
  --output models/reconstructed-context-cpu-v1 \
  --source-release v0.2.0
```

The script verifies the original identity, preserves its manifest and source bytes, normalizes only the declared tokenizer metadata, and records before/after hashes. Weights and `tokenizer.json` remain unchanged. The CPU-compatible native-study digest is `2a78f9457b3a410366349585b69142ee0f2f177888f904e9d8812057a6fa5923`. Conversion neither grants eligibility nor replaces the historical report. Keep the original adapter and its notices with the derived version.

Evaluate the derived version in a fresh workspace with the original context records before considering any use. The retained native preparation did this and still failed seven promotion gates. The first v0.1.0 archive already uses `PreTrainedTokenizerFast`; this particular alias-conversion script is not needed for that artifact. Fresh training exports finalize metadata before freezing their identities.

## Matched label-source ablation heads

The [v0.2.2 release](https://github.com/nazeeh111/ReflexFoundry/releases/tag/v0.2.2) retains separate outcome-target and local-Laya-imitation heads, with `SHA256SUMS.json`. Their [study and reconstruction checks](../benchmarks/local-imitation-context-v1/README.md) distinguish these new fits from the original context head. Do not silently substitute one fit into another experiment's policy/report binding. All remain withheld.
