"""A separate amended replay; the historical replay and phase A stay unchanged."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import selectors
import signal
import statistics
import subprocess
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

BASE_SHA = "3c78c3e4a40893dca288f36af2f49d8e86b830766d052a2caaf0063f7f0a1e1a"
PLAN_SHA = "0634b5648f675aa6cd08e47397397298f7b83e10b7eb1ab00e5afb86440752d1"
AMENDMENT_SHA = "2851023e7a647d9d32d65966c10063f60573c8d1d80477f2b07c309fd7a7dcfd"
REVIEW_SHA = "6663ad88ac0920ccfe49ca02bef789e7418a1349476bd36094a90021f238b59b"
DRIVER_SHA = "795acd32764313fb7d4afde9114c9c9e45211bc5b6d36d75f581ad9d7c185d9f"
WIDTH, HEIGHT, FPS, SECONDS = 1280, 720, 24, 44
SUPPLEMENT = frozenset({"preflight/cachetools-getitem.json", "preflight/funcy-first.json"})
TIMES = (0, 2.5, 5.95, 6, 10.5, 12.95, 13, 16, 18.95, 19, 22, 24.95, 25, 29, 33.95, 34, 38, 43.95)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(base_path: Path, phase_a: Path, original_analysis: Path, continuation: Path,
         amended_analysis: Path, task_source: Path, provenance: Path) -> dict[str, Any]:
    hashes: dict[str, str] = {}

    def read(path: Path, expected: str | None = None) -> bytes:
        if path.is_symlink():
            raise ValueError(f"linked input refused: {path}")
        raw = path.read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        if expected is not None and actual != expected:
            raise ValueError(f"changed input: {path}")
        hashes[str(path.resolve())] = actual
        return raw

    def js(path: Path, expected: str | None = None) -> Any:
        return json.loads(read(path, expected))

    base_bytes = read(base_path, BASE_SHA)
    spec = importlib.util.spec_from_file_location("historical_native_replay", base_path)
    assert spec and spec.loader
    base = importlib.util.module_from_spec(spec)
    # Only the exact pinned, reviewed renderer bytes are executed; no stale cache is read.
    exec(compile(base_bytes, str(base_path), "exec"), base.__dict__)  # noqa: S102
    historical = base.load_evidence(phase_a, original_analysis, task_source, provenance)
    hashes.update(historical["hashes"])
    amendment = js(continuation / "amendment.json", AMENDMENT_SHA)
    review = js(continuation / "review.json", REVIEW_SHA)
    read(continuation / "continue_native.py", DRIVER_SHA)
    if (amendment["original_plan_sha256"] != PLAN_SHA
            or amendment["driver_sha256"] != DRIVER_SHA
            or review["amendment_sha256"] != AMENDMENT_SHA
            or review["driver_sha256"] != DRIVER_SHA
            or review["independent_review_complete"] is not True
            or review["scope_indices"] != [19, 20] or review["unresolved_blockers"]):
        raise ValueError("amendment and independent review are not bound")
    files = amendment["original_phase_files"]
    if len(files) != 135:
        raise ValueError("expected all135 registered phase-A files")
    supplemented = []
    for relative, expected in files.items():
        name = Path(relative)
        if name.is_absolute() or ".." in name.parts:
            raise ValueError("unsafe phase-A manifest path")
        path = phase_a / name
        if not path.exists():
            if relative not in SUPPLEMENT:
                raise ValueError(f"missing phase-A file: {relative}")
            path = continuation / "phase-a-supplement" / name
            supplemented.append(relative)
        read(path, expected)
    analysis = js(amended_analysis)
    meta = analysis.get("continuation", {})
    if (analysis.get("completed_observations") != 20
            or analysis.get("protocol_valid_observations") != 19
            or analysis.get("all_twenty_complete_and_protocol_valid") is not False
            or analysis.get("planned_repository_groups") != 2
            or meta.get("amendment_sha256") != AMENDMENT_SHA
            or meta.get("review_sha256") != REVIEW_SHA
            or meta.get("driver_sha256") != DRIVER_SHA
            or meta.get("scope_indices") != [19, 20]):
        raise ValueError("analysis does not describe the actual amended19valid/1timeout study")
    rows = analysis.get("observations", [])
    byindex = {row["index"]: row for row in rows}
    if len(rows) != 20 or set(byindex) != set(range(1, 21)):
        raise ValueError("analysis must preserve all20 unique observations")
    results = dict(historical["results"])
    plan = historical["plan"]
    for index in (19, 20):
        folder = continuation / "attempts" / f"{index:02}"
        item = plan["order"][index - 1]
        result = js(folder / "result.json")
        started = js(folder / "started.json")
        invocation = js(folder / "invocation.json")
        js(folder / "review.json", REVIEW_SHA)
        bindings = {"index": index, "phase": "reviewed-continuation-01",
                    "amendment_sha256": AMENDMENT_SHA, "review_sha256": REVIEW_SHA,
                    "original_plan_sha256": PLAN_SHA}
        if any(record.get(key) != value for record in (result, started, invocation)
               for key, value in bindings.items()):
            raise ValueError("continuation attempt is not bound to its reviewed phase")
        if (any(result.get(key) != item[key] for key in ("task", "repeat", "arm"))
                or result.get("native_process_started") is not True
                or started.get("native_process_started") is not True
                or result.get("protocol_failure") is not False
                or result.get("task_success") is not True
                or result.get("inference_observed") is not True
                or result.get("observed_receipt_valid") is not True
                or result.get("immutable_files_preserved") is not True
                or result.get("expected_retrieval_calls") != 1
                or result.get("retrieval_command_attempts") != 1
                or result.get("timed_out") is not False
                or result.get("cli_exit_code") != 0
                or result.get("invalid_events") != 0 or result.get("event_errors") != 0
                or result.get("telemetry", {}).get("completed_turns") != 1
                or result.get("extra_files") != []):
            raise ValueError("continuation does not prove an independently successful inference repair")
        if any(result["independent"][name].get("passed") is not True
               for name in ("focused", "full", "public_contract")):
            raise ValueError("independent continuation check did not pass")
        receipts = result.get("retrieval_receipts", [])
        if len(receipts) != 1:
            raise ValueError("one validated worker receipt required")
        receipt, context = receipts[0], result["context"]
        required = {"arm": item["arm"], "inference_observed": True,
                    "request_digest": item["request_digest"], "source_sha256": item["mutated_source_sha256"],
                    "runtime_digest": base.digest(plan["runtime_files"]),
                    "cli_sha256": plan["runtime_files"]["reflex_cli.py"],
                    "model_artifact_digest": plan["model_artifact_digest"],
                    "policy_sha256": plan["policy_sha256"], "report_sha256": plan["report_sha256"],
                    "decision_contract_digest": plan["decision_contract_digest"],
                    "context_digest": base.digest(context), "prediction": context["prediction"],
                    "prediction_digest": base.digest(context["prediction"])}
        if any(receipt.get(key) != value for key, value in required.items()):
            raise ValueError("continuation inference receipt identities changed")
        read(folder / "candidate.py", result["candidate_sha256"])
        results[index] = result
    for index, result in results.items():
        row = byindex[index]
        path = (phase_a if index <= 18 else continuation) / "attempts" / f"{index:02}" / "result.json"
        read(path, row["result_sha256"])
        if (any(row.get(key) != result[key] for key in ("index", "task", "repeat", "arm"))
                or row.get("protocol_valid") is not (index != 18)
                or row.get("independently_verified_success") is not (index != 18)):
            raise ValueError("analysis outcomes differ from actual retained results")
        usage = result["telemetry"]["token_usage"]
        metrics = {key: result[key] for key in ("cli_wall_ms", "pipeline_wall_ms")}
        metrics.update({key: usage[key] if usage is not None else None
                        for key in ("input_tokens", "cached_input_tokens", "output_tokens")})
        if row["metrics"] != metrics:
            raise ValueError("analysis metrics differ from actual result bytes")
        if index != 18 and (any(not base.finite(v) or v < 0 for v in metrics.values())
                            or usage["cached_input_tokens"] > usage["input_tokens"]):
            raise ValueError("invalid finite metrics or cached-subset counter")
    if (len(results) != 20 or sum(r["protocol_failure"] for r in results.values()) != 1
            or sum(r["task_success"] for r in results.values()) != 19
            or sum(r.get("inference_observed", False) for r in results.values()) != 11
            or sum(pair["valid"] for pair in analysis.get("pairs", [])) != 15):
        raise ValueError("actual amended counts differ from the factual replay")
    arms = []
    for arm in base.ARMS:
        group = [r for r in results.values() if r["arm"] == arm and not r["protocol_failure"]]
        if len(group) != (3 if arm == "ordinary-laya" else 4):
            raise ValueError("unexpected per-arm valid count")
        arms.append({"arm": arm, "n": len(group),
                     "cli_seconds": statistics.mean(r["cli_wall_ms"] for r in group) / 1000,
                     "pipeline_seconds": statistics.mean(r["pipeline_wall_ms"] for r in group) / 1000,
                     "input_tokens": statistics.mean(r["telemetry"]["token_usage"]["input_tokens"] for r in group),
                     "output_tokens": statistics.mean(r["telemetry"]["token_usage"]["output_tokens"] for r in group)})
    return {"base": base, "historical": historical, "results": results, "arms": arms,
            "hashes": hashes, "supplemented": supplemented, "analysis": analysis}


def frame(t: float, evidence: dict[str, Any]) -> Image.Image:
    base = evidence["base"]
    if not base.finite(t) or not 0 <= t < SECONDS:
        raise ValueError("frame time outside half-open44-second timeline")
    if t < 25:
        return base.frame(t, evidence["historical"])
    image = Image.new("RGB", (WIDTH, HEIGHT), base.PAPER)
    draw = ImageDraw.Draw(image)
    def text(xy: tuple[int, int], value: str, size: int = 24, color: str = base.INK, style: str = "regular") -> None:
        base.text(draw, xy, value, size, color, style, max_width=1164)
    draw.line((58, 92, 1222, 92), fill=base.RULE, width=2)
    text((58, 35), "REFLEXFOUNDRY", 27, style="bold")
    text((907, 41), "AMENDED REPLAY", 18, base.RUST, "bold")
    draw.line((58, 642, 1222, 642), fill=base.RULE, width=2)
    text((58, 663), "Editorial time. Not a screen recording or real-time speed demonstration.", 17, base.MUTED)
    if t < 34:
        text((58, 123), "All five arms. One retained timeout.", 39, style="bold")
        text((58, 182), "20 calls / 19 valid repairs / 15 valid pairs / reviewed continuation", 24, base.MUTED)
        xs = (58, 495, 657, 822, 984, 1132)
        for x, label in zip(xs, ("POLICY", "VALID / 4", "CLI MEAN", "PIPELINE", "INPUT*", "OUTPUT")):
            text((x, 245), label, 16, base.MUTED, "bold")
        for i, (name, row) in enumerate(zip(base.NAMES, evidence["arms"])):
            y = 286 + i * 54
            draw.line((58, y + 42, 1222, y + 42), fill=base.RULE)
            color = base.RUST if i == min(4, int((t - 25) / 0.65)) and t < 28.25 else base.INK
            values = (name, f"{row['n']}/4", f"{row['cli_seconds']:.1f}s", f"{row['pipeline_seconds']:.1f}s",
                      base.compact(row["input_tokens"]), base.compact(row["output_tokens"]))
            for j, (x, value) in enumerate(zip(xs, values)):
                text((x, y), value, 22 if j == 0 else 23, color, "bold" if j == 0 else "regular")
        text((58, 582), "Means use valid rows only. Unequal counts; two repositories; shared baselines.", 20, base.MUTED)
        text((58, 612), "*Input includes cached subset. Publication/time gap; no causal or savings claim.", 19, base.MUTED)
    else:
        offset = round(12 * (1 - base.ease((t - 34) / .45)))
        text((58, 126 + offset), "19 verified repairs.", 65, style="bold")
        text((58, 209 + offset), "One timeout preserved.", 60, base.RUST, "italic")
        text((62, 318), "Calls 19 and 20: remaining original cases, after review.", 27, style="bold")
        text((62, 375), "Phase A was published. Continuation followed a time gap.", 26, base.MUTED)
        text((62, 424), "Trial 18 was never retried. Its usage remains unavailable.", 26, base.MUTED)
        text((62, 473), "Not an uninterrupted or fully protocol-valid study.", 28, base.RUST, "bold")
        text((62, 531), "The trained policy remains withheld.", 31, base.GREEN, "bold")
        text((62, 594), "Unknown timeout cause. No broad reliability, superiority or savings claim.", 21, base.MUTED)
    return image


def encode(evidence: dict[str, Any], output: Path, ffmpeg: str) -> tuple[Path, list[str]]:
    staging = output / "rendering.mp4"
    cmd = [ffmpeg, "-n", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{WIDTH}x{HEIGHT}", "-r", str(FPS), "-i", "pipe:0", "-an", "-c:v", "libx264",
           "-preset", "fast", "-crf", "19", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(staging)]
    with (output / "ffmpeg.log").open("wb") as log:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                stderr=log, start_new_session=True)
        assert proc.stdin
        os.set_blocking(proc.stdin.fileno(), False)
        selector = selectors.DefaultSelector()
        selector.register(proc.stdin, selectors.EVENT_WRITE)
        deadline = time.monotonic() + 300
        try:
            for i in range(FPS * SECONDS):
                pending = memoryview(frame(i / FPS, evidence).tobytes())
                while pending:
                    if time.monotonic() >= deadline or proc.poll() is not None:
                        raise RuntimeError("owned encode expired or ended before all frames")
                    if selector.select(timeout=min(1, max(0, deadline - time.monotonic()))):
                        try:
                            pending = pending[os.write(proc.stdin.fileno(), pending):]
                        except BlockingIOError:
                            pass
            selector.unregister(proc.stdin)
            proc.stdin.close()
            if proc.wait(timeout=max(1, deadline - time.monotonic())):
                raise RuntimeError("FFmpeg failed; staging preserved")
        except BaseException:
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=5)
            raise
        finally:
            selector.close()
    final = output / "reflexfoundry-amended-native-replay.mp4"
    staging.rename(final)
    return final, cmd


def main() -> None:
    import shutil

    parser = argparse.ArgumentParser(__doc__)
    for name in ("base-render", "phase-a", "original-analysis", "continuation", "amended-analysis", "task-source", "provenance", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--frames-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("choose a fresh output; previous masters are preserved")
    evidence = load(args.base_render, args.phase_a, args.original_analysis, args.continuation,
                    args.amended_analysis, args.task_source, args.provenance)
    base = evidence["base"]
    for t in (0, 2.5, 10.5, 16, 22, 24.95):
        if frame(t, evidence).tobytes() != base.frame(t, evidence["historical"]).tobytes():
            raise ValueError("historical first25seconds changed")
    before = frame(10.5, evidence).tobytes()
    frame(38, evidence)
    if frame(10.5, evidence).tobytes() != before:
        raise ValueError("nonsequential frame evaluation changed pixels")
    args.output.mkdir(parents=True, exist_ok=False)
    diagnostic = args.output / "diagnostic"
    diagnostic.mkdir()
    for t in TIMES:
        frame(t, evidence).save(diagnostic / f"frame-{t:05.2f}.png")
    frame(38, evidence).resize((960, 540), Image.Resampling.LANCZOS).save(args.output / "poster.png")
    video = command = probe = None
    if not args.frames_only:
        ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            raise RuntimeError("local FFmpeg/ffprobe required; no download is performed")
        video, command = encode(evidence, args.output, ffmpeg)
        probe = json.loads(subprocess.check_output([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)], text=True, timeout=30))
        streams = probe["streams"]
        if (len(streams) != 1 or streams[0]["codec_type"] != "video" or streams[0]["codec_name"] != "h264"
                or streams[0]["width"] != WIDTH or streams[0]["height"] != HEIGHT
                or streams[0]["r_frame_rate"] != "24/1" or int(streams[0]["nb_frames"]) != FPS * SECONDS
                or abs(float(probe["format"]["duration"]) - SECONDS) > .05):
            raise ValueError("encoded media contract failed")
        subprocess.run([ffmpeg, "-v", "error", "-i", str(video), "-f", "null", "-"],
                       check=True, capture_output=True, timeout=120)
    manifest = {"format": 1, "kind": "amended evidence replay, not screen recording",
                "status": "frames-only; unreviewed" if args.frames_only else "encoded and technically verified; perceptual review pending",
                "duration_seconds": SECONDS, "fps": FPS, "frame_count": FPS * SECONDS, "width": WIDTH, "height": HEIGHT, "audio": "none",
                "study": "20starts,19valid,1retainedtimeout; reviewed continuation after publication/time gap; not uninterrupted or fully protocol-valid",
                "phase_a_unchanged": True, "trial18_never_retried": True, "usage_trial18": None,
                "base_render_sha256": BASE_SHA, "source_sha256": sha(Path(__file__)), "evidence_sha256": evidence["hashes"],
                "registered_phase_a_files_verified": 135, "supplemented_missing_files": evidence["supplemented"],
                "first25seconds_use_unmodified_base_frame": True, "sampled_exact_pixel_equality": True,
                "backward_frame_determinism": True, "means": evidence["arms"],
                "font_sources": {style: {"path": base.font_path(style), "sha256": sha(Path(base.font_path(style)))} for style in ("regular", "bold", "italic", "mono")},
                "diagnostic_sha256": {p.name: sha(p) for p in sorted(diagnostic.iterdir())},
                "poster_sha256": sha(args.output / "poster.png"), "video_sha256": sha(video) if video else None,
                "ffmpeg_argv": command, "ffprobe": probe,
                "limits": ["Editorial time, not measured process speed. Silent; no audio judgment is implied.",
                           "Protocol-valid means exclude retained timeout18 with unavailable usage. Two repository groups and shared baselines; no causal or monetary savings claim.",
                           "The original phaseA replay and18-attempt records remain historical. Calls19/20 complete original remaining cases under a reviewed append-only amendment after publication/time gap.",
                           "Raw trial04proposal/candidate/independentchecks are real; trial05guardedfallback is separate. Agent-side checks/order remain agent-reported.",
                           "Sampled stills and technical verification do not establish normal-speed motion quality. Policy remains withheld."]}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(args.output.resolve()), "video": str(video) if video else None, "status": manifest["status"]}))


if __name__ == "__main__":
    main()
