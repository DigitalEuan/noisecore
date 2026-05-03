"""Unit tests for memory instructions (0x30-0x35)."""
import pytest


def test_store_load_round_trip(cpu):
    cpu._op_load(0, 12345)
    cpu._op_store(0, 100)
    cpu._op_load(0, 0)
    cpu._op_load_mem(0, 100)
    assert cpu._read_reg(0) == 12345


def test_store_load_signed(cpu):
    cpu._op_load(0, -777)
    cpu._op_store(0, 50)
    cpu._op_load(0, 0)
    cpu._op_load_mem(0, 50)
    assert cpu._read_reg(0) == -777


def test_indexed_storei_loadi(cpu):
    """Address held in a register."""
    cpu._op_load(0, 42)
    cpu._op_load(1, 80)        # address
    cpu._op_storei(0, 1)       # mem[80] = 42
    cpu._op_load(0, 0)
    cpu._op_loadi(0, 1)
    assert cpu._read_reg(0) == 42


def test_indexed_storex_loadx(cpu):
    """Base + offset addressing."""
    cpu._op_load(0, 100)       # base
    cpu._op_load(1, 11); cpu._op_storex(1, 0, 0)
    cpu._op_load(1, 22); cpu._op_storex(1, 0, 1)
    cpu._op_load(1, 33); cpu._op_storex(1, 0, 2)

    cpu._op_loadx(2, 0, 0); assert cpu._read_reg(2) == 11
    cpu._op_loadx(2, 0, 1); assert cpu._read_reg(2) == 22
    cpu._op_loadx(2, 0, 2); assert cpu._read_reg(2) == 33


def test_memory_bounds_raises(cpu):
    with pytest.raises(IndexError):
        cpu._op_store(0, 9999)
    with pytest.raises(IndexError):
        cpu._op_load_mem(0, 9999)


def test_scratchpad_calculation(cpu):
    """Compute (7+8)*4 = 60 using memory."""
    cpu._op_load(0, 7); cpu._op_load(1, 8)
    cpu._op_add(2, 0, 1)
    cpu._op_store(2, 0)         # mem[0] = 15
    cpu._op_load(3, 4)
    cpu._op_load_mem(2, 0)      # restore 15
    cpu._op_mul(4, 2, 3)
    assert cpu._read_reg(4) == 60
