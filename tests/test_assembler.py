"""Unit tests for the symbolic assembler."""
import pytest
from noisecore_vm import assemble, AssemblerError, disassemble


def test_basic_assembly():
    prog = assemble("""
        LOAD R0, #5
        HALT
    """)
    assert prog.instructions == [(0x01, 0, 5), (0x0F,)]


def test_label_resolution():
    prog = assemble("""
        JMP done
        LOAD R0, #999
    done:
        HALT
    """)
    assert prog.labels["done"] == 2
    assert prog.instructions[0] == (0x10, 2)


def test_equ_constant():
    prog = assemble("""
        .equ MAX 100
        LOAD R0, MAX
        HALT
    """)
    assert prog.constants["MAX"] == 100
    assert prog.instructions[0] == (0x01, 0, 100)


def test_data_directive():
    prog = assemble("""
        .data nums 10 20 30
        LOAD R0, nums
        HALT
    """)
    assert prog.data_layout["nums"] == (0, [10, 20, 30])
    assert prog.instructions[0] == (0x01, 0, 0)   # nums starts at addr 0


def test_data_with_chars():
    prog = assemble("""
        .data msg 'H' 'I' 0
        LOAD R0, msg
        HALT
    """)
    layout = prog.data_layout["msg"]
    assert layout[1] == [ord('H'), ord('I'), 0]


def test_hex_immediate():
    prog = assemble("LOAD R0, #0xFF\nHALT")
    assert prog.instructions[0] == (0x01, 0, 255)


def test_binary_immediate():
    prog = assemble("LOAD R0, #0b1010\nHALT")
    assert prog.instructions[0] == (0x01, 0, 10)


def test_negative_immediate():
    prog = assemble("LOAD R0, #-42\nHALT")
    assert prog.instructions[0] == (0x01, 0, -42)


def test_char_immediate():
    prog = assemble("LOAD R0, 'A'\nHALT")
    assert prog.instructions[0] == (0x01, 0, ord('A'))


def test_unknown_mnemonic_raises():
    with pytest.raises(AssemblerError):
        assemble("FROBNICATE R0, R1\nHALT")


def test_arity_mismatch_raises():
    with pytest.raises(AssemblerError):
        assemble("ADD R0, R1\nHALT")    # ADD wants 3 operands


def test_bad_register_raises():
    with pytest.raises(AssemblerError):
        assemble("LOAD R99999, #5\nHALT")


def test_comments_stripped():
    prog = assemble("""
        ; full-line comment
        LOAD R0, #5    ; trailing comment
        HALT
    """)
    assert len(prog.instructions) == 2


def test_round_trip_disassemble_reassemble():
    src = """
    main:
        LOAD R0, #5
        ADD  R1, R0, R0
        JMP  main
        HALT
    """
    prog1 = assemble(src)
    asm_out = disassemble(prog1.instructions, labels=prog1.labels,
                          show_addresses=False)
    prog2 = assemble(asm_out)
    assert prog1.instructions == prog2.instructions
