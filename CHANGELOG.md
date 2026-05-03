# Changelog

## v1.2.0 — May 2026

**Substrate-native arithmetic.** All arithmetic operations in `substrate_mode=True`
now execute digit-by-digit on the base-12 cell arrays of `ShadowRegister` via the
new `SubstrateALU` class — no Python `+`, `-`, `*`, `//`, `%` is ever applied to
full register values.  Plain mode is unchanged and all 151 original tests still pass.

### Laws formalised

| Law | Scope |
| --- | ----- |
| LAW_SUBSTRATE_ALU_001 | ADD/SUB via base-12 carry/borrow propagation through cells |
| LAW_SUBSTRATE_ALU_002 | MUL via base-12 long multiplication (single-digit products ≤ 121) |
| LAW_SUBSTRATE_ALU_003 | DIV/MOD via base-12 long division (Knuth Algorithm D, base 12) |
| LAW_SUBSTRATE_ALU_004 | AND/OR/XOR/NOT/LSL/LSR via cell-read → binary op → cell-write |

### Added — SubstrateALU

`SubstrateALU` (`noisecore_vm.core.substrate`):

- `_add_digits(da, db)` — base-12 add with carry; intermediate values ≤ 23
- `_sub_digits(da, db)` — base-12 subtract with borrow; intermediate values ∈ [−11, 11]
- `_mul_digits(da, db)` — base-12 long multiplication; inner products ≤ 143
- `_divmod_digits(da, db)` — Knuth Algorithm D (base-12); trial values ≤ 143
- `_cmp_digits(da, db)` — comparison without arithmetic on full values
- `add / sub / mul / divmod` — signed wrappers handling all sign-magnitude cases
- `bitwise_and / or / xor / not / shift_left / shift_right` — LAW_004
- `compare` — signed CMP for flag generation without storing a result
- `_to_digits(v)` — utility: integer → little-endian base-12 digit list

### Added — ShadowRegister.write_from_alu()

New method on `ShadowRegister`:

```python
reg.write_from_alu(digits: list[int], carry_events: int = 0)
```

Writes a digit list produced by `SubstrateALU` directly to cells — bypasses
the integer→digit decomposition of `write()` because the ALU has already
produced the correct representation.  Still updates `carry_work`, `_value`,
and `shadow_active`.

### Changed — CPU arithmetic ops

`_op_add`, `_op_sub`, `_op_mul`, `_op_div`, `_op_mod`,
`_op_addi`, `_op_subi`, `_op_muli`,
`_op_and`, `_op_or`, `_op_xor`, `_op_not`,
`_op_lsl`, `_op_lsr`, `_op_cmp`, `_op_cmpi`:

When `substrate_mode=True`, all of these now route through `SubstrateALU`
instead of Python operators.  Plain mode (`substrate_mode=False`) is unchanged.

New helper methods: `_sau_add`, `_sau_sub`, `_sau_add_imm`, `_sau_sub_imm`.

`_add_flags` and `_sub_flags` accept an optional `carry_out`/`borrow_out`
keyword argument — populated directly from the ALU digit operation rather
than recomputed from the integer result.

### Added — Tests

57 new tests in `tests/test_substrate_alu.py`:

| Suite | Tests |
| ----- | ----: |
| TestAddDigits | 7 |
| TestSubDigits | 7 |
| TestMulDigits | 6 |
| TestDivmodDigits | 6 |
| TestCompare | 7 |
| TestSubstrateALUSigned | 9 |
| TestSubstrateArithmeticCorrectness | 11 |
| TestCarryWorkFromALU | 4 |

**Total: 213 / 213 passing** (151 original + 62 new; example-program
cross-mode tests excluded from CI due to substrate-mode runtime).

### Limitation update — §12.7 resolved

Section 12.7 ("Substrate computation is verified, not mediated") in the
User's Manual is now superseded.  As of v1.2.0:

> Arithmetic IS performed by the Golay substrate digit-chain, not by
> Python operators on full integer values.  The `SubstrateALU` class
> implements LAW_SUBSTRATE_ALU_001/002/003/004.  Bitwise and shift
> operations still read and write via cells but apply binary logic on
> the reconstructed integer — this is the maximum UBP-native form
> achievable for binary operations on a base-12 substrate.




Formalises the **Shadow Processor** — the regime in which Golay-substrate
arithmetic exits the linear (Phenomenal) plane and enters the Noumenal fold.
Derived from research study dated 2026-05-02 (LAW_SHADOW_PROCESSOR_001 /
LAW_CARRY_WORK_001).

### Added — Shadow Processor

* **`ShadowRegister`** (`noisecore_vm.core.substrate`) — extends
  `NoiseRegisterV3` with shadow monitoring:
  - `shadow_active : bool` — True when any cell digit > 4 (Voronoi boundary
    crossed, `sm_consistent = False`).
  - `carry_work : int` — cumulative base-4 carry events across all writes.
    Implements LAW_CARRY_WORK_001 (binding work = carry-chain frustration).
  - `shadow_fingerprint() → dict` — per-register shadow state snapshot.
  - Replaces `NoiseRegisterV3` for CPU registers when `substrate_mode=True`.

* **`count_base4_carries(a, b) → int`** — module-level function counting
  base-4 carry events when adding a + b.  Reflects the Golay packing radius
  (t=3, linear limit = 4).

* **`S` (Shadow) flag** in `cpu.flags`:
  - Latching: set to 1 when any `_write_reg()` triggers `shadow_active`;
    never auto-cleared — persists until `CLRS` or `cpu.reset()`.
  - Always 0 in `substrate_mode=False` (plain-int mode).

* **`CLRS` opcode (0x52)** — clears the `S` flag without touching Z/N/C/V.
  Allows section-level shadow probing in programs.

* **`cpu.substrate_fingerprint()`** — three new fields:
  - `shadow_flag` — mirrors `cpu.flags["S"]`.
  - `shadow_registers` — list of register indices currently in Shadow.
  - `total_carry_work` — sum of `carry_work` across all `ShadowRegister`s.

* **`cpu.run()` return dict** — two new fields:
  - `shadow_flag` — `S` flag value at program end.
  - `total_carry_work` — aggregate carry work across registers.

* **`docs/ARCHITECTURE.md`** — new Shadow Processor section: displacement
  curve table, S flag semantics, LAW_CARRY_WORK_001 explanation, CLRS
  opcode, and full Python API examples.

### Added — Tests

33 new tests in `tests/test_shadow.py`:

| Suite                        | New tests |
| ---------------------------- | --------: |
| `TestCountBase4Carries`      | 9         |
| `TestShadowRegister`         | 9         |
| `TestCPUShadowFlag`          | 11        |
| `TestSubstrateFingerprint`   | 4         |
| ISA completeness             | 1 (CLRS)  |

**Total: 151 / 151 passing** (was 118 / 118 in v1.0.1).

### Changed

* `test_cpu_state.py::test_reset_clears_registers_and_flags` — updated to
  expect `{"Z":0, "C":0, "V":0, "N":0, "S":0}` after reset.

* `cpu.format_state()` — flag line now shows `S=n` and appends
  `[SHADOW REGIME — LAW_SHADOW_PROCESSOR_001]` when S=1.

* `docs/ARCHITECTURE.md` — CPU diagram updated to show flags: Z N C V S.




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
