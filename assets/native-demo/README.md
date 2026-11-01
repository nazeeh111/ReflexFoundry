# Native coding evidence replay

The selected master is [the 44-second replay](render-v1/reflexfoundry-native-stopped-evidence-replay.mp4): 1280 × 720, 24 fps, silent. [The manifest](render-v1/manifest.json) binds its actual source, model receipts, candidates, report, analysis and system-font identities. It is an editorial evidence replay, not a screen recording or real-time speed demonstration.

It follows a supplied Funcy defect, actual trained-model symbol retrieval in trial 04, that trial's real source repair, and its independent focused/full/contract checks. Trial 05's guarded fallback is a separate measured trial. Trial 01 produced identical repaired source. The comparison retains all five arms, unequal valid counts, the call-18 timeout and unattempted calls 19–20. No improvement or deployment approval is claimed.

The study stopped incomplete. Seventeen repairs passed independent checks across 18 started calls. The failed attempt has no completed-turn usage or validated inference receipt. Its cause is unknown. Means use valid rows only; paired analysis is available in the [study report](../../benchmarks/codex-e2e-v2/README.md). No model became eligible for deployment.

## Reproduce

Use free local Pillow, FFmpeg and ffprobe. Fonts are read from local Arial, Georgia and Menlo, with DejaVu fallbacks; font files are not copied or bundled. From the repository root, choose a fresh output directory:

```bash
python assets/native-demo/render.py \
  --study benchmarks/codex-e2e-v2/execution \
  --analysis benchmarks/codex-e2e-v2/analysis/analysis.json \
  --task-source scripts/native_study_tasks.py \
  --provenance benchmarks/codex-e2e-v2/execution/observer-provenance.json \
  --output /tmp/reflexfoundry-native-replay-new \
  --frames-only
```

Inspect current-source frames first. Omit `--frames-only` and choose another fresh directory to encode. The renderer requires the actual stopped-study record and exact retained inputs; a complete-study claim, altered result, attempted later call or changed candidate is refused. It executes no native agent, model or candidate code.

The encoder owns its process and has a 300-second limit. It verifies one silent video stream, 1,056 frames, dimensions, rate and duration, then decodes the full master. Frame evaluation is deterministic, including backward seeks. Earlier media and complete-only drafts remain preserved separately.

Technical media verification and sampled frame inspection do not establish full-speed perceptual review. The manifest keeps that distinction explicit. Current visual and receiving checks are recorded in [QA.md](QA.md).
