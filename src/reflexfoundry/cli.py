"""A small, local-first CLI. Agent actions and native permissions stay with the agent."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from . import __version__
from .core import (
    SPECS,
    digest,
    discover,
    observe,
    read_json,
    read_records,
    spec_dicts,
    validate_inputs,
    write_json,
)


def _json_object(path: Path) -> dict[str, Any]:
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("input JSON exceeds 1 MiB")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("input JSON must be an object")
    return value


def _append_record(path: Path, record: dict[str, Any]) -> None:
    rows = read_records(path)
    if any(row.get("id") == record["id"] for row in rows):
        raise ValueError("record already observed; use a distinct source decision id")
    path.parent.mkdir(parents=True, exist_ok=True)
    data = "".join(json.dumps(row, sort_keys=True, allow_nan=False) + "\n" for row in [*rows, record])
    if len(data.encode()) > 32 * 1024 * 1024:
        raise ValueError("records exceed 32 MiB; start a new workspace")
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".reflex-records-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="reflex", description="Compile repeated agent decisions into outcome-gated local policies.",
        epilog="Local only. No hidden transcripts, paid APIs, permission decisions, or arbitrary tool execution.",
    )
    root.add_argument("--version", action="version", version=f"ReflexFoundry {__version__}")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("specs", help="inspect typed decisions, choices and conservative fallbacks")

    def workspace(command: argparse.ArgumentParser) -> None:
        command.add_argument("--workspace", type=Path, default=Path(".reflex"),
                             help="local records and evidence directory (default: .reflex)")

    observe_cmd = commands.add_parser("observe", help="ingest one explicitly authorized, privacy-filtered decision")
    observe_cmd.add_argument("input", type=Path, help="JSON with authorized:true, spec, inputs and selected")
    workspace(observe_cmd)
    observe_cmd.add_argument("--consent", action="store_true", help="authorize storage of this decision")
    discover_cmd = commands.add_parser("discover", help="find repeated supported decisions and outcome evidence")
    workspace(discover_cmd)
    benchmark = commands.add_parser("benchmark", help="execute bounded local decision workloads, without APIs")
    benchmark.add_argument("--output", type=Path, required=True, help="fresh benchmark directory")
    benchmark.add_argument("--repeats", type=int, default=3, help="paired timing trials per task (1–20)")
    benchmark.add_argument("--small", action="store_true", help="32-task demonstration; too small for training/promotion")
    benchmark.add_argument("--decision", choices=tuple(SPECS), default="test-scope-v1")
    benchmark.add_argument("--sources", type=Path, help="parent of pinned public checkouts for context retrieval")
    download = commands.add_parser("download", help="download the pinned Apache-2.0 Laya base checkpoint")
    download.add_argument("--output", type=Path, default=Path("models/base"))
    train_cmd = commands.add_parser("train", help="adapt Laya on the training split only (requires train extra)")
    workspace(train_cmd)
    train_cmd.add_argument("--base", type=Path, required=True)
    train_cmd.add_argument("--output", type=Path, required=True, help="fresh policy version directory")
    train_cmd.add_argument("--epochs", type=int, default=4)
    train_cmd.add_argument("--device", default="auto")
    evaluate = commands.add_parser("evaluate", help="calibrate, independently gate and report held-out outcomes")
    workspace(evaluate)
    evaluate.add_argument("--policy", type=Path, required=True)
    evaluate.add_argument("--base", type=Path, help="also measure ordinary unadapted Laya")
    evaluate.add_argument("--backend", choices=("auto", "mlx", "torch"), default="auto")
    materialize = commands.add_parser("materialize", help="reconstruct a trained policy from its safe tensor head")
    materialize.add_argument("--base", type=Path, required=True)
    materialize.add_argument("--head", type=Path, required=True)
    materialize.add_argument("--output", type=Path, required=True)
    events = commands.add_parser("codex-events", help="summarize authorized command events without retaining arguments")
    events.add_argument("input", type=Path)
    events.add_argument("--consent", action="store_true")
    serve = commands.add_parser("serve", help="serve the read-only Lab on local loopback")
    workspace(serve)
    serve.add_argument("--port", type=int, default=8765)
    lab = commands.add_parser("lab", help="render a self-contained local evidence laboratory")
    workspace(lab)
    lab.add_argument("--output", type=Path, default=Path("reflexfoundry-lab.html"))
    for name, help_text in (("shadow", "observe policy proposals while returning the original fallback"),
                            ("deploy", "opt into bounded use only when independent evidence permits")):
        command = commands.add_parser(name, help=help_text)
        workspace(command)
        command.add_argument("--policy", type=Path, required=True)
        command.add_argument("--max-decisions", type=int, default=100)
        command.add_argument("--consent", "--opt-in", action="store_true", help="explicitly authorize this local deployment")
    decide = commands.add_parser("decide", help="return an advisory choice; does not execute the chosen action")
    workspace(decide)
    decide.add_argument("--backend", choices=("auto", "mlx", "torch"), default="auto")
    decide.add_argument("input", type=Path, help="JSON object with spec and inputs")
    outcome = commands.add_parser("outcome", help="record an independently checked deployment outcome")
    workspace(outcome)
    outcome.add_argument("id", help="decision id returned by decide")
    success = outcome.add_mutually_exclusive_group(required=True)
    success.add_argument("--success", action="store_true")
    success.add_argument("--failure", action="store_true")
    outcome.add_argument("--duration-ms", type=float, required=True)
    outcome.add_argument("--consent", action="store_true")
    outcome.add_argument("--candidate-verified", action="store_true", help="independent grader checked the learned candidate itself")
    rollback = commands.add_parser("rollback", help="revert to the original workflow and retain history")
    workspace(rollback)
    return root


def _evaluate(args: argparse.Namespace) -> dict[str, Any]:
    from .evaluation import evaluate, evaluation_spec
    from .model import LocalPolicy, file_hash

    records = read_records(args.workspace / "records.jsonl")
    # Fail before loading a model if the dataset cannot support an evaluation.
    from .core import validate_splits
    validate_splits(records, require_evaluation_outcomes=True)
    if any(sum(row["split"] == split for row in records) < 30
           for split in ("calibration", "promotion", "test")):
        raise ValueError("evaluation needs at least 30 tasks in each calibration/promotion/test split")
    evaluation_spec(records)
    import time

    from .lifecycle import artifact_digest, register
    screening_started = time.perf_counter()
    artifact = artifact_digest(args.policy)
    screening_ms = (time.perf_counter() - screening_started) * 1000
    policy = LocalPolicy(args.policy, backend=args.backend)
    rows = [row for row in records if row["split"] != "train"]
    predictions = {row["id"]: policy.predict(row["spec"], row["inputs"]) for row in rows}
    base_predictions = None
    base_startup = 0.0
    if args.base:
        base = LocalPolicy(args.base, backend=args.backend)
        base_predictions = {row["id"]: base.predict(row["spec"], row["inputs"]) for row in rows}
        base_startup = base.startup_ms
    if artifact_digest(args.policy) != artifact:
        raise ValueError("policy inference files changed during evaluation; rerun on an immutable version")
    model_digest = file_hash(args.policy / "model.safetensors")
    result = evaluate(records, predictions, policy.startup_ms + screening_ms, model_digest,
                      base_predictions, base_startup)
    result["spec_catalog_digest"] = digest([spec.__dict__ for spec in SPECS.values()])
    result["backend"] = policy.backend
    result["artifact_digest"] = artifact
    result["screening_ms"] = screening_ms
    result["cost_note"] = "Retrospective action outcomes plus measured model startup and integrity screening charged per CLI request; not direct timing of every full CLI process."
    write_json(args.workspace / "predictions.json", {
        "model_digest": model_digest, "dataset_digest": digest(records), "backend": policy.backend,
        "startup_ms": policy.startup_ms + screening_ms, "model_startup_ms": policy.startup_ms,
        "screening_ms": screening_ms, "predictions": predictions,
        "base_predictions": base_predictions, "base_startup_ms": base_startup,
    })
    write_json(args.workspace / "evaluation.json", result)
    register(args.workspace, args.policy, result, records)
    return result


def run(args: argparse.Namespace) -> Any:
    if args.command == "specs":
        return spec_dicts()
    if args.command == "observe":
        record = observe(_json_object(args.input), consent=args.consent)
        from .lifecycle import locked
        with locked(args.workspace):
            _append_record(args.workspace / "records.jsonl", record)
        return {"observed": record["id"], "records": str(args.workspace / "records.jsonl")}
    if args.command == "discover":
        return discover(read_records(args.workspace / "records.jsonl"))
    if args.command == "benchmark":
        if args.decision == "context-route-v1":
            if args.small:
                raise ValueError("--small is for generated test fixtures; context retrieval uses pinned public sources")
            if not args.sources:
                raise ValueError("context retrieval requires --sources containing toolz, funcy, blinker and cachetools")
            from .context_benchmark import generate as generate_context
            sources = {name: args.sources / name for name in ("toolz", "funcy", "blinker", "cachetools")}
            rows = generate_context(args.output, sources, repeats=args.repeats)
            return {"decision": args.decision, "records": len(rows), "output": str(args.output)}
        if args.sources:
            raise ValueError("--sources is used only with --decision context-route-v1")
        from .benchmark import generate, summarize
        counts = {key: 8 for key in ("train", "calibration", "promotion", "test")} if args.small else None
        return summarize(generate(args.output, tasks_per_split=counts, repeats=args.repeats))
    if args.command == "download":
        from .model import download
        return {"base": str(download(args.output))}
    if args.command == "train":
        if not 1 <= args.epochs <= 100:
            raise ValueError("epochs must be between 1 and 100")
        from .model import train
        return train(read_records(args.workspace / "records.jsonl"), args.base, args.output,
                     epochs=args.epochs, device=args.device)
    if args.command == "evaluate":
        return _evaluate(args)
    if args.command == "materialize":
        from .model import materialize
        materialize(args.base, args.head, args.output)
        return {"policy": str(args.output)}
    if args.command == "codex-events":
        from .codex import summarize_events
        return summarize_events(args.input, consent=args.consent)
    if args.command == "serve":
        return _serve(args.workspace, args.port)
    if args.command == "lab":
        from .lab import build_lab
        return {"lab": str(build_lab(args.workspace, args.output))}
    from . import lifecycle
    if args.command in {"shadow", "deploy"}:
        policy = read_json(args.workspace / "policy.json")
        if not policy:
            raise ValueError("evaluate and register a policy first")
        if Path(policy["model"]).resolve() != args.policy.resolve():
            raise ValueError("--policy must match the policy registered by evaluate in this workspace")
        return lifecycle.transition(args.workspace, args.command, opt_in=args.consent,
                                    max_decisions=args.max_decisions)
    if args.command == "decide":
        request = _json_object(args.input)
        spec_id = request.get("spec", "")
        inputs = validate_inputs(spec_id, request.get("inputs"))
        return lifecycle.decide(args.workspace, spec_id, inputs, args.backend)
    if args.command == "outcome":
        if not args.consent:
            raise ValueError("outcome recording requires explicit --consent")
        return lifecycle.outcome(args.workspace, args.id, success=args.success,
                                 duration_ms=args.duration_ms, candidate_verified=args.candidate_verified)
    if args.command == "rollback":
        return lifecycle.transition(args.workspace, "rollback")
    raise ValueError("unsupported command")


def _serve(workspace: Path, port: int) -> None:
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import urlsplit

    from .lifecycle import state

    if not 1024 <= port <= 65535:
        raise ValueError("port must be between 1024 and 65535")
    assets = Path(__file__).parent / "lab"
    routes = {"/": ("index.html", "text/html; charset=utf-8"),
              "/style.css": ("style.css", "text/css; charset=utf-8"),
              "/app.js": ("app.js", "text/javascript; charset=utf-8")}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            route = urlsplit(self.path).path
            if route == "/api/state":
                body = json.dumps(state(workspace), allow_nan=False).encode()
                content_type = "application/json; charset=utf-8"
            elif route in routes:
                name, content_type = routes[route]
                body = (assets / name).read_bytes()
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"ReflexFoundry Lab: http://127.0.0.1:{port} (read-only; Ctrl-C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    command_parser = parser()
    args = command_parser.parse_args(argv)
    try:
        result = run(args)
        print(json.dumps(result, indent=2, allow_nan=False))
    except ImportError:
        print("reflex: required optional runtime is unavailable; install .[train] or .[train,apple] for model commands",
              file=sys.stderr)
        return 2
    except (ValueError, OSError, RuntimeError, KeyError, TypeError) as error:
        print(f"reflex: {error}", file=sys.stderr)
        return 2
    return 0
