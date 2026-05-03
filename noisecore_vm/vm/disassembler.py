"""
================================================================================
NoiseCore VM — Disassembler
================================================================================
Inverse of the assembler: bytecode → human-readable assembly text.

Used for:
  • Round-trip testing  (assemble → disassemble → assemble → equal bytecode)
  • Debugging running programs
  • Generating documentation samples
"""

from __future__ import annotations
from typing import List, Tuple, Dict

from .isa import ISA, SYSCALL_NAMES


def disassemble(program: List[Tuple],
                labels: Dict[str, int] = None,
                show_addresses: bool = True) -> str:
    """
    Render a list of instruction tuples as assembly text.

    Parameters
    ----------
    program : list of instruction tuples (opcode, *args)
    labels  : optional mapping {name: address}; reverse-lookup is used
              to print labels at their target addresses and at jump operands.
    show_addresses : prepend each line with a 4-digit address.
    """
    addr_to_label: Dict[int, str] = {}
    if labels:
        for name, addr in labels.items():
            addr_to_label[addr] = name

    lines: List[str] = []
    for addr, instr in enumerate(program):
        opcode = instr[0]
        spec = ISA.get(opcode)

        # Print label if any
        if addr in addr_to_label:
            lines.append(f"{addr_to_label[addr]}:")

        if spec is None:
            asm = f"DB 0x{opcode:02X}  ; <unknown>"
        else:
            operand_strs = []
            for kind, val in zip(spec.operands, instr[1:]):
                if kind == "R":
                    operand_strs.append(f"R{val}")
                elif kind == "#":
                    operand_strs.append(f"#{val}")
                elif kind == "A":
                    if val in addr_to_label:
                        operand_strs.append(addr_to_label[val])
                    else:
                        operand_strs.append(str(val))
                elif kind == "S":
                    name = SYSCALL_NAMES.get(val, "?")
                    operand_strs.append(f"{val}  ; {name}")
                else:
                    operand_strs.append(str(val))
            asm = f"{spec.mnemonic:<8} {', '.join(operand_strs)}"

        prefix = f"  {addr:04d}:  " if show_addresses else "    "
        lines.append(f"{prefix}{asm}")

    return "\n".join(lines)
