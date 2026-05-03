"""Unit tests for immediate-mode arithmetic (opcodes 0x20-0x25)."""


def test_addi(cpu):
    cpu._op_load(0, 10); cpu._op_addi(1, 0, 5)
    assert cpu._read_reg(1) == 15


def test_subi(cpu):
    cpu._op_load(0, 10); cpu._op_subi(1, 0, 3)
    assert cpu._read_reg(1) == 7


def test_subi_to_negative(cpu):
    cpu._op_load(0, 10); cpu._op_subi(1, 0, 15)
    assert cpu._read_reg(1) == -5


def test_muli(cpu):
    cpu._op_load(0, 10); cpu._op_muli(1, 0, 6)
    assert cpu._read_reg(1) == 60


def test_andi(cpu):
    cpu._op_load(0, 0xFF); cpu._op_andi(1, 0, 0x0F)
    assert cpu._read_reg(1) == 0x0F


def test_ori(cpu):
    cpu._op_load(0, 0xF0); cpu._op_ori(1, 0, 0x0F)
    assert cpu._read_reg(1) == 0xFF


def test_cmpi_equal(cpu):
    cpu._op_load(0, 42); cpu._op_cmpi(0, 42)
    assert cpu.flags["Z"] == 1


def test_cmpi_less(cpu):
    cpu._op_load(0, 5); cpu._op_cmpi(0, 10)
    assert cpu.flags["N"] == 1
