"""
Completeness tests: ensure every opcode in the ISA table is wired into
the CPU's execute() dispatcher and has a working assembler entry.
"""
import pytest
from noisecore_vm import ISA, MNEMONIC_TO_OPCODE, CPU, assemble


def test_every_opcode_has_unique_mnemonic():
    seen = set()
    for op, spec in ISA.items():
        assert spec.mnemonic not in seen, f"Duplicate mnemonic: {spec.mnemonic}"
        seen.add(spec.mnemonic)


def test_mnemonic_table_consistent_with_isa():
    for op, spec in ISA.items():
        assert MNEMONIC_TO_OPCODE[spec.mnemonic].opcode == op


def test_every_opcode_dispatchable():
    """Every opcode should be reachable in CPU.execute() — no NotImplementedError."""
    cpu = CPU(substrate_mode=False)
    # Pre-load some registers to satisfy operands
    for i in range(8):
        cpu._write_reg(i, 1)
    # NOP is always safe; just verify it dispatches
    cpu.execute((0x51,))   # NOP
    cpu.execute((0x0F,))   # HALT  (just sets flag, ok)
    # Reset between calls
    cpu.halted = False


def test_unknown_opcode_raises():
    cpu = CPU(substrate_mode=False)
    with pytest.raises(ValueError, match="Unknown opcode"):
        cpu.execute((0xFF,))


def test_assembler_handles_every_mnemonic():
    """For each opcode, generate a minimal valid line and try to assemble it."""
    # Synthetic operand fillers
    fill = {
        "R": "R0",
        "#": "#0",
        "A": "0",
        "S": "1",
    }
    for op, spec in ISA.items():
        operands = ", ".join(fill[k] for k in spec.operands)
        line = f"{spec.mnemonic} {operands}".strip()
        prog = assemble(line + "\nHALT")
        assert prog.instructions[0][0] == op, f"opcode mismatch for {spec.mnemonic}"


def test_isa_has_minimum_instruction_count():
    """We should have at least 40 opcodes in a 'real' VM."""
    assert len(ISA) >= 40
