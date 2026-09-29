# NoiseCore VM

A substrate-mediated virtual computation environment built on the
[24,12,8] Golay code geometric substrate. Real ISA, real assembler, real
programs — not a toy.

## Status (v1.4.0)

| Component | State |
|---|---|
| Tests | 145+ passing across 13 suites |
| Opcodes | **59** (incl. zero-storage & delta-sigma families) |
| Zero storage | syndrome route verified at import; `table_lookup` trip-wire held at 0 |
| Deep modules | delta-sigma (Lean-proved contract), coset decoder, Cesàro dynamics, deep-hole classifier, NRCI, ledger |

## Status (this build)

| Component                               | State                                   |
| --------------------------------------- | --------------------------------------- |
| **Tests**                               | **118 / 118 passing**                   |
| **Example programs**                    | **8 / 8 working**                       |
| **Opcodes implemented**                 | **45**                                  |
| **Real Golay engine**                   | active (4096 codewords, 759 octads)     |
| **Substrate-mediated mode**             | available; degrades gracefully to plain |

## Quick start

```python
from noisecore_vm import run_program

src = """
    LOAD R0, #5
    LOAD R1, #7
    ADD  R2, R0, R1
    MOV  R0, R2
    SYSCALL 1     ; PRINT_INT
    SYSCALL 6     ; PRINT_NL
    HALT
"""
cpu, info = run_program(src)
print(cpu.console.output())   # → 12
print(info["cycles"])         # → 7
```

Or run a `.nca` file from the command line:

```bash
$ noisecore run examples/04_bubble_sort.nca --stats
1 2 3 4 5 6 7 8
[stats] cycles=450  halted=True  exit=0  elapsed=0.0011s  ips=409090
```

## What you get

### A real ISA (45 instructions)

```
arithmetic / logic
  LOAD MOV ADD SUB AND OR XOR NOT LSL LSR MUL DIV MOD CMP HALT
control flow
  JMP JZ JNZ JN JNN JC JE JNE JG JL JGE JLE
immediate
  ADDI SUBI MULI ANDI ORI CMPI
memory
  STORE LOAD_MEM STOREI LOADI STOREX LOADX
stack & subroutines
  PUSH POP CALL RET
syscalls
  SYSCALL NOP
```

### A real assembler (`.nca` source files)

* Symbolic labels (`fact:`, `loop:`, `done:`)
* Named constants (`.equ N 30`)
* Data sections (`.data arr 8 3 1 5 2 7 4 6`)
* Char literals (`'A'`, `' '`, `'Z'`)
* Hex / binary / decimal / negative immediates
* Fully implemented round-trip: assemble → disassemble → reassemble produces
  bit-identical bytecode (verified by `test_round_trip_disassemble_reassemble`)

### A real CPU

* 8 general-purpose substrate registers + R7 as stack pointer
* 256-cell main memory (also substrate-backed)
* Configurable word width (8 / 16 / 32 / 64 bits)
* Sign-magnitude integer arithmetic that keeps the Golay substrate physically
  valid (geometric displacement is always non-negative; sign lives at the
  ALU layer, exactly as the v2 fix specified)
* Full flag register `{Z, N, C, V}` with correct unsigned/signed semantics
* Cycle counter, instruction counter, and (optional) trace recorder with
  reproducible SHA-256 trace hash

### Real programs (in `examples/`)

| File                            | What it shows                           | Cycles |
| ------------------------------- | --------------------------------------- | -----: |
| `01_hello.nca`                  | PRINT_CHAR syscall                      |     12 |
| `02_factorial_iter.nca`         | iterative loop                          |     38 |
| `03_factorial_recursive.nca`    | CALL/RET + PUSH/POP                     |     49 |
| `04_bubble_sort.nca`            | indexed memory access (LOADI/STOREI)    |    450 |
| `05_prime_sieve.nca`            | Sieve of Eratosthenes up to 30          |    908 |
| `06_fibonacci.nca`              | callee-saved register convention        |    167 |
| `07_gcd.nca`                    | Euclidean GCD via subroutine            |     33 |
| `08_string_reverse.nca`         | memory-mapped strings + PRINT_STR       |    172 |

### Real tests (118 of them)

* `test_arithmetic.py` — every arithmetic/logic op + flag semantics (32 tests)
* `test_immediate.py` — immediate-mode ops (8 tests)
* `test_branches.py` — every jump variant + signed/unsigned compares (13 tests)
* `test_memory.py` — direct, indirect, indexed addressing + bounds (6 tests)
* `test_stack.py` — PUSH/POP/CALL/RET + recursion (7 tests)
* `test_syscalls.py` — every syscall (PRINT_INT, PRINT_CHAR, PRINT_STR, READ_INT, EXIT, PRINT_NL, DUMP_REGS) (7 tests)
* `test_assembler.py` — labels, .equ, .data, char literals, error reporting, disasm round-trip (14 tests)
* `test_programs.py` — full end-to-end runs of all 8 demo programs + ad-hoc programs (10 tests)
* `test_substrate.py` — Golay register round-trip, displacement curve, sign-magnitude in substrate mode (9 tests)
* `test_cpu_state.py` — reset, max_cycles, trace reproducibility (6 tests)
* `test_isa_completeness.py` — every opcode dispatchable, every mnemonic assembleable (6 tests)

```bash
$ pytest
============================= 118 passed in 5.99s ==============================
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    User .nca source                          │
└──────────────────────────────┬──────────────────────────────┘
                               │ assembler (labels, .equ, .data)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│  Bytecode: list of (opcode, *operands) tuples                │
└──────────────────────────────┬──────────────────────────────┘
                               │ CPU.execute() dispatcher
                               ▼
┌─────────────────────────────────────────────────────────────┐
│   CPU registers ─── 8 × NoiseRegisterV3 (sign-magnitude)    │
│   CPU memory   ─── 256 × NoiseRegisterV3 (sign-magnitude)   │
│   CPU flags    ─── {Z, N, C, V}                              │
│   CPU stack    ─── data on R7 / call_stack list             │
│   CPU devices  ─── Console (PRINT_INT/CHAR/STR, READ_INT…)  │
└──────────────────────────────┬──────────────────────────────┘
                               │ each register/memory cell
                               ▼
┌─────────────────────────────────────────────────────────────┐
│   NoiseRegisterV3: base-12 positional accumulator           │
│   ↓                                                          │
│   NoiseCellV3: 24-bit Golay manifold, displacement curve    │
│   ↓                                                          │
│   GolayCodeEngine: real [24,12,8] code (4096 codewords)     │
└─────────────────────────────────────────────────────────────┘
```

## Two execution modes

| Mode                          | Speed     | Physics validity                              |
| ----------------------------- | --------- | --------------------------------------------- |
| `substrate_mode=True`         | ~5–10× slower | Every register/memory cell is Golay-mediated; NRCI fingerprint available |
| `substrate_mode=False`        | fast      | Plain integers; substrate physics bypassed (used for unit tests) |

This lets you write unit tests fast and benchmarks meaningful, while still
being able to run any program through the full substrate when you want
the geometry-backed semantics.

## Documentation

* `docs/ISA.md` — full instruction-set reference
* `docs/ARCHITECTURE.md` — registers, memory model, calling convention
* `docs/PROGRAMMER_GUIDE.md` — how to write `.nca` programs

## CLI reference

```
noisecore run FILE.nca          # assemble & execute
noisecore asm FILE.nca [-o OUT] # disassembled listing with addresses & labels
noisecore disasm FILE.nca       # round-trip disassembly
noisecore info                  # ISA reference + syscall table
noisecore repl                  # interactive
```

## License

MIT — see LICENSE.
