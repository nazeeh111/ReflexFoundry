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


def token_usage(value: Any) -> dict[str, int]:
    """Allowlist documented counters, never reasoning text or unknown fields."""
    required = ("input_tokens", "cached_input_tokens", "output_tokens")
    if not isinstance(value, dict) or any(key not in value for key in required):
        raise ValueError("completed turn has incomplete token usage")
    keys = (*required, "reasoning_output_tokens") if "reasoning_output_tokens" in value else required
    if any(isinstance(value[key], bool) or not isinstance(value[key], int)
           or not 0 <= value[key] <= 2**63 - 1 for key in keys):
        raise ValueError("usage counters must be bounded nonnegative integers")
    if value["cached_input_tokens"] > value["input_tokens"]:
        raise ValueError("cached input exceeds total input")
    if value.get("reasoning_output_tokens", 0) > value["output_tokens"]:
        raise ValueError("reasoning output exceeds total output")
    return {key: value[key] for key in keys}


class EventSummary:
    """Incremental numeric summary; no event, argument, or message is retained."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.total = 0
        self.turns = 0
        self.invalid_usage = 0
        self.reasoning_turns = 0
        self.usage = {key: 0 for key in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")}

    def observe(self, event: Any) -> None:
        if not isinstance(event, dict):
            raise ValueError("event must be an object")
        if not isinstance(event.get("type"), str):
            raise ValueError("event type must be text")
        if event["type"] == "turn.completed":
            self.turns += 1
            try:
                usage = token_usage(event.get("usage"))
            except ValueError:
                self.invalid_usage += 1
                return
            self.reasoning_turns += int("reasoning_output_tokens" in usage)
            for key, value in usage.items():
                self.usage[key] += value
            return
        if event["type"] != "item.completed":
            return
        item = event.get("item")
        if not isinstance(item, dict):
            raise ValueError("completed item must be an object")
        if not isinstance(item.get("type"), str):
            raise ValueError("item type must be text")
        if item["type"] != "command_execution":
            return
        command = item.get("command")
        if not isinstance(command, str):
            raise ValueError("command must be text")
        self.total += 1
        for name in command_names(command):
            self.counts[name] = self.counts.get(name, 0) + 1

    def result(self) -> dict[str, Any]:
        usage = None
        if self.turns and not self.invalid_usage:
            usage = {key: value for key, value in self.usage.items()
                     if key != "reasoning_output_tokens" or self.reasoning_turns == self.turns}
        return {"source": "codex-exec-json", "observable_commands": self.total,
            "allowlisted_command_counts": dict(self.counts),
            "completed_turns": self.turns, "invalid_usage_events": self.invalid_usage,
            "token_usage": usage,
            "training_labels": False,
            "note": "Command counts describe statically requested commands, not verified conditional execution. Token counters are unavailable without complete valid turn usage; they do not measure money, energy, or subscription allowance. No reasoning text is retained."}


def summarize_events(path: Path, consent: bool = False) -> dict[str, Any]:
    if not consent:
        raise ValueError("event inspection requires explicit consent")
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("event export exceeds 16 MiB")
    summary = EventSummary()
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            raise ValueError(f"invalid JSON event at line {number}") from None
        try:
            summary.observe(event)
        except ValueError as error:
            message = str(error).replace(" must ", f" at line {number} must ", 1)
            raise ValueError(message) from None
    return summary.result()
