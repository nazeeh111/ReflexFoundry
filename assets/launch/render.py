"""Render a factual, silent 20-second release clip with local Pillow and FFmpeg.

Uses an executed report, its actual plot, and a screenshot of the real Lab.
No remote services, copied fonts, invented measurements, or simulated UI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT, FPS, SECONDS = 1280, 720, 24, 20
PAPER, INK, MUTED, RULE, ACCENT = "#f3f1e9", "#202720", "#62695e", "#d5d7cb", "#ce4c22"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def font(size: int, *, bold: bool = False, italic: bool = False) -> ImageFont.FreeTypeFont:
    if italic:
        candidates = ["/System/Library/Fonts/Supplemental/Georgia Italic.ttf", "DejaVuSerif-Oblique.ttf"]
    elif bold:
        candidates = ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "DejaVuSans-Bold.ttf"]
    else:
        candidates = ["/System/Library/Fonts/Supplemental/Arial.ttf", "DejaVuSans.ttf"]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    raise RuntimeError("Install a local Arial or DejaVu font; fonts are not downloaded or bundled.")


def fit(image: Image.Image, box: tuple[int, int, int, int]) -> tuple[Image.Image, tuple[int, int]]:
    image = image.copy().convert("RGB")
    x, y, w, h = box
    image.thumbnail((w, h), Image.Resampling.LANCZOS)
    return image, (x + (w - image.width) // 2, y + (h - image.height) // 2)


def frame(t: float, report: dict, chart: Image.Image, lab: Image.Image) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)
    draw.line((52, 96, 1228, 96), fill=RULE, width=2)
    draw.text((52, 35), "REFLEXFOUNDRY", fill=INK, font=font(28, bold=True))
    draw.text((950, 42), "v0.1.0 / EXPERIMENTAL", fill=MUTED, font=font(16))
    draw.line((52, 649, 1228, 649), fill=RULE, width=2)
    draw.text((52, 670), "LOCAL POLICIES. VERIFIED OUTCOMES.", fill=MUTED, font=font(14))
    draw.text((851, 670), "github.com/nazeeh111/ReflexFoundry", fill=INK, font=font(15))

    if t < 4:
        offset = round(16 * (1 - min(1, t / .5)) ** 3)
        draw.text((52, 159 + offset), "Fast decisions.", fill=INK, font=font(94, bold=True))
        draw.text((52, 278 + offset), "Earned trust.", fill=ACCENT, font=font(102, italic=True))
        draw.text((57, 432), "Teach agents which decisions can become local reflexes.", fill=MUTED, font=font(27))
        draw.text((57, 530), "OBSERVE  /  TRAIN  /  VERIFY  /  SHADOW  /  DEPLOY", fill=INK, font=font(20))
    elif t < 9:
        draw.text((52, 117), "Inspect every proposed shortcut.", fill=INK, font=font(32, bold=True))
        shot, pos = fit(lab, (52, 174, 1176, 423))
        image.paste(shot, pos)
        draw.text((52, 610), "Actual Lab snapshot from the executed fixture experiment.", fill=MUTED, font=font(18))
    elif t < 15:
        draw.text((52, 117), "Measure the whole decision cost.", fill=INK, font=font(32, bold=True))
        plot, pos = fit(chart, (44, 176, 1192, 422))
        image.paste(plot, pos)
        draw.text((52, 611), "Generated patch validation. Cold loading and integrity checks included.", fill=MUTED, font=font(18))
    else:
        selective = next(p for p in report["policies"] if p["name"] == "selective")
        draw.rectangle((52, 140, 312, 181), fill=ACCENT)
        draw.text((67, 150), "DEPLOYMENT BLOCKED", fill=PAPER, font=font(18, bold=True))
        draw.text((52, 223), "The reflex did not", fill=INK, font=font(75, bold=True))
        draw.text((52, 316), "earn deployment.", fill=ACCENT, font=font(78, italic=True))
        fallback = selective["fallback_rate"] * 100
        draw.text((57, 458), f"{fallback:.0f}% fallback. Keep the original workflow.", fill=INK, font=font(31))
        draw.text((57, 531), "A trained model is a candidate. Evidence decides whether it is useful.", fill=MUTED, font=font(24))

    # Brief continuous brightness fade, without hiding the settled reading holds.
    local = t if t < 4 else t - 4 if t < 9 else t - 9 if t < 15 else t - 15
    if local < .13:
        alpha = .65 + .35 * min(1, local / .13)
        image = Image.blend(Image.new("RGB", image.size, PAPER), image, alpha)
    return image


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--chart", type=Path, default=Path(__file__).with_name("benchmark.png"))
    p.add_argument("--lab", type=Path, required=True, help="actual captured Lab screenshot")
    p.add_argument("--output", type=Path, required=True, help="fresh output directory")
    args = p.parse_args()
    report = json.loads(args.report.read_text())
    if report.get("deployment_allowed") is not False:
        raise ValueError("This factual storyboard requires an actually rejected policy report.")
    if not all(math.isfinite(float(p["mean_ms"])) for p in report["policies"]):
        raise ValueError("Report contains nonfinite measurements")
    if args.output.exists():
        raise FileExistsError("Choose a fresh render directory; valid outputs are preserved.")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required for the free local render.")
    chart = Image.open(args.chart).convert("RGB")
    lab = Image.open(args.lab).convert("RGB")
    args.output.mkdir(parents=True)
    staging = args.output / "rendering.mp4"
    cmd = [ffmpeg, "-n", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{WIDTH}x{HEIGHT}", "-r", str(FPS), "-i", "pipe:0", "-an", "-c:v", "libx264",
           "-preset", "fast", "-crf", "19", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(staging)]
    process = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        assert process.stdin is not None
        for index in range(FPS * SECONDS):
            process.stdin.write(frame(index / FPS, report, chart, lab).tobytes())
        process.stdin.close()
        if process.wait():
            raise RuntimeError("FFmpeg failed; staged output retained for diagnosis.")
    except BaseException:
        process.kill()
        process.wait()
        raise
    final = args.output / "reflexfoundry-v0.1.0.mp4"
    staging.rename(final)
    for t in (2, 6.5, 12, 17.5):
        frame(t, report, chart, lab).save(args.output / f"frame-{t:g}.png")
    manifest = {"duration_s": SECONDS, "fps": FPS, "width": WIDTH, "height": HEIGHT, "audio": "none",
                "report_sha256": sha(args.report), "chart_sha256": sha(args.chart),
                "lab_sha256": sha(args.lab), "render_source_sha256": sha(Path(__file__)),
                "video_sha256": sha(final), "scope": report["scope"],
                "provenance": "Original typography and motion; actual Lab screenshot and report-derived plot. No generated UI or remote media."}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(final)


if __name__ == "__main__":
    main()
