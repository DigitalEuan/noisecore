# NoiseCore VM — Instruction Set Reference

All instructions are encoded as Python tuples `(opcode, operand1, operand2, ...)`.
The assembler accepts the mnemonic forms shown below.

## Operand kinds

| Tag | Meaning                  | Examples                          |
| --- | ------------------------ | --------------------------------- |
| `R` | Register index `0..N-1`  | `R0`, `R7`                         |
| `#` | Signed immediate         | `#5`, `#-42`, `#0xFF`, `#0b1010`, `'A'` |
| `A` | Memory or program address (label-resolvable) | `loop`, `arr`, `100` |
| `S` | Syscall number           | `1` (PRINT_INT), `5` (EXIT)        |

## Arithmetic / logic / halt — `0x01`–`0x0F`

| Opcode | Mnemonic | Operands         | Semantics                                              |
| -----: | -------- | ---------------- | ------------------------------------------------------ |
|  `01`  | `LOAD`   | `R, #`           | `Rd ← imm` (sign preserved); flags                     |
|  `02`  | `MOV`    | `R, R`           | `Rd ← Rs`; flags                                        |
|  `03`  | `ADD`    | `R, R, R`        | `Rd ← Rs1 + Rs2`; Z, N, C, V                            |
|  `04`  | `SUB`    | `R, R, R`        | `Rd ← Rs1 − Rs2`; Z, N, C(borrow), V                    |
|  `05`  | `AND`    | `R, R, R`        | bitwise on magnitudes                                   |
|  `06`  | `OR`     | `R, R, R`        | bitwise on magnitudes                                   |
|  `07`  | `XOR`    | `R, R, R`        | bitwise on magnitudes                                   |
|  `08`  | `NOT`    | `R, R`           | bitwise NOT, masked to `word_bits`                      |
|  `09`  | `LSL`    | `R, R, #`        | logical shift left                                      |
|  `0A`  | `LSR`    | `R, R, #`        | logical shift right                                     |
|  `0B`  | `MUL`    | `R, R, R`        | signed product                                          |
|  `0C`  | `DIV`    | `R, R, R`        | signed quotient (truncates toward 0); ZeroDivisionError |
|  `0D`  | `MOD`    | `R, R, R`        | sign-of-dividend remainder; ZeroDivisionError           |
|  `0E`  | `CMP`    | `R, R`           | flags ← (Rs1 − Rs2); registers untouched                |
|  `0F`  | `HALT`   | (none)           | sets `halted = True`                                    |

## Control flow — `0x10`–`0x1B`

| Opcode | Mnemonic | Condition                  |
| -----: | -------- | -------------------------- |
|  `10`  | `JMP`    | unconditional              |
|  `11`  | `JZ`     | Z = 1                      |
|  `12`  | `JNZ`    | Z = 0                      |
|  `13`  | `JN`     | N = 1                      |
|  `14`  | `JNN`    | N = 0                      |
|  `15`  | `JC`     | C = 1                      |
|  `16`  | `JE`     | Z = 1                      |
|  `17`  | `JNE`    | Z = 0                      |
|  `18`  | `JG`     | Z = 0  AND  N = V          |
|  `19`  | `JL`     | N ≠ V                      |
|  `1A`  | `JGE`    | N = V                      |
|  `1B`  | `JLE`    | Z = 1  OR  N ≠ V           |

`CMP`/`CMPI` set the flags; the conditional jumps consume them.
Signed comparisons (`JG`, `JL`, `JGE`, `JLE`) follow the standard ARM/x86
"N == V" convention.

## Immediate-mode arithmetic — `0x20`–`0x25`

| Opcode | Mnemonic | Operands     | Semantics                |
| -----: | -------- | ------------ | ------------------------ |
|  `20`  | `ADDI`   | `R, R, #`    | `Rd ← Rs + imm`           |
|  `21`  | `SUBI`   | `R, R, #`    | `Rd ← Rs − imm`           |
|  `22`  | `MULI`   | `R, R, #`    | `Rd ← Rs × imm`           |
|  `23`  | `ANDI`   | `R, R, #`    | bitwise AND with imm      |
|  `24`  | `ORI`    | `R, R, #`    | bitwise OR with imm       |
|  `25`  | `CMPI`   | `R, #`       | flags ← (Rs − imm)        |

## Memory access — `0x30`–`0x35`

| Opcode | Mnemonic   | Operands       | Semantics                                |
| -----: | ---------- | -------------- | ---------------------------------------- |
|  `30`  | `STORE`    | `R, A`         | `mem[addr] ← Rs`                          |
|  `31`  | `LOAD_MEM` | `R, A`         | `Rd ← mem[addr]`                          |
|  `32`  | `STOREI`   | `R, R`         | `mem[Rb] ← Rs`  (indirect via register)   |
|  `33`  | `LOADI`    | `R, R`         | `Rd ← mem[Rs]`                            |
|  `34`  | `STOREX`   | `R, R, #`      | `mem[Rb + off] ← Rs`                      |
|  `35`  | `LOADX`    | `R, R, #`      | `Rd ← mem[Rb + off]`                      |

## Stack & subroutines — `0x40`–`0x43`

| Opcode | Mnemonic | Operands | Semantics                                 |
| -----: | -------- | -------- | ----------------------------------------- |
|  `40`  | `PUSH`   | `R`      | `mem[SP] ← Rs; SP ← SP − 1`                |
|  `41`  | `POP`    | `R`      | `SP ← SP + 1; Rd ← mem[SP]`                |
|  `42`  | `CALL`   | `A`      | `call_stack.push(PC + 1); PC ← addr`       |
|  `43`  | `RET`    | (none)   | `PC ← call_stack.pop()`                    |

`SP` is **`R7`**. It starts at `memory_size − 1` and grows downward.
`CALL`/`RET` use a separate Python-level call stack so user code is free to
treat the data stack however it likes.

## System calls — `0x50`–`0x51`

| Opcode | Mnemonic | Operands | Semantics                          |
| -----: | -------- | -------- | ---------------------------------- |
|  `50`  | `SYSCALL`| `S`      | dispatch to console device by num  |
|  `51`  | `NOP`    | (none)   | no operation                       |

### Syscall numbers

| `#` | Name        | Action                                         |
| --- | ----------- | ---------------------------------------------- |
| `1` | PRINT_INT   | print signed integer in `R0`                   |
| `2` | PRINT_CHAR  | print Unicode char with code-point in `R0`     |
| `3` | PRINT_STR   | print zero-terminated string starting at `mem[R0]` |
| `4` | READ_INT    | read integer from input queue into `R0`        |
| `5` | EXIT        | halt (`exit_code = R0`)                        |
| `6` | PRINT_NL    | print a newline                                |
| `7` | DUMP_REGS   | print full CPU state                           |

## Flag-setting summary

|             | Z | N | C        | V         |
| ----------- | - | - | -------- | --------- |
| `LOAD`      | ✓ | ✓ | —        | —         |
| `MOV`       | ✓ | ✓ | —        | —         |
| `ADD`/`ADDI`| ✓ | ✓ | unsigned | signed    |
| `SUB`/`SUBI`| ✓ | ✓ | borrow   | signed    |
| `MUL`/`MULI`| ✓ | ✓ | —        | —         |
| `DIV`/`MOD` | ✓ | ✓ | —        | —         |
| `AND`/`OR`/`XOR`/`NOT` | ✓ | ✓ | — | —    |
| `LSL`/`LSR` | ✓ | ✓ | —        | —         |
| `CMP`/`CMPI`| ✓ | ✓ | borrow   | signed    |
| `LOAD_MEM`/`LOADI`/`LOADX` | ✓ | ✓ | — | — |
| `POP`       | ✓ | ✓ | —        | —         |

`STORE`/`STOREI`/`STOREX` deliberately do **not** set flags.
