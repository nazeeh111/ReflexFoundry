"""Create publication figures solely from executed experiment records."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

root = Path(__file__).resolve().parents[1]
r = json.loads((root / "benchmarks/run-001/report.json").read_text())
policies = r["policies"]
names = {
    "original-full": "Original full suite",
    "deterministic-heuristic": "Deterministic heuristic",
    "always-focused": "Always focused",
    "trained-always": "Trained Laya, always",
    "selective": "Trained Laya, selective",
    "ordinary-laya": "Untuned Laya",
}
plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.facecolor": "#f5f3ec",
        "axes.facecolor": "#f5f3ec",
    }
)
fig, (left, right) = plt.subplots(1, 2, figsize=(12, 4.5), gridspec_kw={"width_ratios": [1.2, 1]})
y = list(range(len(policies)))
colors = [
    "#26352c" if p["name"] == "original-full" else "#c84927" if p["name"] == "selective" else "#879482"
    for p in policies
]
left.barh(y, [p["mean_ms"] for p in policies], color=colors)
left.set_yticks(y, [names[p["name"]] for p in policies])
left.invert_yaxis()
left.set_xlabel("Mean validation-stage wall time (ms)")
left.set_title("Include cold startup on every CLI request", loc="left", fontweight="bold")
for i, p in enumerate(policies):
    left.text(p["mean_ms"] + 20, i, f"{p['mean_ms']:.1f}", va="center", fontsize=8)
left.set_xlim(0, max(p["mean_ms"] for p in policies) * 1.24)
right.barh(y, [p["success_rate"] * 100 for p in policies], color=colors)
right.set_yticks(y, [names[p["name"]] for p in policies])
right.invert_yaxis()
right.set_xlim(0, 110)
right.set_xlabel("Correct patch accept/reject (%)")
right.set_title("Independent public-contract grader", loc="left", fontweight="bold")
for i, p in enumerate(policies):
    right.text(p["success_rate"] * 100 + 1, i, f"{p['n'] - p['errors']}/{p['n']}", va="center", fontsize=8)
fig.suptitle(
    "ReflexFoundry · the reflex did not earn deployment", x=0.04, ha="left", fontweight="bold", fontsize=16
)
fig.text(
    0.04,
    0.015,
    "80 locked-test generated tasks, 8 repository groups. Shared fixture grammar limits generalization.\nRecorded costs, not a live-agent speedup. Selective fallback: 100%. Source: benchmarks/run-001/report.json",
    fontsize=8,
    color="#5b655c",
)
fig.tight_layout(rect=(0, 0.09, 1, 0.93))
(root / "assets").mkdir(exist_ok=True)
fig.savefig(root / "assets/benchmark.png", dpi=180)
fig.savefig(root / "assets/benchmark.svg")
print(root / "assets/benchmark.png")

# Normalize generated SVG whitespace for clean source diffs.
svg = root / "assets/benchmark.svg"
svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n")
