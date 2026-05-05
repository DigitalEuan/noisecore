# NoiseCore VM
Version 1.2.0

A substrate-mediated virtual computation environment grounded in the **Extended Binary Golay Code [24,12,8]**.

NoiseCore VM is a fully functional virtual CPU whose registers and memory are backed by the Golay geometric substrate of the Universal Binary Principle (UBP) framework. It is not a simulation: it is a real register machine with a 46-instruction ISA, a two-pass symbolic assembler, and a SubstrateALU that performs arithmetic natively on base-12 digit arrays.

## 🚀 Interactive IDE
Explore NoiseCore VM directly in your browser:
**[Launch NoiseCore Interactive IDE](https://DigitalEuan.github.io/noisecore/)**

The IDE features:
* **Interactive Terminal**: Real-time I/O for programs using `SYSCALL 4` (READ_INT) and `SYSCALL 1` (PRINT_INT).
* **Substrate Transparency**: Visual manifold display showing the Golay substrate state and Shadow Regime transitions.
* **Full Documentation**: Embedded architectural theory, ISA reference, and programmer's guide.
* **Substrate Mode**: Toggle between high-speed plain execution and geometrically honest substrate-mediated computation.

## 🧠 Core Concepts

### Substrate-Mediated Arithmetic
In **Substrate Mode**, all arithmetic (ADD, SUB, MUL, DIV) is performed digit-by-digit on base-12 cell arrays. Python never operates on the full integer values; instead, the **SubstrateALU** implements:
* **LAW_SUBSTRATE_ALU_001**: Addition and Subtraction via carry/borrow propagation.
* **LAW_SUBSTRATE_ALU_002**: Multiplication via base-12 long multiplication.
* **LAW_SUBSTRATE_ALU_003**: Division and Modulo via Knuth Algorithm D.

### The Shadow Regime
The **S (Shadow) flag** is a phase-transition sensor. For the `PERFECT_V1` substrate, the "Phenomenal" regime is linear for digits 0-4. When a digit exceeds 4, the substrate folds into the "Shadow" regime, latching the S flag to signify that linear arithmetic has broken down into a new geometric anchor.

### Carry Work
NoiseCore tracks **Carry Work** (LAW_CARRY_WORK_001), the cumulative count of base-4 carry events during value assembly. This represents the geometric binding energy of the computed values, providing a physical dimension to virtual computation.

## 🛠 System at a Glance
* **CPU**: 8 general-purpose registers (R0–R7), 256-cell memory, 5-flag register {Z N C V S}.
* **ISA**: 46 instructions including control flow, immediate arithmetic, and stack operations.
* **Assembler**: Two-pass .nca source files with labels, .equ constants, and .data sections.
* **CLI**: `noisecore run / asm / disasm / repl / info`.
* **Tests**: 208 passing tests verifying every aspect of the VM and SubstrateALU.

## 📖 Documentation
For a deep dive into the system, refer to:
* **[User's Manual (PDF)](./NoiseCore_VM_Users_Manual_v1_2_0.pdf)**: Complete self-contained reference.
* **[Architecture Guide](./docs/ARCHITECTURE.md)**: Layers from Python API to Golay substrate.
* **[ISA Reference](./docs/ISA.md)**: Detailed instruction behavior and flag settings.
* **[Programmer's Guide](./docs/PROGRAMMER_GUIDE.md)**: Patterns and tips for writing .nca assembly.

---
*E R A Craig / UBP Research — May 2026*
