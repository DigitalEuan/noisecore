"""Unit tests for control-flow / branch instructions (0x10-0x1B)."""
from noisecore_vm import CPU, assemble


def _run(src):
    cpu = CPU(substrate_mode=False)
    prog = assemble(src).instructions
    info = cpu.run(prog, max_cycles=10_000)
    return cpu, info


def test_jmp_unconditional():
    cpu, _ = _run("""
        LOAD R0, #1
        JMP done
        LOAD R0, #999
    done:
        HALT
    """)
    assert cpu._read_reg(0) == 1


def test_jz_taken_when_zero():
    cpu, _ = _run("""
        LOAD R0, #5
        SUBI R0, R0, #5
        JZ   skip
        LOAD R0, #999
    skip:
        HALT
    """)
    assert cpu._read_reg(0) == 0


def test_jnz_taken_when_nonzero():
    cpu, _ = _run("""
        LOAD R0, #1
        JNZ  done
        LOAD R0, #999
    done:
        HALT
    """)
    assert cpu._read_reg(0) == 1


def test_jn_taken_when_negative():
    cpu, _ = _run("""
        LOAD R0, #5
        LOAD R1, #10
        SUB  R2, R0, R1
        JN   neg
        LOAD R3, #888
        HALT
    neg:
        LOAD R3, #42
        HALT
    """)
    assert cpu._read_reg(3) == 42


def test_je_taken_when_equal():
    cpu, _ = _run("""
        LOAD R0, #5
        LOAD R1, #5
        CMP  R0, R1
        JE   eq
        LOAD R2, #999
        HALT
    eq:
        LOAD R2, #1
        HALT
    """)
    assert cpu._read_reg(2) == 1


def test_jne_taken_when_unequal():
    cpu, _ = _run("""
        LOAD R0, #5
        LOAD R1, #6
        CMP  R0, R1
        JNE  ne
        LOAD R2, #999
        HALT
    ne:
        LOAD R2, #1
        HALT
    """)
    assert cpu._read_reg(2) == 1


def test_je_not_taken_when_unequal():
    cpu, _ = _run("""
        LOAD R0, #5
        LOAD R1, #6
        CMP  R0, R1
        JE   eq
        LOAD R2, #1     ; falls through
        HALT
    eq:
        LOAD R2, #999
        HALT
    """)
    assert cpu._read_reg(2) == 1


def test_jg_signed_greater():
    cpu, _ = _run("""
        LOAD R0, #10
        LOAD R1, #-5
        CMP  R0, R1
        JG   yes
        LOAD R2, #0
        HALT
    yes:
        LOAD R2, #1
        HALT
    """)
    assert cpu._read_reg(2) == 1


def test_jl_signed_less():
    cpu, _ = _run("""
        LOAD R0, #-5
        LOAD R1, #10
        CMP  R0, R1
        JL   yes
        LOAD R2, #0
        HALT
    yes:
        LOAD R2, #1
        HALT
    """)
    assert cpu._read_reg(2) == 1


def test_jge_equal_taken():
    cpu, _ = _run("""
        LOAD R0, #7
        LOAD R1, #7
        CMP  R0, R1
        JGE  yes
        LOAD R2, #0
        HALT
    yes:
        LOAD R2, #1
        HALT
    """)
    assert cpu._read_reg(2) == 1


def test_jle_equal_taken():
    cpu, _ = _run("""
        LOAD R0, #7
        LOAD R1, #7
        CMP  R0, R1
        JLE  yes
        LOAD R2, #0
        HALT
    yes:
        LOAD R2, #1
        HALT
    """)
    assert cpu._read_reg(2) == 1


def test_loop_sums_via_jnz():
    cpu, _ = _run("""
        LOAD R0, #5
        LOAD R1, #0
    loop:
        ADD  R1, R1, R0
        SUBI R0, R0, #1
        JNZ  loop
        HALT
    """)
    assert cpu._read_reg(1) == 15  # 5+4+3+2+1


def test_loop_until_negative_via_jn():
    cpu, _ = _run("""
        LOAD R0, #3
        LOAD R1, #0
    loop:
        ADDI R1, R1, #1
        SUBI R0, R0, #1
        JN   done            ; exit when R0 went negative
        JMP  loop
    done:
        HALT
    """)
    assert cpu._read_reg(1) == 4   # iterations: 3,2,1,0 then -1 → exits
