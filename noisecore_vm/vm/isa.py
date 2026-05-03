"""
================================================================================
NoiseCore VM — Instruction Set Architecture (ISA)
================================================================================
Single source of truth for opcode → mnemonic → operand-shape mapping.
Used by the CPU (decode), assembler (encode), and disassembler (pretty-print).

Operand shapes
--------------
Each entry has:
    mnemonic  : str   — uppercase canonical name
    operands  : tuple — sequence of operand-kind tags:
                          'R'   register index 0..N-1
                          '#'   signed immediate
                          'A'   memory / program address (unsigned)
                          'S'   syscall number
                        empty tuple for no-operand opcodes
    arity     : int   — number of operands

Authoring conventions
---------------------
• Opcodes 0x01..0x0F     core arithmetic / logic / halt
• Opcodes 0x10..0x1F     control flow (jumps, compare)
• Opcodes 0x20..0x2F     immediate-mode arithmetic
• Opcodes 0x30..0x3F     memory access (direct + indexed)
• Opcodes 0x40..0x4F     stack & subroutines
• Opcodes 0x50..0x5F     system calls / I/O
"""

from typing import Dict, NamedTuple, Tuple


class OpSpec(NamedTuple):
    opcode: int
    mnemonic: str
    operands: Tuple[str, ...]

    @property
    def arity(self) -> int:
        return len(self.operands)


# ── ISA TABLE ────────────────────────────────────────────────────────────────

ISA: Dict[int, OpSpec] = {
    # arithmetic / logic / halt -------------------------------------------------
    0x01: OpSpec(0x01, "LOAD",   ("R", "#")),
    0x02: OpSpec(0x02, "MOV",    ("R", "R")),
    0x03: OpSpec(0x03, "ADD",    ("R", "R", "R")),
    0x04: OpSpec(0x04, "SUB",    ("R", "R", "R")),
    0x05: OpSpec(0x05, "AND",    ("R", "R", "R")),
    0x06: OpSpec(0x06, "OR",     ("R", "R", "R")),
    0x07: OpSpec(0x07, "XOR",    ("R", "R", "R")),
    0x08: OpSpec(0x08, "NOT",    ("R", "R")),
    0x09: OpSpec(0x09, "LSL",    ("R", "R", "#")),
    0x0A: OpSpec(0x0A, "LSR",    ("R", "R", "#")),
    0x0B: OpSpec(0x0B, "MUL",    ("R", "R", "R")),
    0x0C: OpSpec(0x0C, "DIV",    ("R", "R", "R")),
    0x0D: OpSpec(0x0D, "MOD",    ("R", "R", "R")),
    0x0E: OpSpec(0x0E, "CMP",    ("R", "R")),     # NEW: sets flags from Rs1 - Rs2
    0x0F: OpSpec(0x0F, "HALT",   ()),

    # control flow ---------------------------------------------------------------
    0x10: OpSpec(0x10, "JMP",    ("A",)),
    0x11: OpSpec(0x11, "JZ",     ("A",)),
    0x12: OpSpec(0x12, "JNZ",    ("A",)),
    0x13: OpSpec(0x13, "JN",     ("A",)),
    0x14: OpSpec(0x14, "JNN",    ("A",)),
    0x15: OpSpec(0x15, "JC",     ("A",)),
    0x16: OpSpec(0x16, "JE",     ("A",)),         # NEW: jump if equal (Z=1)
    0x17: OpSpec(0x17, "JNE",    ("A",)),         # NEW: jump if not equal
    0x18: OpSpec(0x18, "JG",     ("A",)),         # NEW: signed greater  (Z=0 & N=V)
    0x19: OpSpec(0x19, "JL",     ("A",)),         # NEW: signed less    (N!=V)
    0x1A: OpSpec(0x1A, "JGE",    ("A",)),         # NEW: signed >=     (N==V)
    0x1B: OpSpec(0x1B, "JLE",    ("A",)),         # NEW: signed <=     (Z=1 | N!=V)

    # immediate-mode arithmetic --------------------------------------------------
    0x20: OpSpec(0x20, "ADDI",   ("R", "R", "#")),
    0x21: OpSpec(0x21, "SUBI",   ("R", "R", "#")),
    0x22: OpSpec(0x22, "MULI",   ("R", "R", "#")),
    0x23: OpSpec(0x23, "ANDI",   ("R", "R", "#")),    # NEW
    0x24: OpSpec(0x24, "ORI",    ("R", "R", "#")),    # NEW
    0x25: OpSpec(0x25, "CMPI",   ("R", "#")),         # NEW: compare reg with imm

    # memory access --------------------------------------------------------------
    0x30: OpSpec(0x30, "STORE",      ("R", "A")),
    0x31: OpSpec(0x31, "LOAD_MEM",   ("R", "A")),
    0x32: OpSpec(0x32, "STOREI",     ("R", "R")),     # NEW: store Rs at addr in Rb
    0x33: OpSpec(0x33, "LOADI",      ("R", "R")),     # NEW: load from addr in Rs
    0x34: OpSpec(0x34, "STOREX",     ("R", "R", "#")),# NEW: indexed store base+offset
    0x35: OpSpec(0x35, "LOADX",      ("R", "R", "#")),# NEW: indexed load  base+offset

    # stack & subroutines --------------------------------------------------------
    0x40: OpSpec(0x40, "PUSH",   ("R",)),             # NEW
    0x41: OpSpec(0x41, "POP",    ("R",)),             # NEW
    0x42: OpSpec(0x42, "CALL",   ("A",)),             # NEW
    0x43: OpSpec(0x43, "RET",    ()),                 # NEW

    # system calls ---------------------------------------------------------------
    0x50: OpSpec(0x50, "SYSCALL", ("S",)),            # NEW
    0x51: OpSpec(0x51, "NOP",     ()),                # NEW
    0x52: OpSpec(0x52, "CLRS",    ()),                # NEW: clear Shadow flag (S=0)
}

# Reverse map for the assembler
MNEMONIC_TO_OPCODE: Dict[str, OpSpec] = {spec.mnemonic: spec for spec in ISA.values()}


# ── SYSCALL TABLE ────────────────────────────────────────────────────────────
#
# SYSCALL pulls its number from its operand. Convention:
#   1  PRINT_INT   — print signed integer in R0
#   2  PRINT_CHAR  — print Unicode char with code-point in R0
#   3  PRINT_STR   — print zero-terminated string from memory[R0..]
#   4  READ_INT    — read integer from input device into R0
#   5  EXIT        — set HALT (R0 = exit code)
#   6  PRINT_NL    — print a newline
#   7  DUMP_REGS   — diagnostic: print all registers + flags

SYSCALL_NAMES = {
    1: "PRINT_INT",
    2: "PRINT_CHAR",
    3: "PRINT_STR",
    4: "READ_INT",
    5: "EXIT",
    6: "PRINT_NL",
    7: "DUMP_REGS",
}


def describe(opcode: int) -> str:
    """Human-readable description of an opcode."""
    spec = ISA.get(opcode)
    if spec is None:
        return f"<UNKNOWN opcode 0x{opcode:02X}>"
    return f"0x{opcode:02X} {spec.mnemonic} {' '.join(spec.operands)}"
