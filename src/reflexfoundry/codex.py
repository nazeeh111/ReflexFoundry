"""Privacy-minimizing summaries of explicitly supplied Codex JSON events.

Actions are observations, never training labels. Shell commands are parsed
statically: nothing is executed, expanded, or retained beyond allowlisted names.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ALLOWED_COMMANDS = frozenset({"pytest", "python", "python3", "rg", "git", "npm", "cargo", "go"})
_SHELLS = frozenset({"sh", "bash", "zsh"})
_CONTROL = frozenset({"if", "then", "else", "elif", "fi", "for", "while", "until", "do", "done",
                      "case", "esac", "function", "select", "time", "!"})
_MAX_COMMAND_BYTES = 65536
_MAX_WRAPPERS = 3


def _shell_tokens(command: str) -> list[tuple[str, str]] | None:
    """Keep quoted punctuation inside words; reject expansion and shell programs.

    This intentionally recognizes less than a shell grammar. In particular,
    heredocs, substitutions, grouping and control flow are not telemetry sources.
    """
    tokens: list[tuple[str, str]] = []
    word: list[str] = []
    started = False
    index = 0

    def flush() -> None:
        nonlocal started
        if started:
            tokens.append(("word", "".join(word)))
            word.clear()
            started = False

    while index < len(command):
        char = command[index]
        if char in " \t\r":
            flush()
            index += 1
        elif char == "\n":
            flush()
            if tokens and tokens[-1][0] != "separator":
                tokens.append(("separator", ";"))
            index += 1
        elif char == "#" and not started:
            end = command.find("\n", index)
            index = len(command) if end < 0 else end
        elif char == "\\":
            if index + 1 == len(command):
                return None
            if command[index + 1] != "\n":
                started = True
                word.append(command[index + 1])
            index += 2
        elif char in "'\"":
            quote = char
            started = True
            index += 1
            while index < len(command) and command[index] != quote:
                char = command[index]
                if quote == '"' and char in "$`":
                    return None
                if quote == '"' and char == "\\" and index + 1 < len(command):
                    following = command[index + 1]
                    if following in '\\"$`\n':
                        if following != "\n":
                            word.append(following)
                        index += 2
                        continue
                word.append(char)
                index += 1
            if index == len(command):
                return None
            index += 1
        elif char in "$`(){}":
            return None
        elif char in ";&|":
            flush()
            operator = char
            if index + 1 < len(command) and command[index + 1] == char:
                operator += char
            if operator in {";;", "&&&", "|||"}:
                return None
            tokens.append(("separator", operator))
            index += len(operator)
        elif char in "<>":
            flush()
            operator = char
            if index + 1 < len(command) and command[index + 1] in "<>&|":
                operator += command[index + 1]
            if operator.startswith("<<"):
                return None
            tokens.append(("redirect", operator))
            index += len(operator)
        else:
            started = True
            word.append(char)
            index += 1
    flush()
    return tokens


def command_names(command: str) -> list[str]:
    """Extract conservative command-name telemetry, including shell wrappers.

    Supports direct commands and exact ``sh/bash/zsh -c/-lc SCRIPT`` forms,
    nested at most three times, plus unquoted shell list/pipeline operators.
    Ambiguous scripts deliberately undercount. Arguments, outputs and unknown
    binaries are never returned. Version-suffixed Python names are not guessed.
    """
    if not isinstance(command, str):
        raise ValueError("command must be text")
    if len(command.encode("utf-8")) > _MAX_COMMAND_BYTES or "\x00" in command:
        return []

    def parse(source: str, depth: int) -> list[str]:
        tokens = _shell_tokens(source)
        if not tokens:
            return []
        segments: list[list[tuple[str, str]]] = [[]]
        last_operator = ""
        for token in tokens:
            if token[0] == "separator":
                if not segments[-1]:
                    return []
                segments.append([])
                last_operator = token[1]
            else:
                segments[-1].append(token)
        if not segments[-1]:
            if last_operator not in {";", "&"}:
                return []
            segments.pop()
        # Do not treat individual statements inside a control program as actions.
        if any(segment[0][1] in _CONTROL for segment in segments):
            return []
        names: list[str] = []
        for segment in segments:
            if segment[0][0] != "word":
                continue
            name = Path(segment[0][1]).name
            if name in _SHELLS:
                if (depth < _MAX_WRAPPERS and len(segment) == 3
                        and all(token[0] == "word" for token in segment)
                        and segment[1][1] in {"-c", "-lc"}):
                    names.extend(parse(segment[2][1], depth + 1))
            elif name in ALLOWED_COMMANDS:
                names.append(name)
        return names

    return parse(command, 0)


def summarize_events(path: Path, consent: bool = False) -> dict[str, Any]:
    if not consent:
        raise ValueError("event inspection requires explicit consent")
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("event export exceeds 16 MiB")
    counts: dict[str, int] = {}
    total = 0
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            raise ValueError(f"invalid JSON event at line {number}") from None
        if not isinstance(event, dict):
            raise ValueError(f"event at line {number} must be an object")
        if not isinstance(event.get("type"), str):
            raise ValueError(f"event type at line {number} must be text")
        if event["type"] != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            raise ValueError(f"completed item at line {number} must be an object")
        if not isinstance(item.get("type"), str):
            raise ValueError(f"item type at line {number} must be text")
        if item["type"] != "command_execution":
            continue
        command = item.get("command")
        if not isinstance(command, str):
            raise ValueError(f"command at line {number} must be text")
        total += 1
        for name in command_names(command):
            counts[name] = counts.get(name, 0) + 1
    return {"source": "codex-exec-json", "observable_commands": total,
            "allowlisted_command_counts": counts,
            "training_labels": False,
            "note": "Counts identify statically requested commands, not verified execution of conditional branches. Ambiguous shell syntax is uncounted. Add typed decisions and independent outcomes separately."}
