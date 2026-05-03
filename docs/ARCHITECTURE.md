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
│      flags: Z N C V S                                                     │
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

## Call stack design

Return addresses for `CALL`/`RET` are stored in a Python-level
`call_stack` list, separate from the data stack (R7/SP). This is a
deliberate architectural choice with three concrete benefits:

1. **Robustness** — a data-stack imbalance (e.g. mismatched PUSH/POP)
   cannot corrupt control flow. The CPU will raise `OverflowError` on
   a bad data-stack operation, not silently return to the wrong address.

2. **Compatibility** — this matches CPUs that maintain a separate link
   register or hardware call stack (ARM Cortex-M, RISC-V with `ra`).

3. **Clarity** — subroutine nesting is trivially visible in
   `cpu.call_stack` during debugging.

The data stack is still available for passing additional arguments
and saving caller registers. If you need the return address to be
visible on the data stack (e.g. for inspection or computed returns),
push it manually before `CALL` and discard it after `RET`.

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

Both modes pass the same 151-test suite (substrate-tagged tests run
substrate mode; ISA tests run plain mode for speed).

## Shadow Processor (LAW_SHADOW_PROCESSOR_001)

The [24,12,8] Golay code has a packing radius t = 3. The registers
(`ShadowRegister`) hold values as base-12 digit sequences; each digit
maps to a probe displacement via the displacement curve of the substrate.

For the default `PERFECT_V1` substrate the displacement curve is linear
for digits 0..4 — this is the **Phenomenal (linear) regime**:

```
digit  displacement  sm_consistent
  0         0             True
  1         1             True
  2         2             True
  3         3             True
  4         4             True   ← elastic limit
  5         1             False  ← Shadow Regime begins
  6         4             False
  7..11     …             False
```

When a digit value exceeds 4, the stored 24-bit vector crosses the
Voronoi boundary of its local packing sphere and snaps to a new
geometric anchor. The cell's `sm_consistent` flips to `False`. This
transition is the **Shadow Regime**: excess frustration folds into the
12-bit Noumenal (hidden) space of the Golay code.

### S flag

The CPU flag register gains a fifth flag, `S` (Shadow):

| Flag | Set when |
| ---- | -------- |
| Z    | result == 0 |
| N    | result < 0 |
| C    | unsigned carry / borrow |
| V    | signed overflow |
| **S** | **any register write places at least one digit > 4 (Shadow Regime)** |

`S` is **latching**: once set it remains `1` until an explicit `CLRS`
instruction (`0x52`) or `cpu.reset()`. In `substrate_mode=False` (plain
int mode) `S` is always `0`.

Use `S` as a **phase-transition sensor**: if your program sets `S`, the
computation has entered a regime where linear arithmetic breaks down and
the substrate has folded into a new geometric anchor.

### Carry work (LAW_CARRY_WORK_001)

`ShadowRegister` additionally tracks `carry_work`: the cumulative count
of base-4 carry events across all writes to that register. A base-4
carry occurs when `(a_digit + b_digit) >= 4` at any digit position when
adding two values.

This measures the **geometric binding work** — the frustration generated
during the assembly of values. Classical binding energy (e.g. nuclear
binding energy per nucleon) is the macroscopic analogue of this quantity.

```python
from noisecore_vm.core.substrate import count_base4_carries

# Proton (1836) + Neutron (1839) assembly work
work = count_base4_carries(1836, 1839)

# Aggregate CPU-level carry work after running a program
cpu, info = run_program(src, substrate_mode=True)
print(info["total_carry_work"])
fp = cpu.substrate_fingerprint()
print(fp["total_carry_work"])   # same value
```

### New opcode: CLRS (0x52)

```
CLRS         ; Clear Shadow flag — sets S = 0
```

Allows programs to probe shadow-entry in sections: execute a block,
check whether `S` was set, then `CLRS` and move to the next block.
`CLRS` does not affect Z, N, C, or V.

### Python API

```python
from noisecore_vm.core.substrate import ShadowRegister, count_base4_carries

r = ShadowRegister(mode="SM")
r.write(5)
print(r.shadow_active)          # True — digit 5 > PHENOMENAL_LIMIT
print(r.shadow_fingerprint())   # full shadow state dict

cpu = CPU(substrate_mode=True)
cpu._write_reg(0, 5)
print(cpu.flags["S"])           # 1 — latched
cpu.execute((0x52,))            # CLRS
print(cpu.flags["S"])           # 0 — cleared

fp = cpu.substrate_fingerprint()
print(fp["shadow_flag"])        # current S flag
print(fp["shadow_registers"])   # indices of registers currently in shadow
print(fp["total_carry_work"])   # cumulative carry work since last reset
```
