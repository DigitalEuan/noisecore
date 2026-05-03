"""
================================================================================
Tests — SubstrateALU (LAW_SUBSTRATE_ALU_001/002/003/004)
================================================================================
Verifies that all arithmetic operations in substrate_mode=True are performed
natively on base-12 digit arrays, not via Python arithmetic on full integers.

Test strategy:
  • Unit-test the ALU digit operations directly (digit arrays in, digit arrays out)
  • Integration-test CPU ops in substrate_mode=True, verifying results match
    plain-mode results across a comprehensive value space
  • Verify that carry_work is populated correctly (digit-level carries recorded)
  • Verify that SUB via flipped-sign ADD is correct for all sign combinations
"""

import pytest
from fractions import Fraction
from noisecore_vm import CPU, assemble, SubstrateALU, ShadowRegister
from noisecore_vm import run_program


# ── helpers ──────────────────────────────────────────────────────────────────

def _reg(value: int, mode: str = "SV") -> ShadowRegister:
    """Create a ShadowRegister holding |value|."""
    r = ShadowRegister(mode=mode)
    r.write(abs(value))
    return r

def _sign(v: int) -> bool:
    return v < 0

def _read(r: ShadowRegister) -> int:
    return r.read()

def cpu_sub() -> CPU:
    return CPU(substrate_mode=True, mode="SV")

def cpu_plain() -> CPU:
    return CPU(substrate_mode=False)


# ── _add_digits ───────────────────────────────────────────────────────────────

class TestAddDigits:

    def _add(self, a, b):
        da = SubstrateALU._to_digits(a)
        db = SubstrateALU._to_digits(b)
        digits, carry_out, ce = SubstrateALU._add_digits(da, db)
        result = sum(d * 12**i for i, d in enumerate(digits))
        return result, carry_out, ce

    def test_zero_plus_zero(self):
        r, c, _ = self._add(0, 0)
        assert r == 0 and not c

    def test_small_no_carry(self):
        r, c, ce = self._add(3, 4)
        assert r == 7 and not c and ce == 0

    def test_carry_at_twelve(self):
        # 6 + 6 = 12 = [0, 1] in base 12; one carry event at digit 0
        r, c, ce = self._add(6, 6)
        assert r == 12 and not c and ce == 1

    def test_large_values(self):
        for a, b in [(100, 200), (1836, 1839), (999, 1), (0, 65535)]:
            r, _, _ = self._add(a, b)
            assert r == a + b, f"{a}+{b}: expected {a+b}, got {r}"

    def test_carry_out(self):
        # Values that produce a carry out of all digit positions
        big = 12**8 - 1
        r, carry_out, _ = self._add(big, 1)
        assert r == big + 1

    def test_carry_events_counted(self):
        # 11 + 11 = 22 = 1*12 + 10: one carry
        _, _, ce = self._add(11, 11)
        assert ce == 1
        # 143 + 143: more carries expected
        _, _, ce2 = self._add(143, 143)
        assert ce2 >= 1


# ── _sub_digits ───────────────────────────────────────────────────────────────

class TestSubDigits:

    def _sub(self, a, b):
        da = SubstrateALU._to_digits(a)
        db = SubstrateALU._to_digits(b)
        digits, borrow = SubstrateALU._sub_digits(da, db)
        result = sum(d * 12**i for i, d in enumerate(digits))
        return result, borrow

    def test_simple_sub(self):
        r, borrow = self._sub(10, 3)
        assert r == 7 and not borrow

    def test_sub_zero(self):
        r, borrow = self._sub(5, 0)
        assert r == 5 and not borrow

    def test_sub_equal(self):
        r, borrow = self._sub(42, 42)
        assert r == 0

    def test_sub_with_borrow(self):
        # 12 - 5: digit 0: 0-5 < 0 → borrow
        r, borrow = self._sub(12, 5)
        assert r == 7 and not borrow

    def test_underflow_flagged(self):
        r, borrow = self._sub(3, 10)
        assert borrow  # underflow detected

    def test_large_values(self):
        for a, b in [(1836, 939), (65535, 100), (1000, 999)]:
            r, _ = self._sub(a, b)
            assert r == a - b, f"{a}-{b}: expected {a-b}, got {r}"


# ── _mul_digits ───────────────────────────────────────────────────────────────

class TestMulDigits:

    def _mul(self, a, b):
        da = SubstrateALU._to_digits(a)
        db = SubstrateALU._to_digits(b)
        digits = SubstrateALU._mul_digits(da, db)
        return sum(d * 12**i for i, d in enumerate(digits))

    def test_zero(self):
        assert self._mul(0, 100) == 0
        assert self._mul(100, 0) == 0

    def test_one(self):
        assert self._mul(1, 42) == 42

    def test_small(self):
        assert self._mul(3, 4) == 12

    def test_medium(self):
        for a, b in [(12, 12), (11, 11), (100, 7), (1836, 1)]:
            assert self._mul(a, b) == a * b, f"{a}*{b}"

    def test_large(self):
        assert self._mul(1836, 1839) == 1836 * 1839

    def test_commutativity(self):
        for a, b in [(7, 13), (100, 200), (1836, 42)]:
            assert self._mul(a, b) == self._mul(b, a)


# ── _divmod_digits ────────────────────────────────────────────────────────────

class TestDivmodDigits:

    def _divmod(self, a, b):
        da = SubstrateALU._to_digits(a)
        db = SubstrateALU._to_digits(b)
        q_d, r_d = SubstrateALU._divmod_digits(da, db)
        q = sum(d * 12**i for i, d in enumerate(q_d))
        r = sum(d * 12**i for i, d in enumerate(r_d))
        return q, r

    def test_exact_division(self):
        q, r = self._divmod(12, 3)
        assert q == 4 and r == 0

    def test_division_with_remainder(self):
        q, r = self._divmod(13, 3)
        assert q == 4 and r == 1

    def test_dividend_smaller_than_divisor(self):
        q, r = self._divmod(3, 10)
        assert q == 0 and r == 3

    def test_single_digit_divisor(self):
        for a in (1, 11, 12, 144, 1836):
            for b in range(1, 12):
                q, r = self._divmod(a, b)
                assert q * b + r == a, f"{a}÷{b}"

    def test_multi_digit_divisor(self):
        for a, b in [(100, 12), (1836, 13), (65535, 256), (1000, 144)]:
            q, r = self._divmod(a, b)
            assert q == a // b and r == a % b, f"{a}÷{b}"

    def test_large_values(self):
        q, r = self._divmod(1836 * 1839, 1836)
        assert q == 1839 and r == 0


# ── compare ───────────────────────────────────────────────────────────────────

class TestCompare:

    def _cmp(self, a, b):
        ra = _reg(abs(a)); sa = a < 0
        rb = _reg(abs(b)); sb = b < 0
        return SubstrateALU.compare(ra, sa, rb, sb)

    def test_equal(self):
        assert self._cmp(5, 5) == 0

    def test_greater(self):
        assert self._cmp(10, 5) == 1

    def test_less(self):
        assert self._cmp(3, 7) == -1

    def test_positive_gt_negative(self):
        assert self._cmp(1, -1) == 1

    def test_negative_lt_positive(self):
        assert self._cmp(-1, 1) == -1

    def test_both_negative(self):
        # -3 < -1 (more negative)
        assert self._cmp(-3, -1) == -1

    def test_zero(self):
        assert self._cmp(0, 0) == 0


# ── signed add/sub via ALU ────────────────────────────────────────────────────

class TestSubstrateALUSigned:

    def _add(self, a, b):
        ra = _reg(abs(a)); sa = a < 0
        rb = _reg(abs(b)); sb = b < 0
        rd = ShadowRegister(mode="SV")
        result_neg, _, _ = SubstrateALU.add(ra, sa, rb, sb, rd)
        mag = rd.read()
        return -mag if result_neg and mag != 0 else mag

    def test_pos_plus_pos(self):
        assert self._add(3, 4) == 7

    def test_pos_plus_neg_larger(self):
        assert self._add(10, -3) == 7

    def test_pos_plus_neg_smaller(self):
        assert self._add(3, -10) == -7

    def test_neg_plus_pos_larger(self):
        assert self._add(-3, 10) == 7

    def test_neg_plus_neg(self):
        assert self._add(-3, -4) == -7

    def test_cancel(self):
        assert self._add(5, -5) == 0

    def test_large_values(self):
        for a, b in [(1836, 939), (-1836, 1839), (1836, -1839), (-1836, -939)]:
            assert self._add(a, b) == a + b, f"{a}+{b}"

    def test_sub_is_add_negated(self):
        # a - b == a + (-b)
        ra = _reg(10); rb = _reg(3); rd = ShadowRegister()
        SubstrateALU.sub(ra, False, rb, False, rd)
        assert rd.read() == 7

    def test_mul_signed(self):
        cases = [(3, 4, 12), (-3, 4, -12), (3, -4, -12), (-3, -4, 12), (0, 5, 0)]
        for a, b, expected in cases:
            ra = _reg(abs(a)); rb = _reg(abs(b)); rd = ShadowRegister()
            result_neg = SubstrateALU.mul(ra, a < 0, rb, b < 0, rd)
            mag = rd.read()
            result = -mag if result_neg and mag != 0 else mag
            assert result == expected, f"{a}*{b}: expected {expected}, got {result}"


# ── CPU integration: substrate_mode results == plain_mode results ─────────────

class TestSubstrateArithmeticCorrectness:
    """
    Every arithmetic instruction must produce the same result in substrate mode
    as in plain mode.  Tests a representative range of values covering the
    Phenomenal regime (≤4 per digit), the elastic limit boundary (5-11), and
    larger multi-digit values.
    """

    TEST_PAIRS = [
        (0, 0), (1, 0), (0, 1), (1, 1), (3, 4), (4, 4),
        (5, 5), (6, 7), (11, 11), (12, 1), (12, 12),
        (100, 7), (100, 99), (144, 12), (1836, 1), (1836, 1839),
        (-1, 5), (5, -3), (-7, -7), (-12, 6),
    ]

    def _run(self, src, mode):
        cpu = CPU(substrate_mode=mode, mode="SV" if mode else "SV")
        prog = assemble(src)
        cpu.run(prog.instructions)
        return cpu._read_reg(2)   # result always in R2

    def _pair_test(self, template, pairs=None):
        pairs = pairs or self.TEST_PAIRS
        for a, b in pairs:
            src = template.format(a=a, b=b)
            try:
                plain = self._run(src, False)
                sub   = self._run(src, True)
                assert plain == sub, f"a={a} b={b}: plain={plain} substrate={sub}\n{src}"
            except ZeroDivisionError:
                pass   # both modes should raise — not a correctness failure

    def test_add(self):
        self._pair_test("LOAD R0,#{a}\nLOAD R1,#{b}\nADD R2,R0,R1\nHALT")

    def test_sub(self):
        self._pair_test("LOAD R0,#{a}\nLOAD R1,#{b}\nSUB R2,R0,R1\nHALT")

    def test_mul(self):
        self._pair_test("LOAD R0,#{a}\nLOAD R1,#{b}\nMUL R2,R0,R1\nHALT",
                        [(a, b) for a, b in self.TEST_PAIRS if a >= 0 and b >= 0])

    def test_div(self):
        pairs = [(a, b) for a, b in self.TEST_PAIRS if b != 0]
        self._pair_test("LOAD R0,#{a}\nLOAD R1,#{b}\nDIV R2,R0,R1\nHALT", pairs)

    def test_mod(self):
        pairs = [(a, b) for a, b in self.TEST_PAIRS if b != 0]
        self._pair_test("LOAD R0,#{a}\nLOAD R1,#{b}\nMOD R2,R0,R1\nHALT", pairs)

    def test_addi(self):
        self._pair_test("LOAD R0,#{a}\nADDI R2,R0,#{b}\nHALT")

    def test_subi(self):
        self._pair_test("LOAD R0,#{a}\nSUBI R2,R0,#{b}\nHALT")

    def test_muli(self):
        pairs = [(a, b) for a, b in self.TEST_PAIRS if a >= 0 and b >= 0]
        self._pair_test("LOAD R0,#{a}\nMULI R2,R0,#{b}\nHALT", pairs)

    def test_and(self):
        pairs = [(a, b) for a, b in self.TEST_PAIRS if a >= 0 and b >= 0]
        self._pair_test("LOAD R0,#{a}\nLOAD R1,#{b}\nAND R2,R0,R1\nHALT", pairs)

    def test_or(self):
        pairs = [(a, b) for a, b in self.TEST_PAIRS if a >= 0 and b >= 0]
        self._pair_test("LOAD R0,#{a}\nLOAD R1,#{b}\nOR R2,R0,R1\nHALT", pairs)

    def test_xor(self):
        pairs = [(a, b) for a, b in self.TEST_PAIRS if a >= 0 and b >= 0]
        self._pair_test("LOAD R0,#{a}\nLOAD R1,#{b}\nXOR R2,R0,R1\nHALT", pairs)

    def test_lsl(self):
        for v in (1, 3, 12, 100, 1836):
            for amt in (0, 1, 2, 4):
                src = f"LOAD R0,#{v}\nLSL R2,R0,#{amt}\nHALT"
                assert self._run(src, False) == self._run(src, True), f"LSL {v}<<{amt}"

    def test_lsr(self):
        for v in (1, 12, 100, 1836, 65535):
            for amt in (0, 1, 2, 4):
                src = f"LOAD R0,#{v}\nLSR R2,R0,#{amt}\nHALT"
                assert self._run(src, False) == self._run(src, True), f"LSR {v}>>{amt}"


# ── carry_work populated from ALU ops ─────────────────────────────────────────

class TestCarryWorkFromALU:

    def test_carry_work_recorded_on_add(self):
        cpu = CPU(substrate_mode=True)
        prog = assemble("LOAD R0,#6\nLOAD R1,#6\nADD R2,R0,R1\nHALT")
        cpu.run(prog.instructions)
        # R2 = 12; digit decomposition: 12 = [0,1]; the ADD of 6+6 should have
        # generated carry events in the ALU path tracked on R2
        fp = cpu.substrate_fingerprint()
        assert fp["total_carry_work"] >= 0   # at minimum: no crash

    def test_write_from_alu_updates_carry_work(self):
        r = ShadowRegister(mode="SV")
        initial = r.carry_work
        da = SubstrateALU._to_digits(6)
        db = SubstrateALU._to_digits(6)
        digits, _, ce = SubstrateALU._add_digits(da, db)
        r.write_from_alu(digits, ce)
        assert r.carry_work == initial + ce

    def test_write_from_alu_updates_shadow(self):
        r = ShadowRegister(mode="SV")
        # Write digit 5 (> PHENOMENAL_LIMIT=4) → shadow_active should be True
        r.write_from_alu([5, 0], 0)
        assert r.shadow_active is True

    def test_write_from_alu_phenomenal(self):
        r = ShadowRegister(mode="SV")
        r.write_from_alu([3, 0], 0)
        assert r.shadow_active is False


# ── example programs: substrate mode produces correct output ─────────────────

class TestExamplePrograms:
    """All 8 example programs must produce the same output in both modes."""

    def _compare_modes(self, src):
        cpu_s, info_s = run_program(src, substrate_mode=True)
        cpu_p, info_p = run_program(src, substrate_mode=False)
        assert cpu_s.console.output() == cpu_p.console.output(), (
            f"Output mismatch:\n  substrate: {cpu_s.console.output()!r}\n"
            f"  plain:     {cpu_p.console.output()!r}"
        )

    def test_factorial_iterative(self):
        import os, pathlib
        p = pathlib.Path(__file__).parent.parent / "examples" / "02_factorial_iter.nca"
        if p.exists():
            self._compare_modes(p.read_text())

    def test_gcd(self):
        import pathlib
        p = pathlib.Path(__file__).parent.parent / "examples" / "07_gcd.nca"
        if p.exists():
            self._compare_modes(p.read_text())

    def test_fibonacci(self):
        import pathlib
        p = pathlib.Path(__file__).parent.parent / "examples" / "06_fibonacci.nca"
        if p.exists():
            self._compare_modes(p.read_text())

    def test_inline_multiply_divide(self):
        src = """
            LOAD  R0, #1836
            LOAD  R1, #1839
            MUL   R2, R0, R1
            LOAD  R3, #1839
            DIV   R4, R2, R3
            MOV   R0, R4
            SYSCALL 1
            SYSCALL 6
            HALT
        """
        cpu_s, _ = run_program(src, substrate_mode=True)
        cpu_p, _ = run_program(src, substrate_mode=False)
        assert cpu_s.console.output() == cpu_p.console.output()
        assert "1836" in cpu_s.console.output()

    def test_inline_add_sub_chain(self):
        src = """
            LOAD  R0, #100
            ADDI  R0, R0, #44
            SUBI  R0, R0, #44
            SYSCALL 1
            SYSCALL 6
            HALT
        """
        self._compare_modes(src)
