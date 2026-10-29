# Context retrieval experiment records

Use **scoped-v1/** for training and evaluation. Its records passed repository,
task-group, and identical-input split checks before the new context model trained.
See [the study](../../docs/context-benchmark.md) for source pins, grading, measured
cost boundaries, failures, and the one-repository-per-split limitation.

Other directories are diagnostic provenance and are excluded from the study:

- Parent records: artificial file hints derived from target metadata.
- no-file-hints/: removed those hints, but common API requests duplicated across splits.
- accounted-v1/: derived cost-accounting view of no-file-hints; same split failure.

Those earlier records and action timings are preserved. They must not be used as
accepted training or held-out evaluation evidence. The final scoped requests
were rerun through both actions, with three alternating-order trials each.
