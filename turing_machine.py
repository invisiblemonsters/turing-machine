#!/usr/bin/env python3
"""A tiny deterministic Turing machine simulator.

Machines are plain JSON files:

    {
      "name": "binary-increment",
      "blank": "_",
      "start": "q0",
      "halt": ["halt"],
      "transitions": [
        {"state": "q0", "read": "1", "write": "1", "move": "R", "next": "q0"},
        ...
      ]
    }

Run one with:

    python turing_machine.py machines/binary-increment.json --input 1011
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Dict, Iterable, List, Optional, Tuple

MOVES = ("L", "R", "N")


class MachineError(ValueError):
    """Raised when a machine definition is malformed."""


class StepLimitExceeded(RuntimeError):
    """Raised when a machine does not halt within the allowed number of steps."""

    def __init__(self, steps: int, state: str):
        super().__init__(f"did not halt within {steps} steps (state={state})")
        self.steps = steps
        self.state = state


def load_machine(spec: dict) -> "TuringMachine":
    """Build a TuringMachine from a parsed JSON spec, validating it first."""
    if not isinstance(spec, dict):
        raise MachineError("machine spec must be a JSON object")

    name = spec.get("name", "unnamed")
    blank = spec.get("blank", "_")
    start = spec.get("start")
    halt = spec.get("halt")
    raw_transitions = spec.get("transitions")

    if not isinstance(blank, str) or len(blank) != 1:
        raise MachineError("blank must be a single character")
    if not isinstance(start, str) or not start:
        raise MachineError("start must be a non-empty string")
    if isinstance(halt, str):
        halt = [halt]
    if not isinstance(halt, list) or not halt:
        raise MachineError("halt must be a state name or a non-empty list of them")
    if not all(isinstance(s, str) and s for s in halt):
        raise MachineError("halt states must be non-empty strings")
    if not isinstance(raw_transitions, list) or not raw_transitions:
        raise MachineError("transitions must be a non-empty list")

    transitions: Dict[Tuple[str, str], Tuple[str, str, str]] = {}
    for index, rule in enumerate(raw_transitions):
        if not isinstance(rule, dict):
            raise MachineError(f"transition #{index} must be an object")
        try:
            state = rule["state"]
            read = rule["read"]
            write = rule["write"]
            move = rule["move"]
            nxt = rule["next"]
        except KeyError as exc:
            raise MachineError(f"transition #{index} is missing key {exc.args[0]!r}") from None

        for label, value in (("state", state), ("next", nxt)):
            if not isinstance(value, str) or not value:
                raise MachineError(f"transition #{index}: {label} must be a non-empty string")
        for label, value in (("read", read), ("write", write)):
            if not isinstance(value, str) or len(value) != 1:
                raise MachineError(f"transition #{index}: {label} must be a single character")
        if move not in MOVES:
            raise MachineError(f"transition #{index}: move must be one of {MOVES}")

        key = (state, read)
        if key in transitions:
            raise MachineError(f"duplicate transition for state {state!r} on {read!r}")
        transitions[key] = (write, move, nxt)

    return TuringMachine(
        transitions=transitions,
        blank=blank,
        start=start,
        halt=tuple(halt),
        name=name,
    )


def load_machine_file(path: str) -> "TuringMachine":
    with open(path, "r", encoding="utf-8") as handle:
        try:
            spec = json.load(handle)
        except json.JSONDecodeError as exc:
            raise MachineError(f"{path}: invalid JSON ({exc})") from None
    return load_machine(spec)


class TuringMachine:
    """A single-tape deterministic Turing machine with an infinite blank tape."""

    def __init__(
        self,
        transitions: Dict[Tuple[str, str], Tuple[str, str, str]],
        blank: str = "_",
        start: str = "q0",
        halt: Iterable[str] = ("halt",),
        name: str = "unnamed",
    ):
        self.transitions = dict(transitions)
        self.blank = blank
        self.start = start
        self.halt = tuple(halt)
        self.name = name

        self.state = start
        self.head = 0
        self.cells: Dict[int, str] = {}
        self.steps = 0
        self.halted = False

    # ---- tape -----------------------------------------------------------
    def read(self) -> str:
        return self.cells.get(self.head, self.blank)

    def write(self, symbol: str) -> None:
        if len(symbol) != 1:
            raise MachineError("tape symbols are single characters")
        if symbol == self.blank:
            self.cells.pop(self.head, None)
        else:
            self.cells[self.head] = symbol

    def move_head(self, direction: str) -> None:
        if direction == "L":
            self.head -= 1
        elif direction == "R":
            self.head += 1
        elif direction == "N":
            pass
        else:
            raise MachineError(f"invalid move {direction!r}")

    def tape(self) -> str:
        """Tape contents trimmed of leading/trailing blanks ("" when empty)."""
        if not self.cells:
            return ""
        low = min(self.cells)
        high = max(self.cells)
        return "".join(self.cells.get(i, self.blank) for i in range(low, high + 1))

    def tape_bounds(self) -> Tuple[int, int]:
        if not self.cells:
            return (self.head, self.head)
        return (min(self.cells), max(self.cells))

    # ---- execution ------------------------------------------------------
    def load_input(self, text: str) -> None:
        """Reset the machine and write `text` onto the tape starting at cell 0."""
        if self.blank in text:
            raise MachineError(f"input must not contain the blank symbol {self.blank!r}")
        self.state = self.start
        self.head = 0
        self.cells = {i: ch for i, ch in enumerate(text)}
        self.steps = 0
        self.halted = False

    def step(self) -> bool:
        """Execute one transition. Returns True if the machine is still running."""
        if self.halted:
            return False
        if self.state in self.halt:
            self.halted = True
            return False

        rule = self.transitions.get((self.state, self.read()))
        if rule is None:
            # No rule for this (state, symbol): the machine hangs, like a real TM would.
            self.halted = True
            return False

        write, direction, nxt = rule
        self.write(write)
        self.move_head(direction)
        self.state = nxt
        self.steps += 1

        if self.state in self.halt:
            self.halted = True
            return False
        return True

    def run(self, max_steps: int = 100_000) -> "TuringMachine":
        if max_steps < 0:
            raise ValueError("max_steps must be non-negative")
        while self.steps < max_steps:
            if not self.step():
                return self
        if not self.halted:
            raise StepLimitExceeded(max_steps, self.state)
        return self

    def run_input(self, text: str, max_steps: int = 100_000) -> "TuringMachine":
        self.load_input(text)
        return self.run(max_steps=max_steps)

    # ---- presentation ---------------------------------------------------
    def render(self) -> str:
        low, high = self.tape_bounds()
        low, high = min(low, self.head), max(high, self.head)
        symbols: List[str] = [self.cells.get(i, self.blank) for i in range(low, high + 1)]
        pointer = [" "] * len(symbols)
        pointer[self.head - low] = "^"
        return "\n".join(
            [
                f"state: {self.state}",
                "tape:  " + "".join(symbols),
                "head:  " + "".join(pointer),
            ]
        )

    def summary(self) -> str:
        status = "halted" if self.halted else "running"
        return f"{status} in {self.steps} steps at state {self.state!r}; tape={self.tape()!r}"


def write_out(text: str) -> None:
    """Write ASCII output byte-exactly (text-mode stdout would rewrite \\n on Windows)."""
    sys.stdout.buffer.write((text + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run a deterministic Turing machine from a JSON file.")
    parser.add_argument("machine", help="path to a machine JSON file")
    parser.add_argument("--input", default="", help="initial tape contents (default: empty)")
    parser.add_argument("--max-steps", type=int, default=100_000, help="step limit before giving up")
    parser.add_argument("--trace", action="store_true", help="print every step")
    args = parser.parse_args(argv)

    try:
        machine = load_machine_file(args.machine)
    except (OSError, MachineError) as exc:
        write_out(f"error: {exc}")
        return 2

    machine.load_input(args.input)
    try:
        while True:
            if args.trace:
                write_out(f"step {machine.steps:>4}: {machine.state}  tape={machine.tape()!r} head={machine.head}")
            if not machine.step():
                break
            if machine.steps >= args.max_steps:
                raise StepLimitExceeded(args.max_steps, machine.state)
    except StepLimitExceeded as exc:
        write_out(f"error: {exc}")
        write_out(machine.render())
        return 1

    write_out(f"machine: {machine.name}")
    write_out(f"steps:   {machine.steps}")
    write_out(f"final:   {machine.state}")
    write_out(f"tape:    {machine.tape()}")
    if args.trace:
        write_out(machine.render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
