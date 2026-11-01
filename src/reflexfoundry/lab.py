"""Offline, read-only evidence laboratory. No server, telemetry or tool execution."""
from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any

from .core import discover, privacy_filter, read_json, read_records, spec_dicts

_NATIVE_ARMS = (
    "original-agent", "deterministic-heuristic", "ordinary-laya", "trained-always", "selective-shadow",
)
_NATIVE_METRICS = ("cli_wall_ms", "pipeline_wall_ms", "input_tokens", "cached_input_tokens", "output_tokens")
_NATIVE_MAX_BYTES = 512 * 1024


def _native_for_display(path: Path) -> dict[str, Any] | None:
    """Reduce bounded native analysis to numeric summaries and known arm IDs.

    Do not carry observations, source text, paths, transcripts or provenance into
    the HTML. Derive completeness and means from actual observation statuses.
    """
    if path.is_symlink():
        raise ValueError("native-study.json must be a regular file, not a link")
    if not path.exists():
        return None
    if not path.is_file():
        raise ValueError("native-study.json must be a regular file, not a link")
    with path.open("rb") as handle:
        raw = handle.read(_NATIVE_MAX_BYTES + 1)
    if len(raw) > _NATIVE_MAX_BYTES:
        raise ValueError("native-study.json exceeds its 512 KiB display limit")
    source = json.loads(raw)
    if not isinstance(source, dict) or type(source.get("format")) is not int or source["format"] != 1:
        raise ValueError("native study requires analysis format 1")
    for key, expected in (("planned_observations", 20), ("planned_repository_groups", 2)):
        if type(source.get(key)) is not int or source[key] != expected:
            raise ValueError("native study requires the bounded 20-observation, 2-repository analysis")
    observations = source.get("observations")
    if not isinstance(observations, list) or len(observations) != 20:
        raise ValueError("native study must retain all 20 planned observations, including missing rows")
    rows: list[dict[str, Any]] = []
    indices: set[int] = set()
    identities: set[tuple[str, int, str]] = set()
    for row in observations:
        if not isinstance(row, dict):
            raise ValueError("native observations must be objects")
        index, task, repeat, arm = (row.get(key) for key in ("index", "task", "repeat", "arm"))
        if (type(index) is not int or index not in range(1, 21) or index in indices
                or not isinstance(task, str) or task not in {"funcy-first", "cachetools-getitem"}
                or not isinstance(arm, str)
                or type(repeat) is not int or repeat not in (1, 2) or arm not in _NATIVE_ARMS):
            raise ValueError("native observation has an unknown or duplicate identity")
        identity = (task, repeat, arm)
        if identity in identities:
            raise ValueError("native observation has a duplicate task/repeat/arm")
        indices.add(index)
        identities.add(identity)
        status = row.get("status")
        completed, valid = row.get("result_present"), row.get("protocol_valid")
        expected_status = {
            "missing": (False, False), "started-no-result": (False, False),
            "protocol-failed": (True, False), "protocol-valid": (True, True),
        }
        if (not isinstance(status, str) or status not in expected_status or type(completed) is not bool or type(valid) is not bool
                or (completed, valid) != expected_status[status]):
            raise ValueError("native observation status is inconsistent")
        success = row.get("independently_verified_success")
        if ((success is not None and type(success) is not bool) or (valid and success is None)
                or (not completed and success is not None)):
            raise ValueError("native independent outcome must be explicit or unavailable")
        metrics = row.get("metrics")
        if not isinstance(metrics, dict):
            raise ValueError("native observation metrics must be an object")
        compact = {}
        for key in _NATIVE_METRICS:
            value = metrics.get(key)
            if value is not None and (type(value) not in (int, float) or value < 0 or value > 2**63 - 1
                                      or not math.isfinite(value) or (key.endswith("tokens") and type(value) is not int)):
                raise ValueError("native metrics must be finite nonnegative numbers")
            if valid and value is None:
                raise ValueError("protocol-valid native metrics cannot be missing")
            compact[key] = value
        cached, inputs = compact["cached_input_tokens"], compact["input_tokens"]
        if cached is not None and inputs is not None and cached > inputs:
            raise ValueError("native cached tokens are a subset of input tokens")
        inference = row.get("inference_observed", False)
        if type(inference) is not bool or (inference and (not completed or arm not in _NATIVE_ARMS[2:])):
            raise ValueError("native model-inference observation is inconsistent")
        if valid and arm in _NATIVE_ARMS[2:] and not inference:
            raise ValueError("protocol-valid model arms require observed inference")
        rows.append({"task": task, "repeat": repeat, "arm": arm, "completed": completed, "valid": valid,
                     "success": success, "metrics": compact, "inference": inference})
    completed_count = sum(row["completed"] for row in rows)
    valid_count = sum(row["valid"] for row in rows)
    for key, expected in (("completed_observations", completed_count), ("protocol_valid_observations", valid_count)):
        if type(source.get(key)) is not int or source[key] != expected:
            raise ValueError("native summary counts disagree with observation rows")
    arms = []
    for arm in _NATIVE_ARMS:
        group = [row for row in rows if row["arm"] == arm]
        valid_rows = [row for row in group if row["valid"]]
        arms.append({"arm": arm, "planned": len(group), "completed": sum(row["completed"] for row in group),
                     "protocol_valid": len(valid_rows), "protocol_failed": sum(row["completed"] and not row["valid"] for row in group),
                     "independent_checked": sum(row["success"] is not None for row in group),
                     "independent_successes": sum(row["success"] is True for row in group),
                     "means": {key: statistics.mean(row["metrics"][key] for row in valid_rows) if valid_rows else None
                               for key in _NATIVE_METRICS}})
    original = {(row["task"], row["repeat"]): row for row in rows if row["arm"] == "original-agent"}
    pairs = []
    for arm in _NATIVE_ARMS[1:]:
        matched = [(row, original[(row["task"], row["repeat"])]) for row in rows
                   if row["arm"] == arm and row["valid"] and original[(row["task"], row["repeat"])]["valid"]]
        pairs.append({"arm": arm, "n": len(matched), "planned": 4,
                      "success_delta": sum(int(row["success"]) - int(base["success"]) for row, base in matched),
                      "means": {key: statistics.mean(row["metrics"][key] - base["metrics"][key]
                                                     for row, base in matched) if matched else None
                                for key in ("cli_wall_ms", "pipeline_wall_ms", "input_tokens", "output_tokens")}})
    return {"planned": 20, "completed": completed_count, "protocol_valid": valid_count,
            "protocol_failed": completed_count - valid_count, "complete": completed_count == valid_count == 20,
            "repository_groups": 2, "model_inference_observations": sum(row["valid"] and row["inference"] for row in rows),
            "arms": arms, "pairs": pairs}


def _records_for_display(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Render an allowlist, never arbitrary metadata or unfiltered transcripts."""
    return [
        {
            "id": row.get("id", ""),
            "spec": row.get("spec", ""),
            "split": row.get("split", "unassigned"),
            "selected": row.get("selected", ""),
            "inputs": privacy_filter({
                key: value for key, value in row.get("inputs", {}).items()
                if key in {"summary", "changed_files", "symbol"}
            }),
            "outcomes": row.get("outcomes", {}),
            "source": row.get("source", ""),
            "repository": row.get("repository", ""),
        }
        for row in records
    ]


def build_lab(workspace: Path, output: Path) -> Path:
    """Build a portable HTML snapshot of actual evidence from ``workspace``.

    Reads records.jsonl, evaluation.json, deployment.json and optional
    native-study.json when present.
    ``output`` may be an HTML filename or a directory (index.html is written).
    This is a read-only report, not a policy-control surface.
    """
    workspace, output = Path(workspace), Path(output)
    records = read_records(workspace / "records.jsonl")
    payload = {
        "records": _records_for_display(records),
        "discovery": discover(records),
        "evaluation": read_json(workspace / "evaluation.json", {}),
        "deployment": read_json(workspace / "deployment.json", {}),
        "specs": spec_dicts(),
        "native": _native_for_display(workspace / "native-study.json"),
    }
    # JSON is data inside a non-executing script element. Escape HTML delimiters
    # to prevent even a malicious input from terminating that element.
    serialized = (json.dumps(payload, ensure_ascii=True, allow_nan=False)
                  .replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e"))
    target = output if output.suffix.lower() == ".html" else output / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_HTML.replace("__REFLEX_DATA__", serialized), encoding="utf-8")
    return target


_HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'">
<title>ReflexFoundry Lab · Decision evidence</title>
<style>
:root{--paper:#f3f1e9;--white:#fffef8;--ink:#202720;--muted:#62695e;--rule:#d5d7cb;--accent:#ce4c22;--green:#3c6246;--pale:#e4e9d8;--mono:ui-monospace,SFMono-Regular,Consolas,monospace;--sans:Arial,Helvetica,sans-serif}*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:24px}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 var(--sans)}button,input,select{font:inherit}a{color:inherit}a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible{outline:3px solid var(--accent);outline-offset:4px}.shell{display:grid;grid-template-columns:226px minmax(0,1fr);min-height:100vh}.rail{position:sticky;top:0;align-self:start;height:100vh;border-right:1px solid var(--rule);padding:30px 25px;display:flex;flex-direction:column}.logo{display:flex;align-items:center;gap:9px;text-decoration:none;font-size:16px;font-weight:800;letter-spacing:-.7px}.mark{width:29px;height:33px;flex:none}.edition{font:10px var(--mono);letter-spacing:1.7px;color:var(--muted);margin:12px 0 40px}.rail nav{display:grid;gap:5px}.rail nav a{text-decoration:none;padding:10px 0;color:var(--muted);font-size:13px;display:flex;gap:16px}.rail nav a:hover{color:var(--accent)}.rail nav span{font:11px var(--mono);padding-top:3px}.rail-bottom{margin-top:auto;font:10px/1.8 var(--mono);color:var(--muted);border-top:1px solid var(--rule);padding-top:16px}.dot{display:inline-block;width:6px;height:6px;background:var(--green);border-radius:50%;margin-right:7px}.main{max-width:1500px;width:100%;padding:30px 44px 40px}.topline{display:flex;justify-content:space-between;gap:20px;font:10px var(--mono);letter-spacing:1.4px;padding-bottom:21px;border-bottom:1px solid var(--rule);text-transform:uppercase}.topline b{color:var(--accent);font-weight:400}.hero{display:grid;grid-template-columns:minmax(0,1fr) 260px;gap:32px;padding:36px 0 30px}.eyebrow{font:10px var(--mono);letter-spacing:1.6px;text-transform:uppercase;color:var(--muted);margin-bottom:12px}h1{font-size:clamp(36px,4vw,60px);line-height:1.03;letter-spacing:-3px;font-weight:600;margin:0 0 18px;max-width:680px}h1 em{font-family:Georgia,serif;font-weight:400;color:var(--accent)}.intro{max-width:560px;color:var(--muted);font-size:14px;margin:0}.status-card{border:1px solid var(--ink);background:var(--white);padding:20px;align-self:center;position:relative}.status-card:before{content:'';position:absolute;left:-1px;top:-1px;width:35px;height:3px;background:var(--accent)}.status-card .label{font:10px var(--mono);letter-spacing:1px}.status-card h2{font-size:26px;line-height:1.2;margin:14px 0 9px;letter-spacing:-1px}.status-card p{font-size:12px;color:var(--muted);margin:0}.badge{font:10px var(--mono);text-transform:uppercase;display:inline-block;padding:5px 8px;background:var(--pale);color:var(--green);white-space:nowrap}.badge.warn{background:#f6e3d4;color:#9d3c1d}.badge.neutral{background:#e9eae3;color:var(--muted)}.pipeline{display:grid;grid-template-columns:repeat(7,1fr);border:1px solid var(--rule);margin:0 0 27px}.stage{padding:13px 10px;border-right:1px solid var(--rule);background:#ebece3;min-width:0}.stage:last-child{border:0}.stage-number{font:9px var(--mono);color:var(--muted);display:block;margin-bottom:6px}.stage-name{font-size:11px;text-transform:uppercase;letter-spacing:.5px;font-weight:600}.stage.ready{background:var(--pale)}.stage.current{background:var(--ink);color:var(--white)}.stage.current .stage-number{color:#a5b39b}.metrics{display:grid;grid-template-columns:repeat(4,1fr);border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);margin:0 0 34px}.metric{padding:18px 15px 19px 0;border-right:1px solid var(--rule);margin-right:20px}.metric:last-child{border:0;margin-right:0}.metric .value{display:block;font-size:33px;letter-spacing:-1.5px;line-height:1.2;margin-bottom:7px}.metric .value small{font:12px var(--mono);letter-spacing:0;color:var(--muted)}.metric .caption{font:10px var(--mono);color:var(--muted);text-transform:uppercase;letter-spacing:.6px}.metric .note{font-size:11px;color:var(--muted);margin-top:4px}.section{margin-bottom:34px;scroll-margin-top:24px}.section-head{display:flex;justify-content:space-between;align-items:baseline;gap:15px;margin-bottom:15px}.section-head h2{font-size:22px;letter-spacing:-.7px;font-weight:500;margin:0}.section-head h2 span{font:11px var(--mono);color:var(--accent);margin-right:12px}.section-head .sub{font:10px var(--mono);color:var(--muted)}.panel{background:var(--white);border:1px solid var(--rule)}.panel-inner{padding:22px}.comparison{display:grid;grid-template-columns:minmax(0,1fr) 260px}.chart-area{padding:22px;border-right:1px solid var(--rule)}.chart-caption{font:10px var(--mono);color:var(--muted);margin:0 0 20px;text-transform:uppercase;letter-spacing:.7px}.chart-row{display:grid;grid-template-columns:138px minmax(70px,1fr) 75px;gap:14px;align-items:center;margin:15px 0}.chart-name{font-size:12px}.chart-track{height:24px;background:#f0f0e8;position:relative;overflow:hidden}.chart-bar{height:100%;background:#aab5a1;min-width:2px}.chart-row.selective .chart-bar{background:var(--accent)}.chart-row.original .chart-bar{background:var(--ink)}.chart-value{font:12px var(--mono);text-align:right}.chart-key{display:flex;gap:18px;font:10px var(--mono);color:var(--muted);margin-top:22px}.key-box{display:inline-block;width:7px;height:7px;margin-right:6px;background:var(--ink)}.chart-note{font-size:11px;color:var(--muted);border-top:1px solid var(--rule);padding-top:13px;margin:18px 0 0}.evidence-aside{padding:23px}.evidence-aside h3{font-size:15px;font-weight:500;margin:0 0 12px}.evidence-aside p{font-size:12px;color:var(--muted)}.reason{display:flex;gap:10px;padding:10px 0;border-top:1px solid var(--rule);font-size:11px}.reason i{font:11px var(--mono);font-style:normal;color:var(--accent)}.fine{font:10px/1.7 var(--mono);color:var(--muted);overflow-wrap:anywhere}.policies{width:100%;border-collapse:collapse;font-size:12px}.policies th{text-align:left;font:9px var(--mono);text-transform:uppercase;letter-spacing:.7px;padding:11px 14px;background:#eceee4;color:var(--muted)}.policies td{padding:12px 14px;border-top:1px solid var(--rule)}.policies td:not(:first-child){font-family:var(--mono);font-size:11px}.policies tr.highlight td{background:#faf0e5}.table-wrap{overflow:auto}.two-col{display:grid;grid-template-columns:1fr 1fr;gap:20px}.spec{padding:22px;min-width:0}.spec h3{font-size:20px;letter-spacing:-.6px;font-weight:500;margin:9px 0}.spec p{font-size:12px;color:var(--muted);min-height:36px}.spec-data{display:grid;grid-template-columns:1fr 1fr;gap:14px;padding-top:16px;border-top:1px solid var(--rule)}.spec-data .label{display:block;font:9px var(--mono);letter-spacing:.7px;text-transform:uppercase;color:var(--muted);margin-bottom:4px}.spec-data .data{font:11px var(--mono)}.spec-foot{font-size:11px;color:var(--muted);padding-top:17px}.toolbar{padding:15px;border-bottom:1px solid var(--rule);display:flex;gap:10px;align-items:center;flex-wrap:wrap}.toolbar input{flex:1;min-width:180px}.toolbar input,.toolbar select{background:var(--paper);border:1px solid var(--rule);border-radius:0;padding:10px 12px;font-size:12px;color:var(--ink)}.toolbar label{font:9px var(--mono);color:var(--muted);text-transform:uppercase;letter-spacing:.5px}.record{border-bottom:1px solid var(--rule)}.record:last-child{border:0}.record summary{list-style:none;display:grid;grid-template-columns:85px minmax(0,1fr) 90px 17px;gap:15px;align-items:center;cursor:pointer;padding:15px 18px}.record summary::-webkit-details-marker{display:none}.record summary:hover{background:#f6f5ec}.record .split{font:9px var(--mono);text-transform:uppercase;color:var(--muted)}.record .summary-text{font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.record .choice{font:10px var(--mono);text-align:right}.record .plus{font-size:18px;color:var(--accent)}.record[open] .plus{transform:rotate(45deg)}.record-body{padding:0 18px 18px 118px}.record-body pre{white-space:pre-wrap;overflow-wrap:anywhere;font:11px/1.7 var(--mono);background:var(--paper);padding:15px;margin:10px 0}.record-body .outcomes{display:flex;gap:20px;font:11px var(--mono)}.record-count{font:10px var(--mono);color:var(--muted);padding:13px 18px;border-top:1px solid var(--rule)}.empty{padding:25px;color:var(--muted);font-size:13px}.empty code,.code{font:11px var(--mono);background:var(--paper);padding:3px 5px;color:var(--ink)}.boundary{display:flex;gap:17px;padding:19px 22px;background:#e6e9de;border:1px solid #ccd2c0;margin-top:20px}.boundary .icon{font:18px var(--mono);color:var(--green)}.boundary p{font-size:12px;margin:0;color:#4c5946}.boundary strong{display:block;color:var(--ink);margin-bottom:3px}.deploy-layout>div{min-width:0}.history-row{overflow-wrap:anywhere}.deploy-layout{display:grid;grid-template-columns:1fr 1fr}.deploy-layout>div{padding:22px}.deploy-layout>div:first-child{border-right:1px solid var(--rule)}.deploy-title{font-size:15px;margin:0 0 12px;font-weight:500}.history-row{padding:9px 0;border-bottom:1px solid var(--rule);font:11px/1.7 var(--mono)}.history-row:last-child{border:0}.footer{display:flex;justify-content:space-between;gap:20px;border-top:1px solid var(--rule);padding-top:20px;font:9px/1.7 var(--mono);color:var(--muted);text-transform:uppercase;letter-spacing:.5px}.skip{position:absolute;top:-80px;left:20px;background:var(--ink);color:white;padding:12px;z-index:10}.skip:focus{top:15px}[hidden]{display:none!important}@media(min-width:1600px){.main{padding-left:65px;padding-right:65px}}@media(max-width:1100px){.shell{grid-template-columns:185px 1fr}.rail{padding:25px 18px}.logo{font-size:14px}.main{padding:25px}.hero{grid-template-columns:1fr 220px;gap:20px}.comparison{grid-template-columns:1fr}.chart-area{border-right:0;border-bottom:1px solid var(--rule)}.evidence-aside{padding:20px}.metrics .metric{margin-right:12px}.metric .value{font-size:28px}.stage{padding:12px 7px}.stage-name{font-size:9px}}@media(max-width:760px){.shell{display:block}.rail{position:static;height:auto;padding:18px 20px;border-right:0;border-bottom:1px solid var(--rule);display:block}.rail .edition{margin:6px 0 0}.rail nav{display:flex;gap:18px;margin-top:15px;overflow:auto}.rail nav a{font-size:11px;white-space:nowrap;padding:4px 0}.rail nav span,.rail-bottom{display:none}.main{padding:20px}.topline{font-size:8px;gap:10px}.hero{grid-template-columns:1fr;padding:27px 0}h1{font-size:46px}.status-card{padding:16px;max-width:none}.status-card h2{font-size:22px;margin:7px 0}.pipeline{overflow:auto;grid-template-columns:repeat(7,minmax(80px,1fr))}.metrics{grid-template-columns:1fr 1fr}.metric{margin:0;padding:15px 10px}.metric:nth-child(2){border-right:0}.metric:nth-child(-n+2){border-bottom:1px solid var(--rule)}.two-col{grid-template-columns:1fr}.section-head{align-items:start}.section-head h2{font-size:20px}.section-head .sub{font-size:9px;text-align:right;max-width:130px}.chart-area{padding:16px}.chart-row{grid-template-columns:105px minmax(30px,1fr) 60px;gap:8px}.chart-name{font-size:10px}.chart-value{font-size:10px}.record summary{grid-template-columns:55px minmax(0,1fr) 48px 10px;gap:9px;padding:13px 12px}.record-body{padding:0 12px 14px}.record .split{font-size:8px}.record .choice{font-size:9px}.deploy-layout>div{min-width:0}.history-row{overflow-wrap:anywhere}.deploy-layout{grid-template-columns:1fr}.deploy-layout>div:first-child{border-right:0;border-bottom:1px solid var(--rule)}.footer{flex-direction:column;gap:8px}.boundary{padding:16px}.policies th,.policies td{padding:10px}.toolbar input{min-width:160px}.spec{padding:18px}}@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
.native-table-wrap{max-width:100%;border-top:1px solid var(--rule);border-bottom:1px solid var(--rule)}.native-policies{min-width:1120px}.native-policies caption{text-align:left;padding:12px 14px;font-size:12px;color:var(--muted)}.native-policies th,.native-policies td{vertical-align:top}.native-policies th:first-child,.native-policies td:first-child{min-width:155px}.native-notes p,.native-note{font-size:12px;color:var(--muted);max-width:100ch}.native-notes p:last-child{margin-bottom:0}
</style></head><body><a class="skip" href="#main">Skip to evidence</a><div class="shell">
<aside class="rail"><a class="logo" href="#overview" aria-label="ReflexFoundry Lab home"><svg class="mark" viewBox="0 0 32 36" fill="none" aria-hidden="true"><path d="M4 3H27L21 14H12L7 23H20L14 33H3L11 18H3L11 3" stroke="#ce4c22" stroke-width="2.5" stroke-linejoin="miter"/></svg>REFLEXFOUNDRY</a><p class="edition">LAB / EVIDENCE WORKSPACE</p><nav aria-label="Evidence sections"><a href="#overview"><span>01</span>Overview</a><a href="#comparison"><span>02</span>Policy comparison</a><a href="#native-comparison" id="native-nav" hidden><span>02A</span>Native comparison</a><a href="#decisions"><span>03</span>Decision catalog</a><a href="#records"><span>04</span>Training & evidence</a><a href="#deployment"><span>05</span>Deployment</a></nav><div class="rail-bottom"><span class="dot"></span>LOCAL SNAPSHOT<br>NO TELEMETRY · NO API CALLS<br>READ-ONLY LABORATORY</div></aside>
<main class="main" id="main"><div class="topline"><span>Decision compilation <b>/</b> evidence before delegation</span><span id="workspace-state">Awaiting local evidence</span></div>
<section id="overview"><div class="hero"><div><div class="eyebrow">ReflexFoundry / Experiment console</div><h1>Fast decisions.<br><em>Earned</em> trust.</h1><p class="intro">Find repeated decisions. Train a local reflex. Keep it only when independent task outcomes justify the change.</p></div><div class="status-card"><div class="label">DEPLOYMENT GATE</div><h2 id="gate-heading">Evidence pending</h2><p id="gate-copy">Run an evaluation to establish whether this policy should be used.</p></div></div><div class="pipeline" id="pipeline" aria-label="Decision policy lifecycle"></div><div class="metrics" id="metrics"></div></section>
<section class="section" id="comparison"><div class="section-head"><h2><span>02</span>Make the comparison count.</h2><div class="sub">HELD-OUT OUTCOMES / ACCOUNTED TIME</div></div><div class="panel comparison"><div class="chart-area"><p class="chart-caption">Accounted decision duration · lower is faster</p><div id="chart"></div><div class="chart-key"><span><i class="key-box"></i>Original workflow</span><span><i class="key-box" style="background:var(--accent)"></i>Selective policy</span></div><p class="chart-note" id="chart-note">No executed evaluation is loaded. Timing bars appear only when measured evidence is available.</p></div><aside class="evidence-aside"><div class="eyebrow">The promotion verdict</div><h3 id="verdict-heading">Measure before using.</h3><p id="scope-note">Local inference is useful only if the complete workflow benefits.</p><div id="gate-reasons"></div></aside></div><div class="panel table-wrap" style="margin-top:15px"><table class="policies"><caption class="skip">Held-out policy comparison</caption><thead><tr><th>Policy</th><th>Tasks</th><th>Outcome success</th><th>Mean time</th><th>Fallback</th></tr></thead><tbody id="policy-table"></tbody></table></div></section>
<section class="section" id="native-comparison" hidden><div class="section-head"><h2><span>02A</span>Real coding workflows, measured.</h2><div class="sub">NATIVE AGENT / INDEPENDENT CHECKS</div></div><div class="panel"><div class="panel-inner"><span class="badge warn" id="native-status"></span><p id="native-summary"></p><p class="native-note" id="native-inference"></p></div><div class="table-wrap native-table-wrap" role="region" aria-label="Native agent comparison table" tabindex="0"><table class="policies native-policies"><caption>Observed native calls. Means use protocol-valid observations only.</caption><thead><tr><th>Arm</th><th>Complete / planned</th><th>Protocol valid</th><th>Protocol failed</th><th>Independent success</th><th>CLI mean (s)</th><th>Pipeline mean (s)</th><th>Input mean</th><th>Cached subset mean</th><th>Output mean</th></tr></thead><tbody id="native-table"></tbody></table></div><div class="panel-inner"><h3 class="deploy-title">Matched against the original agent</h3><p class="native-note">Candidate minus original for the same task and repetition. Each pair requires two protocol-valid observations. Shared baselines and correlated repeats remain explicit.</p></div><div class="table-wrap native-table-wrap" role="region" aria-label="Matched native comparisons" tabindex="0"><table class="policies"><thead><tr><th>Arm</th><th>Valid pairs / planned</th><th>CLI change (s)</th><th>Pipeline change (s)</th><th>Input-token change</th><th>Success delta sum</th></tr></thead><tbody id="native-pairs"></tbody></table></div><div class="panel-inner native-notes"><p>CLI time includes native process startup and the actual agent workflow. Pipeline time also includes the independent focused, full-suite and public-contract checks. Readiness hashing and the subsequent postcondition audit are separate. These are full native measurements, separate from retrospective decision-stage accounting. Arm means can have unequal task composition; use matched deltas when comparing arms.</p><p>Independent post-run checks are directly observed. Agent-side internal check execution and ordering are agent-reported. Independent success counts include completed observations with an available checked outcome; protocol failures remain visible and contribute no timing or token mean.</p><p>Only two repository groups, with correlated repeats and shared original-agent baselines. Host load and caches are uncontrolled. These descriptive results establish no causal superiority or currency, energy or subscription-allowance savings. Cached input tokens are included within input tokens and are never added to them.</p><p>This read-only comparison does not change policy eligibility or deployment. Missing and protocol-failed comparisons yield no paired estimate.</p></div></div></section>
<section class="section" id="decisions"><div class="section-head"><h2><span>03</span>Small decisions. Explicit boundaries.</h2><div class="sub">TYPED / BOUNDED / REVERSIBLE</div></div><div class="two-col" id="specs"></div><div class="boundary"><span class="icon" aria-hidden="true">↳</span><p><strong>Agent authority stays with the agent.</strong>Reflexes provide bounded advice. Permissions, destructive actions, credentials, and security approvals never depend on a learned model as their sole authority.</p></div></section>
<section class="section" id="records"><div class="section-head"><h2><span>04</span>Open the evidence.</h2><div class="sub" id="record-total">CONSENTED DECISION RECORDS</div></div><div class="panel"><div class="toolbar"><label for="record-search">Find</label><input id="record-search" type="search" placeholder="Search summaries, choices, or record IDs" aria-label="Search decision records"><label for="split-filter">Split</label><select id="split-filter"><option value="all">All splits</option><option>train</option><option>calibration</option><option>promotion</option><option>test</option><option>unassigned</option></select></div><div id="record-list"></div><div class="record-count" id="record-count" aria-live="polite"></div></div></section>
<section class="section" id="deployment"><div class="section-head"><h2><span>05</span>Keep a way back.</h2><div class="sub">SHADOW / OPT-IN / ROLLBACK</div></div><div class="panel deploy-layout"><div><div class="eyebrow">Current policy</div><h3 class="deploy-title" id="deployment-state">No deployment loaded</h3><p class="fine" id="deployment-detail">Shadow mode records suggestions without changing the original workflow.</p><div id="deployment-badges"></div></div><div><div class="eyebrow">Version & rollback history</div><div id="history"><p class="fine">No history in this snapshot.</p></div></div></div></section>
<footer class="footer"><span>ReflexFoundry Lab · teach agents which decisions can become reflexes.</span><span>Static snapshot · refresh by rebuilding the Lab</span></footer></main></div>
<script type="application/json" id="reflex-data">__REFLEX_DATA__</script>
<script>
'use strict';
const data=JSON.parse(document.getElementById('reflex-data').textContent);
const $=id=>document.getElementById(id), records=data.records||[], ev=data.evaluation||{}, dep=data.deployment||{};
const finite=v=>typeof v==='number'&&Number.isFinite(v), num=v=>finite(v)?v.toLocaleString(undefined,{maximumFractionDigits:1}):'—', pct=v=>finite(v)?(v*100).toFixed(1)+'%':'—';
const element=(tag,cls,text)=>{const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=String(text);return node};
const add=(parent,tag,cls,text)=>{const n=element(tag,cls,text);parent.append(n);return n};
const policies=ev.policies||(ev.test||{}).policies||[], test=ev.test||{}, hasEval=policies.length>0;
const names={'original-full':'Original · full suite','no-delegation':'Original · full suite','deterministic-heuristic':'Simple heuristic','always-focused':'Always focused','original-search':'Original · repository search','always-symbol':'Always symbol lookup','trained-always':'Trained · always delegate','ordinary-laya':'Ordinary Laya','selective':'Trained · selective'};
const selective=policies.find(p=>p.name==='selective'), original=policies.find(p=>['original-full','original-search','no-delegation'].includes(p.name));
$('workspace-state').textContent=hasEval?'Evaluation snapshot':records.length?'Observation snapshot':data.native?'Native comparison snapshot':'Empty workspace';
$('gate-heading').textContent=hasEval?(ev.deployment_allowed?'Eligible for opt-in':'Deployment withheld'):'Evidence pending';
$('gate-copy').textContent=hasEval?(ev.deployment_allowed?'The saved evaluation passed its promotion gates. Deployment still requires explicit opt-in.':'The saved evaluation did not support deployment. The original workflow remains the fallback.'):'Observe decisions and evaluate a candidate to establish whether it should be used.';
const steps=['Observe','Discover','Train','Evaluate','Shadow','Deploy','Monitor'];
steps.forEach((name,i)=>{const complete=i<2&&records.length||i<4&&hasEval;const current=i===3&&hasEval||i===0&&!records.length||i===1&&records.length&&!hasEval;const stage=add($('pipeline'),'div','stage'+(complete?' ready':'')+(current?' current':''));add(stage,'span','stage-number','0'+(i+1));add(stage,'span','stage-name',name)});
function metric(value,unit,label,note){const n=add($('metrics'),'div','metric'), v=add(n,'span','value',value);if(unit)add(v,'small','', ' '+unit);add(n,'span','caption',label);add(n,'div','note',note)}
metric(num(records.length),'','Observed decisions','Only records in this workspace');
metric(hasEval&&selective?pct(selective.success_rate):'—','','Held-out outcome success',hasEval?'Selective policy, locked test':'Awaiting independent outcomes');
metric(hasEval&&selective?num(selective.mean_ms):'—','ms','Mean accounted decision time','Includes recorded model startup');
metric(hasEval&&selective?pct(selective.fallback_rate):'—','','Fallback rate','Original workflow on abstention');
if(hasEval){const max=Math.max(1,...policies.map(p=>finite(p.mean_ms)?p.mean_ms:0));policies.forEach(p=>{const row=add($('chart'),'div','chart-row'+(p.name==='selective'?' selective':'')+(['original-full','original-search','no-delegation'].includes(p.name)?' original':''));add(row,'span','chart-name',names[p.name]||p.name);const track=add(row,'div','chart-track');track.setAttribute('role','img');track.setAttribute('aria-label',(names[p.name]||p.name)+': '+num(p.mean_ms)+' milliseconds');const bar=add(track,'div','chart-bar');bar.style.width=(Math.max(0,finite(p.mean_ms)?p.mean_ms:0)/max*100)+'%';add(row,'span','chart-value',num(p.mean_ms)+' ms')});$('chart-note').textContent='Recorded action time plus measured model overhead. Excludes Python/CLI startup and full agent time. '+(ev.statistics||'Compare correctness alongside time.');
$('verdict-heading').textContent=ev.deployment_allowed?'Evidence supports bounded opt-in.':'A faster model must earn its place.';$('scope-note').textContent=ev.scope||'Measured outcomes apply only to the evaluated workload.';(ev.reasons||[]).forEach((reason,i)=>{const n=add($('gate-reasons'),'div','reason');add(n,'i','',String(i+1).padStart(2,'0'));add(n,'span','',reason)});if(ev.deployment_allowed)add($('gate-reasons'),'p','fine','Promotion passed. Confirm the policy version and deployment limits before opting in.');
policies.forEach(p=>{const tr=add($('policy-table'),'tr',p.name==='selective'?'highlight':'');[(names[p.name]||p.name),num(p.n),pct(p.success_rate),num(p.mean_ms)+' ms',pct(p.fallback_rate)].forEach(v=>add(tr,'td','',v))});
}else{add($('chart'),'div','empty','No timing measurements yet.');const tr=add($('policy-table'),'tr','');const td=add(tr,'td','empty','Run reflex evaluate after training to compare outcomes and complete workflow costs.');td.colSpan=5;}
if(data.native){const n=data.native,nativeNames={'original-agent':'Original agent','deterministic-heuristic':'Deterministic heuristic','ordinary-laya':'Ordinary Laya','trained-always':'Trained always','selective-shadow':'Selective shadow'};
if(!hasEval&&!records.length){$('comparison').hidden=true;$('pipeline').hidden=true;document.querySelector('.metrics').hidden=true;document.querySelector('.rail nav a[href="#comparison"]').hidden=true;$('gate-heading').textContent='No deployment approval';$('gate-copy').textContent='Native comparisons do not establish policy eligibility. Evaluation and verified shadow evidence are still required.';document.querySelector('.intro').textContent='Compare real coding outcomes, native process time and reported tokens. Failed and unattempted observations stay visible.';}
$('native-comparison').hidden=false;$('native-nav').hidden=false;
$('native-status').textContent=n.complete?'Complete descriptive comparison':'Partial comparison: incomplete or protocol-failed';
$('native-status').className='badge'+(n.complete?' neutral':' warn');
$('native-summary').textContent=num(n.completed)+' / '+num(n.planned)+' observations complete; '+num(n.protocol_valid)+' protocol-valid; '+num(n.protocol_failed)+' protocol-failed; '+num(n.planned-n.completed)+' without a result.';
$('native-inference').textContent=num(n.model_inference_observations)+' protocol-valid local model inference observations · '+num(n.repository_groups)+' repository groups · all five arms retained.';
n.arms.forEach(arm=>{const m=arm.means,tr=add($('native-table'),'tr',arm.protocol_failed?'highlight':'');const values=[nativeNames[arm.arm],num(arm.completed)+' / '+num(arm.planned),num(arm.protocol_valid),num(arm.protocol_failed),num(arm.independent_successes)+' / '+num(arm.independent_checked)+' checked',finite(m.cli_wall_ms)?num(m.cli_wall_ms/1000):'Unavailable',finite(m.pipeline_wall_ms)?num(m.pipeline_wall_ms/1000):'Unavailable',num(m.input_tokens),num(m.cached_input_tokens),num(m.output_tokens)];values.forEach(value=>add(tr,'td','',value));});}
if(data.native){const signed=value=>finite(value)?(value>0?'+':'')+num(value):'Unavailable';const labels={'deterministic-heuristic':'Deterministic heuristic','ordinary-laya':'Ordinary Laya','trained-always':'Trained always','selective-shadow':'Selective shadow'};data.native.pairs.forEach(pair=>{const tr=add($('native-pairs'),'tr','');[labels[pair.arm],num(pair.n)+' / '+num(pair.planned),signed(finite(pair.means.cli_wall_ms)?pair.means.cli_wall_ms/1000:null),signed(finite(pair.means.pipeline_wall_ms)?pair.means.pipeline_wall_ms/1000:null),signed(pair.means.input_tokens),pair.n?signed(pair.success_delta):'Unavailable'].forEach(value=>add(tr,'td','',value));});}
(data.specs||[]).forEach((spec,i)=>{const n=add($('specs'),'article','panel spec');const discovery=(data.discovery||[]).find(d=>d.spec===spec.id);add(n,'span','badge'+(!discovery?' neutral':''),discovery?discovery.status:'Awaiting observations');add(n,'h3','',spec.id==='test-scope-v1'?'Choose the test scope':'Prioritize source retrieval');add(n,'p','',spec.purpose);const grid=add(n,'div','spec-data');[['Decision spec',spec.id],['Candidate choices',(spec.choices||[]).join(' / ')],['Fallback',spec.fallback],['Inference budget',num(spec.budget_ms)+' ms']].forEach(([label,value])=>{const item=add(grid,'div','');add(item,'span','label',label);add(item,'span','data',value)});add(n,'div','spec-foot',discovery?num(discovery.records)+' observations · '+num(discovery.repositories)+' repository groups · '+num(discovery.outcome_records)+' with outcome evidence':i===1?'Typed retrieval specification; independent held-out evidence is required before deployment.':'Record explicit authorized choices to discover repeated opportunities.');});
$('record-total').textContent=num(records.length)+' LOCAL DECISION RECORDS';
function renderRecords(){const query=$('record-search').value.toLowerCase().trim(),split=$('split-filter').value;const matching=records.filter(r=>(split==='all'||r.split===split)&&(!query||[r.id,r.spec,r.selected,r.inputs?.summary,JSON.stringify(r.inputs?.changed_files||[])].join(' ').toLowerCase().includes(query)));$('record-list').replaceChildren();matching.slice(0,100).forEach(r=>{const d=add($('record-list'),'details','record'),s=add(d,'summary','');add(s,'span','split',r.split);add(s,'span','summary-text',r.inputs?.summary||r.id);add(s,'span','choice',r.selected);add(s,'span','plus','+');const body=add(d,'div','record-body');add(body,'div','fine',r.id+' · '+r.spec+' · '+r.source);add(body,'pre','',JSON.stringify(r.inputs,null,2));const outcomes=add(body,'div','outcomes');Object.entries(r.outcomes||{}).forEach(([choice,o])=>add(outcomes,'span','',choice+': '+(o.success?'correct outcome':'incorrect outcome')+' / '+num(o.duration_ms)+' ms'));});if(!matching.length)add($('record-list'),'div','empty',records.length?'No records match this filter.':'No records yet. Start with reflex observe and explicitly consent to the decision data you record.');$('record-count').textContent=matching.length>100?'Showing the first 100 of '+num(matching.length)+' matches. Narrow the search or split filter.':num(matching.length)+' matching records · expand a row to inspect inputs and outcomes.';}
$('record-search').addEventListener('input',renderRecords);$('split-filter').addEventListener('change',renderRecords);renderRecords();
const state=dep.mode||dep.status||dep.state;
if(state){$('deployment-state').textContent=String(state);const details=[];for(const key of ['policy_version','version','spec','model_digest','threshold','max_decisions','reason'])if(dep[key]!==undefined)details.push(key+': '+String(dep[key]));$('deployment-detail').textContent=details.join('\n')||'Inspect the saved deployment record for operational limits.';add($('deployment-badges'),'span','badge'+(state==='active'?'':' neutral'),String(state));}
const history=dep.history||dep.rollback_history||[];if(Array.isArray(history)&&history.length){$('history').replaceChildren();history.slice(-10).reverse().forEach(item=>add($('history'),'div','history-row',typeof item==='string'?item:JSON.stringify(item)));}
</script></body></html>'''
