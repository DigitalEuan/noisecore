# NoiseCore VM — Architecture

## High-level

NoiseCore VM is a **register machine** whose registers and memory are
backed by `NoiseRegisterV3` instances — base-12 positional accumulators
built on top of a 24-bit Golay [24,12,8] manifold.

```
┌──────────── NoiseCore VM ────────────────────────────────────────────────┐
│                                                                           │
│   R0 R1 R2 R3 R4 R5 R6 R7(SP)        ◄── general-purpose registers        │
│      └──────┬─────────┘                                                   │
│             │                                                              │
│      flags: Z N C V                                                       │
│      pc:    instruction pointer                                            │
│      call_stack: list of return PCs (CALL/RET)                            │
│                                                                            │
│   ┌─── Main memory: 256 NoiseRegisterV3 cells ───────────────────────┐    │
│   │  [0]    [1]    [2]    ...    [254]    [255]                       │    │
│   └─────────────────────────────┬─────────────────────────────────────┘    │
│                                  │                                         │
│   ┌─── Devices ───────────────────────────────────────────────────────┐   │
│   │  ConsoleDevice (PRINT_*, READ_*, EXIT, DUMP_REGS)                  │   │
│   └────────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────────┘
```

## Word model: sign-magnitude

The Golay substrate measures **geometric displacement** — a non-negative
quantity. So:

```
NoiseRegisterV3   stores |value|     (always ≥ 0; perfectly substrate-valid)
CPU._signs[i]     stores sign of Ri  (True = negative)
```

Reading is `(-mag if sign and mag != 0 else mag)`. The substrate never
sees a negative number; sign is purely an ISA-level annotation.

This is the v1.0 → v2.0 critical fix made canonical: sign lives in the
ALU, magnitude lives in the cell.

## Memory model

* Addresses 0 … `memory_size − 1` (default 256)
* `.data` directives populate from address 0 upward (origin configurable)
* The stack lives at the **top** of memory and grows **downward** (R7=SP)
* Bounds-checked: out-of-range read or write raises `IndexError`

## Calling convention

| Resource          | Caller-saved  | Callee-saved  |
| ----------------- | ------------- | ------------- |
| R0 (arg / return) | yes           | no            |
| R1–R6             | yes           | no            |
| R7 (SP)           | -             | always        |
| flags             | yes           | no            |

By convention, the first argument is passed in R0 and the return value
comes back in R0. Anything caller-sensitive is `PUSH`ed before `CALL`
and `POP`ped after `RET`. See `examples/03_factorial_recursive.nca`
and `examples/06_fibonacci.nca` for canonical examples.

## Trace and reproducibility

When constructed with `trace=True`, the CPU records every instruction:

```python
TraceEntry(pc, instr, mnemonic, flags_before, flags_after, cycle)
```

The full trace can be hashed (SHA-256) via `info["trace_hash"]` returned
from `cpu.run()`. The same program produces the **same** trace hash on
every run — this is verified by `test_trace_hash_reproducible`.

## Substrate fingerprint

`cpu.substrate_fingerprint()` returns:

* `nrci_mean` — mean Noise-Resonance-Coherence-Index across all
  registers (each register's first cell contributes one NRCI value)
* `magnitude_sha` — SHA-256 (truncated to 16 hex chars) of the magnitude
  pattern across all registers + first 32 memory cells

This gives every program execution a deterministic geometric signature
that can be checked across machines.

## Extension points

| Hook                     | Purpose                                           |
| ------------------------ | ------------------------------------------------- |
| `Device` subclass        | New SYSCALL-driven device (filesystem, net, …)    |
| `cpu.devices.append(d)`  | Register the device with the dispatcher           |
| `Assembler` subclass     | Custom directives                                 |
| `ISA` table              | New opcodes — assembler picks them up automatically |

## Two execution modes

```python
CPU(substrate_mode=True)   # Golay-backed; full physics; ~5–10× slower
CPU(substrate_mode=False)  # plain ints; ~10⁶ ips on a laptop
```

Both modes pass the same 118-test suite (substrate-tagged tests run
substrate mode; ISA tests run plain mode for speed).
