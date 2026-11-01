# Native coding evidence replay

The selected master is [the amended 44-second replay](render-v2/reflexfoundry-amended-native-replay.mp4): 1280 × 720, 24 fps, silent. [The manifest](render-v2/manifest.json) binds its actual source, model receipts, candidates, report, analysis and system-font identities. It is an editorial evidence replay, not a screen recording or real-time speed demonstration.

It follows a supplied Funcy defect, actual trained-model symbol retrieval in trial 04, that trial's real source repair, and its independent focused/full/contract checks. Trial 05's guarded fallback is a separate measured trial. Trial 01 produced identical repaired source. The comparison retains all five arms, unequal valid counts and the call-18 timeout. Calls 19–20 ran as the two remaining original cases after review and a publication/time gap.

Nineteen repairs passed independent checks across 20 started calls. The failed attempt has no completed-turn usage or validated inference receipt. Its cause is unknown and it was never retried. This is not an uninterrupted or fully protocol-valid study. Means use valid rows only; paired analysis is available in the [study report](../../benchmarks/codex-e2e-v2/README.md). No model became eligible for deployment. The original [phase-A replay](render-v1/reflexfoundry-native-stopped-evidence-replay.mp4), [QA record](QA.md), and [Lab](lab.html) remain historical snapshots.

## Reproduce

Use free local Pillow, FFmpeg and ffprobe. Fonts are read from local Arial, Georgia and Menlo, with DejaVu fallbacks; font files are not copied or bundled. From the repository root, choose a fresh output directory:

```bash
python assets/native-demo/render_amended.py \
  --base-render assets/native-demo/render.py \
  --phase-a benchmarks/codex-e2e-v2/execution \
  --original-analysis benchmarks/codex-e2e-v2/analysis/analysis.json \
  --continuation benchmarks/codex-e2e-v2/continuation \
  --amended-analysis benchmarks/codex-e2e-v2/amended-analysis/analysis.json \
  --task-source scripts/native_study_tasks.py \
  --provenance benchmarks/codex-e2e-v2/execution/observer-provenance.json \
  --output /tmp/reflexfoundry-native-replay-new \
  --frames-only
```

Inspect current-source frames first. Omit `--frames-only` and choose another fresh directory to encode. The renderer requires the actual stopped-study record, reviewed continuation and exact retained inputs. Altered results, a retry of trial 18, changed candidates or an uninterrupted-study claim are refused. The first 25 seconds use the original renderer's frame function unchanged. It executes no native agent, model or candidate code.

The encoder owns its process and has a 300-second limit. It verifies one silent video stream, 1,056 frames, dimensions, rate and duration, then decodes the full master. Frame evaluation is deterministic, including backward seeks. Earlier media remain preserved separately.

Technical media verification and sampled frame inspection do not establish full-speed perceptual review. The manifest keeps that distinction explicit. Current checks are recorded in [QA-amended.md](QA-amended.md). Open the [current portable Lab](lab-amended.html), or inspect its [desktop](lab-amended-desktop.png) and [mobile](lab-amended-mobile.png) captures.
