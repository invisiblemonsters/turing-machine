# turing-machine

A tiny deterministic Turing machine simulator in plain Python — no dependencies. Machines are JSON files, the tape is infinite, and every run reports the step count, the final state and the tape.

## Usage

```bash
python turing_machine.py machines/binary-increment.json --input 1011
```

```
machine: binary-increment
steps:   8
final:   halt
tape:    1100
```

Add `--trace` to print every step, and `--max-steps N` to bound a run:

```bash
python turing_machine.py machines/busy-beaver-3.json --trace
python turing_machine.py machines/busy-beaver-3.json --max-steps 3   # exits 1
```

Exit codes: `0` halted normally, `1` hit the step limit, `2` bad machine file.

## Machine format

```json
{
  "name": "flip-first-bit",
  "blank": "_",
  "start": "q0",
  "halt": ["halt"],
  "transitions": [
    {"state": "q0", "read": "1", "write": "0", "move": "R", "next": "halt"},
    {"state": "q0", "read": "0", "write": "1", "move": "R", "next": "halt"}
  ]
}
```

- `state` / `next` — state names, any non-empty strings.
- `read` / `write` — single characters. Writing the blank symbol erases the cell.
- `move` — `L`, `R` or `N` (stay put).
- A state listed in `halt` stops the machine without consuming a step.
- If a state has no rule for the symbol under the head, the machine halts where it is — exactly what a real machine would do: it hangs.

## Included machines

| Machine | Input | Result |
| --- | --- | --- |
| `binary-increment` | `1011` | `1100` — adds 1 to a binary number |
| `palindrome-binary` | `0110` | halts in `accept` (marks the tape `XYYX`) |
| `palindrome-binary` | `011` | halts in `reject` |
| `busy-beaver-3` | blank tape | 6 ones left after 14 steps |

`palindrome-binary` answers through its final state rather than the tape: it walks in from both ends, replacing 0/1 with X/Y as it verifies the match.

## Library use

```python
from turing_machine import load_machine_file

machine = load_machine_file("machines/binary-increment.json")
machine.run_input("1111")
print(machine.steps, machine.state, machine.tape())   # 10 halt 10000
```

## Tests

```bash
python -m unittest -v
```

28 tests: tape mechanics, spec validation, step limits, CLI exit codes and byte-exact output, plus sweeps that check `binary-increment` against `bin(n + 1)` for n < 2048 and `palindrome-binary` against Python's `s == s[::-1]` for every binary string up to length 7.

## License

MIT
