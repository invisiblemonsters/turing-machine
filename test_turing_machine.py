"""Tests for the Turing machine simulator. Run with: python -m unittest -v"""

import itertools
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACHINES = os.path.join(HERE, "machines")

sys.path.insert(0, HERE)

from turing_machine import (  # noqa: E402
    MachineError,
    StepLimitExceeded,
    TuringMachine,
    load_machine,
    load_machine_file,
)


def binary_strings(max_len):
    for length in range(max_len + 1):
        for bits in itertools.product("01", repeat=length):
            yield "".join(bits)


def simple_machine(rules, **kwargs):
    transitions = {(s, r): (w, mv, n) for (s, r, w, mv, n) in rules}
    return TuringMachine(transitions, blank=kwargs.pop("blank", "_"),
                         start=kwargs.pop("start", "q0"), halt=kwargs.pop("halt", ("halt",)))


class TapeTests(unittest.TestCase):
    def test_blank_tape_reads_blank(self):
        machine = simple_machine([])
        self.assertEqual(machine.read(), "_")
        self.assertEqual(machine.tape(), "")

    def test_write_then_move(self):
        machine = simple_machine([])
        machine.write("1")
        machine.move_head("R")
        machine.write("0")
        self.assertEqual(machine.head, 1)
        self.assertEqual(machine.read(), "0")
        machine.move_head("L")
        self.assertEqual(machine.read(), "1")
        machine.move_head("N")
        self.assertEqual(machine.head, 0)

    def test_writing_blank_erases(self):
        machine = simple_machine([])
        machine.write("1")
        machine.write("_")
        self.assertEqual(machine.tape(), "")
        self.assertEqual(machine.cells, {})

    def test_tape_trims_edges_but_keeps_inner_blanks(self):
        machine = simple_machine([])
        machine.cells = {-2: "1", 0: "0", 3: "1"}
        self.assertEqual(machine.tape(), "1_0__1")
        self.assertEqual(machine.tape_bounds(), (-2, 3))

    def test_invalid_move_and_symbol_rejected(self):
        machine = simple_machine([])
        with self.assertRaises(MachineError):
            machine.move_head("U")
        with self.assertRaises(MachineError):
            machine.write("11")

    def test_render_points_at_head(self):
        machine = simple_machine([])
        machine.load_input("101")
        machine.head = 2
        lines = machine.render().splitlines()
        self.assertEqual(lines[1], "tape:  101")
        self.assertEqual(lines[2], "head:    ^")


class StepTests(unittest.TestCase):
    def test_step_halts_in_halt_state(self):
        machine = simple_machine([("q0", "_", "1", "R", "halt")])
        self.assertFalse(machine.step())
        self.assertTrue(machine.halted)
        self.assertEqual(machine.steps, 1)
        self.assertEqual(machine.tape(), "1")

    def test_start_in_halt_state_does_nothing(self):
        machine = simple_machine([], start="halt")
        machine.load_input("1")
        machine.run()
        self.assertEqual(machine.steps, 0)
        self.assertTrue(machine.halted)

    def test_missing_transition_hangs_without_step(self):
        machine = simple_machine([("q0", "1", "1", "R", "halt")])
        machine.load_input("0")
        machine.run()
        self.assertTrue(machine.halted)
        self.assertEqual(machine.steps, 0)
        self.assertEqual(machine.state, "q0")

    def test_step_limit(self):
        looper = simple_machine([("q0", "_", "_", "R", "q0")])
        with self.assertRaises(StepLimitExceeded) as ctx:
            looper.run(max_steps=50)
        self.assertEqual(ctx.exception.steps, 50)
        self.assertEqual(looper.steps, 50)

    def test_zero_step_limit_refuses_to_start(self):
        looper = simple_machine([("q0", "_", "_", "R", "q0")])
        with self.assertRaises(StepLimitExceeded):
            looper.run(max_steps=0)
        self.assertEqual(looper.steps, 0)

    def test_run_input_resets_between_runs(self):
        machine = simple_machine([("q0", "_", "1", "R", "halt")])
        machine.run_input("")
        self.assertEqual(machine.tape(), "1")
        self.assertEqual(machine.steps, 1)
        machine.run_input("11")
        # the rule only matches a blank, so this run halts immediately...
        self.assertEqual(machine.steps, 0)
        self.assertEqual(machine.head, 0)
        # ...and the previous tape must not have survived the reset
        self.assertEqual(machine.tape(), "11")

    def test_input_may_not_contain_blank(self):
        machine = simple_machine([("q0", "_", "1", "R", "halt")])
        with self.assertRaises(MachineError):
            machine.load_input("1_1")


class ValidationTests(unittest.TestCase):
    def base(self):
        return {
            "name": "x",
            "blank": "_",
            "start": "q0",
            "halt": ["halt"],
            "transitions": [
                {"state": "q0", "read": "_", "write": "1", "move": "R", "next": "halt"}
            ],
        }

    def test_valid_spec_builds(self):
        machine = load_machine(self.base())
        self.assertEqual(machine.name, "x")
        self.assertEqual(machine.transitions[("q0", "_")], ("1", "R", "halt"))

    def test_halt_may_be_a_single_string(self):
        spec = self.base()
        spec["halt"] = "done"
        self.assertEqual(load_machine(spec).halt, ("done",))

    def test_rejects_bad_specs(self):
        cases = []
        spec = self.base(); spec["blank"] = "__"; cases.append(spec)
        spec = self.base(); spec["start"] = ""; cases.append(spec)
        spec = self.base(); spec["halt"] = []; cases.append(spec)
        spec = self.base(); spec["transitions"] = []; cases.append(spec)
        spec = self.base(); spec["transitions"][0]["move"] = "X"; cases.append(spec)
        spec = self.base(); spec["transitions"][0]["read"] = "ab"; cases.append(spec)
        spec = self.base(); del spec["transitions"][0]["next"]; cases.append(spec)
        spec = self.base(); spec["transitions"].append(dict(spec["transitions"][0])); cases.append(spec)
        cases.append(["not", "an", "object"])

        for spec in cases:
            with self.subTest(spec=spec):
                with self.assertRaises(MachineError):
                    load_machine(spec)


class ShippedMachineTests(unittest.TestCase):
    def load(self, name):
        return load_machine_file(os.path.join(MACHINES, name + ".json"))

    def test_all_machines_parse(self):
        names = sorted(f[:-5] for f in os.listdir(MACHINES) if f.endswith(".json"))
        self.assertEqual(names, ["binary-increment", "busy-beaver-3", "palindrome-binary"])
        for name in names:
            with self.subTest(name=name):
                self.assertTrue(self.load(name).name)

    def test_binary_increment_sweep(self):
        machine = self.load("binary-increment")
        for n in range(2048):
            with self.subTest(n=n):
                machine.run_input(format(n, "b"), max_steps=10_000)
                self.assertEqual(machine.state, "halt")
                self.assertEqual(machine.tape(), format(n + 1, "b"))

    def test_binary_increment_handles_empty_and_all_ones(self):
        machine = self.load("binary-increment")
        machine.run_input("")
        self.assertEqual(machine.tape(), "1")
        machine.run_input("11111111")
        self.assertEqual(machine.tape(), "100000000")

    def test_palindrome_sweep(self):
        machine = self.load("palindrome-binary")
        seen = {"accept": 0, "reject": 0}
        for text in binary_strings(7):
            with self.subTest(text=text):
                machine.run_input(text, max_steps=100_000)
                expected = "accept" if text == text[::-1] else "reject"
                self.assertEqual(machine.state, expected)
                seen[expected] += 1
        # both branches must actually be exercised
        self.assertGreater(seen["accept"], 0)
        self.assertGreater(seen["reject"], 0)

    def test_palindrome_marks_are_consistent(self):
        machine = self.load("palindrome-binary")
        machine.run_input("0110")
        self.assertEqual(machine.state, "accept")
        self.assertEqual(machine.tape(), "XYYX")

    def test_busy_beaver_three(self):
        machine = self.load("busy-beaver-3")
        machine.run_input("", max_steps=10_000)
        self.assertEqual(machine.state, "H")
        self.assertEqual(machine.steps, 14)
        self.assertEqual(machine.tape(), "1" * 6)


class CliTests(unittest.TestCase):
    def cli(self, *args):
        return subprocess.run(
            [sys.executable, os.path.join(HERE, "turing_machine.py"), *args],
            cwd=HERE,
            capture_output=True,
            timeout=120,
        )

    def test_palindrome_cli(self):
        result = self.cli(os.path.join(MACHINES, "palindrome-binary.json"), "--input", "0110")
        self.assertEqual(result.returncode, 0)
        out = result.stdout.decode("utf-8")
        self.assertIn("final:   accept", out)
        self.assertNotIn(b"\r\n", result.stdout)

    def test_increment_cli(self):
        result = self.cli(os.path.join(MACHINES, "binary-increment.json"), "--input", "1011")
        self.assertEqual(result.returncode, 0)
        self.assertIn("tape:    1100", result.stdout.decode("utf-8"))

    def test_step_limit_exit_code(self):
        result = self.cli(os.path.join(MACHINES, "busy-beaver-3.json"), "--max-steps", "3")
        self.assertEqual(result.returncode, 1)
        self.assertIn("error:", result.stdout.decode("utf-8"))

    def test_missing_file_exit_code(self):
        result = self.cli(os.path.join(MACHINES, "nope.json"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("error:", result.stdout.decode("utf-8"))

    def test_bad_json_exit_code(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "broken.json")
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write("{not json")
            result = self.cli(path)
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid JSON", result.stdout.decode("utf-8"))

    def test_trace_prints_steps(self):
        result = self.cli(os.path.join(MACHINES, "binary-increment.json"), "--input", "1", "--trace")
        self.assertEqual(result.returncode, 0)
        self.assertIn("step", result.stdout.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
