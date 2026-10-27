# Inspect the published research head

The trained Laya head is a reproducible research artifact. **It did not earn deployment.** Source version 0.1.1 can reconstruct and inspect the v0.1.0 artifact while preserving its original evidence and failed promotion result.

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
