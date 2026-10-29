# Experimental Laya context retrieval head, v1

Apache-2.0, adapted from `convaiinnovations/laya` revision
`7b928d828b7b0e022f929d9bd2e44165aa270148`, using upstream Laya source
`b9fe351ce81e2d974bca2bf219c1e4030c0a05ea`.

This is a genuinely trained frozen-encoder head for `context-route-v1`.
The public Toolz training partition had42 requests;36 had at least one successful
retrieval action. Six neither-success requests were excluded from positive
supervision. Only those 36examples reached the upstream trainer, internally
split into31 optimization and5 calibration items. Four epochs, soft-cross-entropy,
seed 17, shuffled choice order, MPS. Training took 342,765.68 ms on the shared host.
The five-item internal calibration was too small to fit temperature, which
stayed 1.0. Internal metrics do not establish held-out reliability.

**Deployment rejected.** On 30controlled cachetools test queries, original
repository search covered 30targets, the deterministic heuristic covered 30,
and trained always-delegation covered 20. Untuned Laya also covered 20.
Selective delegation fell back on all 30 and cost more than original search.
There is one actual repository per partition. Repository-level confidence
intervals are unavailable, and these data cannot support broad promotion.
See `docs/context-benchmark.md` and the retained evaluation for complete costs,
failures, source provenance, and boundaries. These are source-coverage results,
not autonomous coding-task outcomes or measured full-agent latency.

The release archive `reflexfoundry-context-head-v0.2.0.tar.gz` contains
head.safetensors and the complete inference metadata. Download the pinned base
with `reflex download --output models/base`, extract this adapter, then run:

```sh
reflex materialize --base models/base --head extracted/head.safetensors \
  --output models/context-reconstructed
```

Materialization checks base revision, tensor names/shapes, head hash, full
weights hash, and the complete tokenizer/configuration identity. It loads no
pickle weights. Training examples, the manifest and upstream diagnostics are
included. Public source snippets retain upstream BSD/MIT licenses in the study;
no private transcripts or projects were used. Use this failed candidate for
reproduction and shadow research only. It cannot authorize permissions,
credentials, destructive actions, or security-critical decisions.
