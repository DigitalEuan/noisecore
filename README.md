# NoiseCore VM
Version 1.2.0
A substrate-mediated virtual computation environment
grounded in the Extended Binary Golay Code [24,12,8]

* E R A Craig / UBP Research — May 2026
* 208 tests passing  •  46 opcodes  •  8 example programs

## Read the manual:
[https://github.com/DigitalEuan/noisecore/blob/main/NoiseCore_VM_Users_Manual_v1_2_0.pdf]
* Installation and the two-minute quick-start
* The architecture: layers from Python API down to the Golay substrate
* The assembly language (.nca): full syntax, directives, operand forms
* Complete instruction reference with worked examples
* The Python API for embedding the VM in research scripts
* Substrate mode: Golay geometry, Shadow Processor, S flag, carry work, NRCI, magnitude SHA
* SubstrateALU: native base-12 arithmetic for all CPU operations
* The command-line interface
* Practical application patterns: algorithms, I/O, subroutines, research patterns
* Debugging and troubleshooting
* Known limitations and design trade-offs



## Introduction
NoiseCore VM is a fully functional virtual CPU whose registers and memory are backed by the Golay [24,12,8] geometric substrate of the Universal Binary Principle (UBP) framework. It is not a simulation of a CPU: it is a real register machine with a 46-instruction ISA, a two-pass symbolic assembler, a disassembler, a trace recorder, and eight working example programs.

**The system serves two purposes simultaneously:**
* As a computational tool: programs written in NoiseCore Assembly (.nca) can perform any task a general-purpose integer processor can — arithmetic, recursion, sorting, string manipulation, prime sieves. The CPU runs at over 600,000 instructions per second in plain mode.
* As a UBP research instrument: switching to substrate mode replaces each register with a ShadowRegister backed by a real Golay codeword manifold. As of v1.2.0, all arithmetic (ADD/SUB/MUL/DIV) is performed natively by the SubstrateALU — digit-by-digit on the base-12 cell arrays. Every stored value leaves a measurable geometric fingerprint. The S (Shadow) flag reveals when computation crosses the Voronoi boundary of the linear Phenomenal regime.

## System at a Glance
* 8 general-purpose registers (R0–R7), 256-cell memory, 5-flag register {Z N C V S}, PC, cycle counter, trace recorder
* **ISA**
* 46 instructions across 6 groups: arithmetic/logic, control flow, immediate-mode, memory, stack/subroutines, syscalls/misc
* **Assembler**
* Two-pass .nca source files with labels, .equ constants, .data sections, char literals, hex/binary immediates
* **Disassembler**
* Bytecode → labelled assembly text; round-trip verified
* **SubstrateALU (v1.2.0)**
* Base-12 digit-chain arithmetic: ADD/SUB via carry/borrow, MUL via long-mul, DIV/MOD via Knuth Algorithm D. Python arithmetic operators never applied to full register values.
* **Substrate mode**
* ShadowRegisters: Golay-backed with shadow_active detection, carry_work accounting, NRCI and magnitude SHA fingerprints
* **CLI**
* noisecore run / asm / disasm / repl / info
* **Tests**
* 208 passing tests across 12 test modules
