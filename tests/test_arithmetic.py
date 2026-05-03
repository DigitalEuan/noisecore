"""Unit tests for arithmetic & logic instructions (opcodes 0x01-0x0E)."""
import pytest
from noisecore_vm import CPU


# ── LOAD / MOV ──────────────────────────────────────────────────────────────

def test_load_positive(cpu):
    cpu._op_load(0, 42)
    assert cpu._read_reg(0) == 42
    assert cpu.flags["Z"] == 0 and cpu.flags["N"] == 0


def test_load_zero_sets_z_flag(cpu):
    cpu._op_load(0, 0)
    assert cpu.flags["Z"] == 1


def test_load_negative_sets_n_flag(cpu):
    cpu._op_load(0, -7)
    assert cpu._read_reg(0) == -7
    assert cpu.flags["N"] == 1
    assert cpu.registers[0].read() == 7   # magnitude in substrate


def test_mov_preserves_sign(cpu):
    cpu._op_load(0, -99)
    cpu._op_mov(1, 0)
    assert cpu._read_reg(1) == -99


# ── ADD ─────────────────────────────────────────────────────────────────────

def test_add_positive(cpu):
    cpu._op_load(0, 10); cpu._op_load(1, 32)
    cpu._op_add(2, 0, 1)
    assert cpu._read_reg(2) == 42


def test_add_carry_flag_at_word_boundary(cpu):
    cpu._op_load(0, 0xFFFF); cpu._op_load(1, 1)
    cpu._op_add(2, 0, 1)
    assert cpu.flags["C"] == 1


def test_add_no_carry_in_range(cpu):
    cpu._op_load(0, 100); cpu._op_load(1, 200)
    cpu._op_add(2, 0, 1)
    assert cpu.flags["C"] == 0


def test_add_signs_chain(cpu):
    """The classical -7 + 2 = -5 chain that v1 failed."""
    cpu._op_load(0, 3); cpu._op_load(1, 10); cpu._op_load(2, 2)
    cpu._op_sub(3, 0, 1)        # R3 = -7
    cpu._op_add(4, 3, 2)        # R4 = -5
    assert cpu._read_reg(4) == -5


# ── SUB ─────────────────────────────────────────────────────────────────────

def test_sub_positive(cpu):
    cpu._op_load(0, 10); cpu._op_load(1, 4)
    cpu._op_sub(2, 0, 1)
    assert cpu._read_reg(2) == 6


def test_sub_underflow_to_negative(cpu):
    cpu._op_load(0, 5); cpu._op_load(1, 12)
    cpu._op_sub(2, 0, 1)
    assert cpu._read_reg(2) == -7
    assert cpu.flags["N"] == 1
    assert cpu.flags["C"] == 1


def test_sub_zero_sets_z_flag(cpu):
    cpu._op_load(0, 7); cpu._op_load(1, 7)
    cpu._op_sub(2, 0, 1)
    assert cpu.flags["Z"] == 1


# ── MUL ─────────────────────────────────────────────────────────────────────

def test_mul_positive(cpu):
    cpu._op_load(0, 12); cpu._op_load(1, 5)
    cpu._op_mul(2, 0, 1)
    assert cpu._read_reg(2) == 60


def test_mul_negative_negative_is_positive(cpu):
    cpu._op_load(0, -6); cpu._op_load(1, -7)
    cpu._op_mul(2, 0, 1)
    assert cpu._read_reg(2) == 42


def test_mul_positive_negative_is_negative(cpu):
    cpu._op_load(0, 8); cpu._op_load(1, -3)
    cpu._op_mul(2, 0, 1)
    assert cpu._read_reg(2) == -24


def test_mul_by_zero(cpu):
    cpu._op_load(0, 999); cpu._op_load(1, 0)
    cpu._op_mul(2, 0, 1)
    assert cpu._read_reg(2) == 0
    assert cpu.flags["Z"] == 1


# ── DIV / MOD ───────────────────────────────────────────────────────────────

def test_div_positive(cpu):
    cpu._op_load(0, 17); cpu._op_load(1, 4)
    cpu._op_div(2, 0, 1)
    assert cpu._read_reg(2) == 4


def test_div_truncates_toward_zero(cpu):
    cpu._op_load(0, -17); cpu._op_load(1, 4)
    cpu._op_div(2, 0, 1)
    assert cpu._read_reg(2) == -4


def test_div_by_zero_raises(cpu):
    cpu._op_load(0, 5); cpu._op_load(1, 0)
    with pytest.raises(ZeroDivisionError):
        cpu._op_div(2, 0, 1)


def test_mod_positive(cpu):
    cpu._op_load(0, 17); cpu._op_load(1, 4)
    cpu._op_mod(2, 0, 1)
    assert cpu._read_reg(2) == 1


def test_mod_sign_follows_dividend(cpu):
    cpu._op_load(0, -17); cpu._op_load(1, 4)
    cpu._op_mod(2, 0, 1)
    assert cpu._read_reg(2) == -1


def test_div_mod_round_trip(cpu):
    """(a/b)*b + a%b == a"""
    cpu._op_load(0, 100); cpu._op_load(1, 10)
    cpu._op_div(2, 0, 1); cpu._op_mul(3, 2, 1)
    cpu._op_mod(4, 0, 1); cpu._op_add(5, 3, 4)
    assert cpu._read_reg(5) == 100


# ── BITWISE ─────────────────────────────────────────────────────────────────

def test_bitwise_and(cpu):
    cpu._op_load(0, 0b1100); cpu._op_load(1, 0b1010)
    cpu._op_and(2, 0, 1)
    assert cpu._read_reg(2) == 0b1000


def test_bitwise_or(cpu):
    cpu._op_load(0, 0b1100); cpu._op_load(1, 0b1010)
    cpu._op_or(2, 0, 1)
    assert cpu._read_reg(2) == 0b1110


def test_bitwise_xor(cpu):
    cpu._op_load(0, 0b1100); cpu._op_load(1, 0b1010)
    cpu._op_xor(2, 0, 1)
    assert cpu._read_reg(2) == 0b0110


def test_bitwise_not_8bit():
    cpu = CPU(word_bits=8, substrate_mode=False)
    cpu._op_load(0, 0xFF)
    cpu._op_not(1, 0)
    assert cpu._read_reg(1) == 0


def test_bitwise_not_32bit():
    cpu = CPU(word_bits=32, substrate_mode=False)
    cpu._op_load(0, 0x0000FFFF)
    cpu._op_not(1, 0)
    assert cpu._read_reg(1) == 0xFFFF0000


def test_lsl(cpu):
    cpu._op_load(0, 1)
    cpu._op_lsl(1, 0, 8)
    assert cpu._read_reg(1) == 256


def test_lsr(cpu):
    cpu._op_load(0, 256)
    cpu._op_lsr(1, 0, 8)
    assert cpu._read_reg(1) == 1


# ── CMP ─────────────────────────────────────────────────────────────────────

def test_cmp_equal(cpu):
    cpu._op_load(0, 5); cpu._op_load(1, 5)
    cpu._op_cmp(0, 1)
    assert cpu.flags["Z"] == 1


def test_cmp_less(cpu):
    cpu._op_load(0, 3); cpu._op_load(1, 7)
    cpu._op_cmp(0, 1)
    assert cpu.flags["Z"] == 0
    assert cpu.flags["N"] == 1   # 3-7 = -4 < 0


def test_cmp_greater(cpu):
    cpu._op_load(0, 9); cpu._op_load(1, 4)
    cpu._op_cmp(0, 1)
    assert cpu.flags["Z"] == 0
    assert cpu.flags["N"] == 0


def test_cmp_does_not_modify_registers(cpu):
    cpu._op_load(0, 9); cpu._op_load(1, 4)
    cpu._op_cmp(0, 1)
    assert cpu._read_reg(0) == 9
    assert cpu._read_reg(1) == 4
