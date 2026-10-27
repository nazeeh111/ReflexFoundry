# Experimental Laya test-scope head, v1

Apache-2.0, adapted from `convaiinnovations/laya` revision `7b928d828b7b0e022f929d9bd2e44165aa270148` with upstream Laya source commit `b9fe351ce81e2d974bca2bf219c1e4030c0a05ea`.

This is a genuinely trained frozen-encoder decision head, not a fast-rule surrogate or an untrained checkpoint. Training used 160 generated validation records, split internally into 136 optimization and 24 calibration items. Four soft-cross-entropy epochs, seed17, shuffled options, MPS. The complete configuration and executed training diagnostics are in manifest.json and train_report.json. Training took101,656.55ms on this run; host-dependent, not a general speed claim.

**Deployment rejected.** In the80-task locked generated test, always using the trained choice produced74 correct patch accept/reject decisions; the file heuristic and original full suite each produced80. The calibrated cold-CLI policy abstained100% and cost more than the original workflow. Internal calibration accuracy is not independent test accuracy. This adapter is for reproduction and shadow research only.

Get `reflexfoundry-laya-head-v0.1.0.tar.gz` from the GitHub prerelease. It contains head.safetensors plus these metadata files. Download the pinned base with `reflex download --output models/base`, extract the adapter to a directory, then use:

```sh
reflex materialize --base models/base --head extracted/head.safetensors --output models/reconstructed
```

Materialization requires matching SHA-256 digests, base revision, tensor names and shapes. It copies the trained calibration configuration and training manifest. It never loads pickle weights. Run your own evaluation with the exact declared workflow before any opt-in use. Speculative use for permissions, credentials or destructive actions is prohibited by the product boundary.

This adapter has no validation for context retrieval, multilingual tasks, production codebases, or autonomous full coding tasks. Only synthetic public-contract task inputs were used; no private transcripts or user project source was included. See the repository research, evaluation boundaries and third-party notices.
