"""Privacy-minimizing adapter for a user-supplied `codex exec --json` export.

Events reveal actions, not typed decision truth or independent outcomes. This
adapter deliberately does not turn an observed command into a training label.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ALLOWED_COMMANDS = frozenset({"pytest", "python", "python3", "rg", "git", "npm", "cargo", "go"})


def summarize_events(path: Path, consent: bool = False) -> dict[str, Any]:
    if not consent:
        raise ValueError("event inspection requires explicit consent")
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("event export exceeds 16 MiB")
    counts: dict[str, int] = {}
    total = 0
    import shlex
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("type") != "item.completed":
            continue
        item = event.get("item", {})
        if item.get("type") != "command_execution":
            continue
        total += 1
        try:
            parts = shlex.split(item.get("command", ""))
        except ValueError:
            continue
        # Discard all arguments, paths, output, free text, and unknown binaries.
        name = Path(parts[0]).name if parts else ""
        if name in ALLOWED_COMMANDS:
            counts[name] = counts.get(name, 0) + 1
    return {"source": "codex-exec-json", "observable_commands": total,
            "allowlisted_command_counts": counts,
            "training_labels": False, "note": "Actions are observations; add explicit typed decisions and independent outcomes separately."}
