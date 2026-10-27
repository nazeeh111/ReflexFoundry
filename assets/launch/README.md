# Launch media sources

The launch clip uses original ReflexFoundry typography, an actual rendered Lab snapshot, and the plot generated from the executed experiment report. It is silent, 20 seconds, 1280 × 720, at 24 frames per second.

The story is deliberately factual: inspect a candidate, measure the whole decision cost, and withhold deployment when the reflex fails the gate. A trained policy does not establish an improvement.

## Re-render

Use local Pillow and FFmpeg. Pillow is available through the project's development dependencies. Install FFmpeg separately through a free local route if it is absent. Fonts are resolved from local Arial or DejaVu installations; font files are not bundled or downloaded.

From the repository root, after exporting and capturing the current Lab:

```bash
python assets/launch/render.py \
  --report benchmarks/run-001/report.json \
  --chart assets/benchmark.png \
  --lab assets/launch/final-v2/lab-desktop.png \
  --output /tmp/reflexfoundry-launch-rerender
```

The output directory must not exist. Valid renders are preserved. The source rejects reports that do not actually withhold deployment. The final manifest binds the executed report, chart, Lab screenshot, render source and video by SHA-256.

The native video source is `render.py`. Its four deterministic scenes cover a brand introduction, the real Lab, the real benchmark plot, and the report's deployment verdict. Source edits are sufficient to change typography, timing or composition. No remote service, generated UI, paid API, narration, stock media or copied font is involved.

## Verification

Inspect the current video with `ffprobe`, decode the full file with FFmpeg, and review decoded settled frames and both sides of scene transitions. Check duration, dimensions, frame rate, audio absence, clipping and readable holds. Verify manifest hashes against the actual release files after copying them.

Keep the report and screenshot current together. A provisional render made before a report correction is not a final release artifact. The final clip is `render-v2/reflexfoundry-v0.1.0.mp4`, with provenance in `render-v2/manifest.json`; it binds report SHA-256 `d6215d2e2a4999d8204923f507e1d85e8c22065774286ac771f0a6f6149022fa`. The actual Lab capture sources and visual QA are in `final-v2/`.

The retained local `render-v1/` preview used earlier cost accounting and is excluded from the release handoff. Do not distribute it as the final experiment result. The final render has passed full FFmpeg decode, frame count/dimensions/duration checks, and visual inspection of decoded settled and transition frames. It has one H.264 video stream, 480 frames, and no audio stream.
