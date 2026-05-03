# NoiseCore VM — Programmer's Guide

A practical guide to writing programs that run on the NoiseCore VM.

## Source-file format (`.nca`)

* Each line is one statement
* Comments start with `;`
* Labels end in `:`
* Directives start with `.`

Example:
```
; example.nca — multiply two numbers
.equ A 7
.equ B 6

start:
    LOAD R0, #A
    LOAD R1, #B
    MUL  R2, R0, R1
    MOV  R0, R2
    SYSCALL 1                ; PRINT_INT
    SYSCALL 6                ; PRINT_NL
    HALT
```

## Directives

| Directive            | Effect                                         |
| -------------------- | ---------------------------------------------- |
| `.equ NAME VALUE`    | Define a named constant                        |
| `.data NAME v1 v2 …` | Reserve memory & initialise (NAME = base addr) |
| `.org ADDR`          | Set the .data write pointer                    |

## Operand syntax

| Form         | Meaning                            |
| ------------ | ---------------------------------- |
| `R0`–`R7`    | Register                           |
| `#5`         | Decimal immediate                  |
| `#-42`       | Negative decimal immediate         |
| `#0xFF`      | Hex immediate                      |
| `#0b1010`    | Binary immediate                   |
| `'A'`        | Char literal (ord('A') = 65)       |
| `loop`       | Label or `.equ` constant           |
| `MAX`        | Named constant from `.equ`         |

## Common patterns

### Counted loop
```
    LOAD R0, #10        ; counter
loop:
    CMPI R0, 0
    JLE  done
    ; ... body ...
    SUBI R0, R0, #1
    JMP  loop
done:
```

### Array iteration via pointer
```
    LOAD R5, arr        ; base ptr
    LOAD R6, #N         ; length
loop:
    CMPI R6, 0
    JLE  done
    LOADI R0, R5        ; *p
    ; ... use R0 ...
    ADDI R5, R5, #1     ; p++
    SUBI R6, R6, #1
    JMP  loop
```

### Subroutine + caller-saved register
```
    LOAD R0, #5
    PUSH R1             ; save what caller cares about
    CALL square
    POP  R1
    SYSCALL 1
    HALT
square:
    MUL R0, R0, R0
    RET
```

### Recursive function
```
fact:
    CMPI R0, 1
    JLE  fact_base
    PUSH R0
    SUBI R0, R0, #1
    CALL fact
    POP  R1
    MUL  R0, R0, R1
    RET
fact_base:
    LOAD R0, #1
    RET
```

### Memory-mapped string
```
.data greeting 'H' 'I' '!' 0

    LOAD R0, greeting
    SYSCALL 3           ; PRINT_STR (zero-terminated)
```

## Tips

1. **Use `CMP` / `CMPI` for branch tests** — they set flags without
   touching registers. Plain arithmetic also sets flags but it costs you
   the destination register.

2. **Watch flag clobbering**. `LOAD R2, #1` sets the flags from the
   value loaded. If you want to test a flag set earlier, do the test
   *before* the load.

3. **Stack discipline**. Always pair `PUSH` with `POP` along every code
   path that returns. The CPU's auxiliary `call_stack` is separate from
   the data stack, so an unbalanced data stack will not corrupt control
   flow — but it will leak memory cells.

4. **Memory bounds**. `STORE`/`LOAD_MEM` raise `IndexError` if the
   address is out of range. Indirect forms (`STOREI`/`LOADI`/`STOREX`/
   `LOADX`) can compute out-of-range addresses at runtime; the CPU
   catches them.

5. **Infinite-loop guard**. The CPU enforces `max_cycles` (default
   1,000,000) and raises `RuntimeError` if exceeded. Bump it for long
   programs:
   ```python
   cpu.run(prog, max_cycles=10_000_000)
   ```

## Debugging workflow

```bash
$ noisecore asm myprog.nca           # see the disassembled listing
$ noisecore run myprog.nca --verbose # trace each instruction at runtime
$ noisecore run myprog.nca --trace   # record a hashable trace
$ noisecore run myprog.nca --stats   # cycle count, IPS, NRCI fingerprint
```

Inside a program, `SYSCALL 7` (DUMP_REGS) prints the entire CPU state.

## Performance

* Plain mode: typically 100k–1M instructions per second on a laptop
* Substrate mode: 5–10× slower; run only when you need geometric validity

For unit tests of program logic, default to plain mode. For end-to-end
runs whose results you'll publish or commit, use substrate mode and
record `cpu.substrate_fingerprint()` alongside the result.
