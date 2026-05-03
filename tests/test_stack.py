"""Unit tests for stack and subroutine instructions (0x40-0x43)."""
import pytest
from noisecore_vm import CPU, assemble


def test_push_pop_round_trip(cpu):
    cpu._op_load(0, 42)
    cpu._op_push(0)
    cpu._op_load(0, 0)
    cpu._op_pop(1)
    assert cpu._read_reg(1) == 42


def test_stack_lifo_order(cpu):
    cpu._op_load(0, 1); cpu._op_push(0)
    cpu._op_load(0, 2); cpu._op_push(0)
    cpu._op_load(0, 3); cpu._op_push(0)

    cpu._op_pop(1); assert cpu._read_reg(1) == 3
    cpu._op_pop(1); assert cpu._read_reg(1) == 2
    cpu._op_pop(1); assert cpu._read_reg(1) == 1


def test_sp_decrements_on_push(cpu):
    sp_before = cpu._read_reg(cpu.SP_REGISTER)
    cpu._op_load(0, 99)
    cpu._op_push(0)
    sp_after = cpu._read_reg(cpu.SP_REGISTER)
    assert sp_after == sp_before - 1


def test_call_ret_round_trip():
    """A function that doubles its argument."""
    cpu = CPU(substrate_mode=False)
    src = """
        LOAD R0, #21
        CALL doubler
        HALT
    doubler:
        ADD R0, R0, R0
        RET
    """
    prog = assemble(src).instructions
    cpu.run(prog)
    assert cpu._read_reg(0) == 42


def test_recursive_call():
    """Recursive sum 1..n."""
    cpu = CPU(substrate_mode=False)
    src = """
        LOAD R0, #5
        CALL sum
        HALT
    sum:
        CMPI R0, 0
        JE   sum_base
        PUSH R0
        SUBI R0, R0, #1
        CALL sum
        POP  R1
        ADD  R0, R0, R1
        RET
    sum_base:
        RET
    """
    prog = assemble(src).instructions
    cpu.run(prog)
    assert cpu._read_reg(0) == 15   # 1+2+3+4+5


def test_ret_with_empty_stack_raises(cpu):
    with pytest.raises(RuntimeError):
        cpu._op_ret()


def test_pop_underflow_raises(cpu):
    """SP starts at memory_size-1; pop tries to read beyond memory."""
    cpu._write_reg(cpu.SP_REGISTER, cpu.memory_size - 1)
    with pytest.raises(OverflowError):
        cpu._op_pop(0)
