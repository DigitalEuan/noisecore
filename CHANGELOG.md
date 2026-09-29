# Changelog

## v1.0.0 — May 2026

First release of the NoiseCore Virtual Machine as a packaged, reproducible
computation environment (vs. the v2 ALU prototype).

### Added — ISA (15 new opcodes)

| Group        | New                                                     |
| ------------ | ------------------------------------------------------- |
| Arithmetic   | `CMP`                                                   |
| Branches     | `JE`, `JNE`, `JG`, `JL`, `JGE`, `JLE` (signed compares) |
| Immediate    | `ANDI`, `ORI`, `CMPI`                                   |
| Memory       | `STOREI`, `LOADI`, `STOREX`, `LOADX` (indirect/indexed) |
| Control      | `PUSH`, `POP`, `CALL`, `RET`, `SYSCALL`, `NOP`          |

Total opcode count: **45** (was 30 in v2 ALU).

### Added — Toolchain

* Symbolic two-pass assembler with labels, `.equ`, `.data`, `.org`
* Disassembler with round-trip guarantee
* CLI: `noisecore run | asm | disasm | info | repl`
* `pyproject.toml` packaging with console-script entry point

### Added — Devices

* `ConsoleDevice` for I/O syscalls (PRINT_INT, PRINT_CHAR, PRINT_STR,
  READ_INT, EXIT, PRINT_NL, DUMP_REGS)
* Pluggable `Device` base class for extensions

### Added — Diagnostics

* CPU trace recorder with reproducible SHA-256 trace hash
* Aggregate substrate fingerprint (`nrci_mean` + `magnitude_sha`)
* `format_state()` / DUMP_REGS syscall

### Added — Programs

Real demos (not toys), all under `examples/`:

* `04_bubble_sort.nca` — 8-element in-place sort using indexed memory
* `05_prime_sieve.nca` — Sieve of Eratosthenes up to N=30
* `03_factorial_recursive.nca` — recursive factorial via CALL/RET + PUSH/POP
* `06_fibonacci.nca` — Fibonacci with caller-saved registers
* `08_string_reverse.nca` — memory-mapped strings with PRINT_STR
* plus `01_hello.nca`, `02_factorial_iter.nca`, `07_gcd.nca`

### Added — Tests (118 total)

| Suite                          | Tests |
| ------------------------------ | ----: |
| `test_arithmetic.py`           |    32 |
| `test_immediate.py`            |     8 |
| `test_branches.py`             |    13 |
| `test_memory.py`               |     6 |
| `test_stack.py`                |     7 |
| `test_syscalls.py`             |     7 |
| `test_assembler.py`            |    14 |
| `test_programs.py`             |    10 |
| `test_substrate.py`            |     9 |
| `test_cpu_state.py`            |     6 |
| `test_isa_completeness.py`     |     6 |

### Documented

* `docs/ISA.md` — full instruction reference + flag-setting table
* `docs/ARCHITECTURE.md` — registers, memory model, calling convention
* `docs/PROGRAMMER_GUIDE.md` — how to write `.nca` programs

### Validated

`scripts/validate_and_report.py` produces both `validation_report.md` and
`validation_report.json`, exercising:

* full pytest suite
* every example program in plain mode
* every example program in full substrate mode
* trace-hash reproducibility (each example run twice, SHA-256 compared)
* substrate calibration (PERFECT_V1 displacement curve)

### Migrated from v2 ALU

* All v2 sign-magnitude semantics preserved (the `-7 + 2 = -5` chain test
  passes in `test_signs_chain`)
* All v2 flag semantics preserved (C, V, Z, N)
* All 37 v2 ALU tests have equivalents in the new pytest suite

## v1.4.0 — September 2026

* `cesaro.py` — perturbation chain on syndrome space Syn=(ZMod2)^12 with the
  proved Cesàro rate |avg_N − 1/4096| ≤ 24/N, executable (Golay/Cesaro.lean).
* `deep_hole.py` — exact-rational L1 deep-hole classifier machinery with the
  two proved properties as runtime checks: named-of-separated, absent-certifies
  (DeepHoleClassifier.lean).
* v1.3.0 (earlier): `core/zs.py` — zero-storage all the way down; cells and
  registers verify via twelve parities against the 36-byte generator;
  ledger trip-wire `table_lookup == 0` asserted throughout.
* v1.2.0 (earlier): syndrome/Leech/decode/ledger/moving-DS opcodes 0x66–0x6D;
  eight-piece zero-storage v5 integration.
* Polish: census docstring corrected (Lean's Census.lean proves the coset
  census; the codeword weight census is computed from generated codewords).
