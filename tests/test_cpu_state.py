"""Tests for CPU state management: reset, max_cycles, trace, fingerprint."""
import pytest
from noisecore_vm import CPU, assemble


def test_reset_clears_registers_and_flags():
    cpu = CPU(substrate_mode=False)
    cpu._op_load(0, 100)
    cpu._op_load(1, 200)
    cpu.flags["Z"] = 1
    cpu.pc = 50
    cpu.reset()
    assert cpu._read_reg(0) == 0
    assert cpu._read_reg(1) == 0
    assert cpu.flags == {"Z": 0, "C": 0, "V": 0, "N": 0, "S": 0}
    assert cpu.pc == 0
    assert not cpu.halted


def test_max_cycles_enforces_termination():
    cpu = CPU(substrate_mode=False, max_cycles=100)
    src = """
    loop:
        JMP loop
    """
    with pytest.raises(RuntimeError, match="max_cycles"):
        cpu.run(assemble(src).instructions)


def test_trace_recorded_when_enabled():
    cpu = CPU(substrate_mode=False, trace=True)
    src = """
        LOAD R0, #5
        ADDI R1, R0, #3
        HALT
    """
    cpu.run(assemble(src).instructions)
    assert len(cpu.trace) >= 3
    assert cpu.trace[0].mnemonic == "LOAD"


def test_trace_hash_reproducible():
    """Same program → same trace hash, every run."""
    src = """
        LOAD R0, #10
        LOAD R1, #20
        ADD  R2, R0, R1
        HALT
    """
    h1 = h2 = None
    for _ in range(2):
        cpu = CPU(substrate_mode=False, trace=True)
        info = cpu.run(assemble(src).instructions)
        h = info["trace_hash"]
        if h1 is None: h1 = h
        else: h2 = h
    assert h1 == h2


def test_format_state_returns_string():
    cpu = CPU(substrate_mode=False)
    cpu._op_load(0, 42)
    s = cpu.format_state()
    assert "R0: 42" in s
    assert "Flags:" in s


def test_run_returns_metadata():
    cpu = CPU(substrate_mode=False)
    src = "LOAD R0, #5\nHALT"
    info = cpu.run(assemble(src).instructions)
    assert info["cycles"] == 2
    assert info["halted"] is True
    assert "elapsed_s" in info
    assert "registers" in info
