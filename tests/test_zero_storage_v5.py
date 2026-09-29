"""
Zero-storage v5 verification — every Lean theorem in ZeroStorageV5.lean has
an executable check here.  No stored tables are consulted anywhere in these
tests; the ledger's `table_lookup` counter is asserted zero at the end.
"""
from fractions import Fraction
import random

import pytest

from noisecore_vm.core.syndrome import (
    syndrome, syndrome_h, is_golay, is_leech, in_coset, leech_mask,
    bits_to_word, word_to_bits, SELF_DUAL_VERIFIED,
)
from noisecore_vm.core.golay_engine import GOLAY_ENGINE
from noisecore_vm.ledger import Ledger, LEDGER_ITEMS
from noisecore_vm.decoder import decode, decode_exhaustive, SCALE
from noisecore_vm.moving_ds import MovingDeltaSigma
from noisecore_vm.nrci import (
    nrci, nrci_enclosure, ds_average_stream, dyadic_tower_stream,
)
from noisecore_vm import CPU, assemble, run_program


# ── §1 syndromeZero_iff_isGolay ─────────────────────────────────────────────

class TestSyndromeIsMembership:
    def test_self_dual_verified_at_import(self):
        assert SELF_DUAL_VERIFIED is True

    def test_every_codeword_has_zero_syndrome(self):
        """synZero_of_isGolay — all 4096 codewords pass all twelve checks."""
        for cw in GOLAY_ENGINE.get_all_codewords():
            assert syndrome(bits_to_word(cw)) == 0

    def test_zero_syndrome_iff_codeword_sampled(self):
        """isGolay_of_synZero on a random sample, both routes agree."""
        rng = random.Random(24)
        for _ in range(4096):
            w = rng.getrandbits(24)
            assert (syndrome(w) == 0) == (syndrome_h(w) == 0)

    def test_weight_one_word_is_not_codeword(self):
        assert is_golay(0) is True
        assert is_golay(1) is False
        assert is_golay(0x800000) is False

    def test_universe_and_octads_are_codewords(self):
        assert is_golay(0xFFFFFF) is True                     # weight 24
        for octad in GOLAY_ENGINE.get_octads()[:50]:          # weight 8
            assert is_golay(bits_to_word(octad)) is True

    def test_syndrome_is_12_bits(self):
        rng = random.Random(7)
        for _ in range(256):
            assert 0 <= syndrome(rng.getrandbits(24)) < 4096


# ── §1 syndromeSieve_iff_isLeech ────────────────────────────────────────────

class TestLeechSieve:
    def test_alltwos_witness(self):
        """allTwos_inCoset: (2,…,2) lies in coset (m=0, codeword 0)."""
        x = [2] * 24
        m, mask = leech_mask(x)
        # VM mask convention: bit set when 4 ∤ (x−m), so (2,…,2) → universe word.
        # Universe IS a codeword, and 48 ≡ 0 (mod 8), so the point is Leech.
        assert (m, mask) == (0, 0xFFFFFF)
        assert is_leech(x) is True
        assert in_coset(x, 0, 0xFFFFFF) is True

    def test_frame_vectors(self):
        """(±4, ±4, 0²²) are minimal vectors."""
        for s1 in (4, -4):
            for s2 in (4, -4):
                x = [0] * 24
                x[0], x[5] = s1, s2
                assert is_leech(x) is True

    def test_octad_vectors(self):
        """(±2^8 on an octad, 0¹⁶) with an even number of minus signs."""
        oct = GOLAY_ENGINE.get_octads()[0]
        positions = [i for i, b in enumerate(oct) if b]
        assert len(positions) == 8
        x = [0] * 24
        for p in positions:
            x[p] = 2
        assert is_leech(x) is True
        # two minus signs: still Leech
        x[positions[0]] = -2
        x[positions[1]] = -2
        assert is_leech(x) is True
        # one minus sign: mod-8 sum breaks
        x[positions[1]] = 2
        assert is_leech(x) is False

    def test_three_one_vector(self):
        """(3, −1⁷ on octad\{0}, +1¹⁶) is a Leech minimal vector."""
        octs = GOLAY_ENGINE.get_octads()
        oct0 = next(o for o in octs if o[0] == 1)          # contains coord 0
        positions = [i for i, b in enumerate(oct0) if b]
        assert positions[0] == 0
        x = [1] * 24
        x[0] = 3
        for p in positions[1:]:
            x[p] = -1
        assert is_leech(x) is True

    def test_all_ones_is_not_leech(self):
        assert is_leech([1] * 24) is False                  # sum ≡ 0 ≢ 4 (mod 8)

    def test_parity_mismatch_rejected(self):
        x = [2] * 24
        x[3] = 3
        assert is_leech(x) is False

    def test_off_coset_rejected(self):
        """A valid-parity point whose mask is not a codeword is not Leech."""
        x = [2] + [0] * 23                                  # mask = weight 1
        assert is_leech(x) is False


# ── §2 the register tracks a moving target ───────────────────────────────────

class TestMovingDeltaSigma:
    def test_accumulator_bounded_on_ramp(self):
        """dsAcc_mem_Ico across a 6-target schedule (asserted inside tick too)."""
        mds = MovingDeltaSigma(Fraction(1, 7))
        for k in range(6):
            mds.retarget(Fraction(k + 1, 10))
            mds.run(80)
        assert Fraction(0) <= mds.acc < Fraction(1)

    def test_count_identity_exact(self):
        """dsAcc_eq: Σ bits = Σ targets − accumulator, exactly."""
        mds = MovingDeltaSigma(Fraction(2, 7))
        mds.run(100)
        mds.retarget(Fraction(5, 11))
        mds.run(200)
        assert Fraction(mds.sum_bits) == mds.sum_targets - mds.acc

    def test_track_bound_holds(self):
        """ds_track_bound: |avg − mean target| < 1/N on a moving target."""
        mds = MovingDeltaSigma(Fraction(1, 5))
        mds.run(128)
        mds.retarget(Fraction(3, 5))
        mds.run(128)
        assert mds.n == 256
        assert mds.track_bound_holds() is True

    def test_moving_error_decomposition(self):
        """ds_track_moving_target: |avg − s| ≤ 1/N + mean|tᵢ − s|."""
        mds = MovingDeltaSigma(Fraction(1, 7))
        mds.run(200)
        mds.retarget(Fraction(6, 7))
        mds.run(200)
        s = Fraction(1, 2)
        assert mds.error_against(s) <= mds.moving_error_bound(s)

    def test_retarget_preserves_phase(self):
        """Retargeting must NOT zero the accumulator (the v5 gene)."""
        mds = MovingDeltaSigma(Fraction(1, 3))
        mds.run(5)
        acc_before = mds.acc
        mds.retarget(Fraction(2, 3))
        assert mds.acc == acc_before


# ── §3–§4 the decoder returns the nearest point of the lattice ───────────────

class TestCosetDecoder:
    def test_zero_target_decodes_to_origin(self):
        res = decode([0] * 24)
        assert res["point"] == [0] * 24
        assert res["cost"] == 0

    def test_alltwos_target_decodes_to_alltwos(self):
        res = decode([2 * SCALE] * 24)
        assert res["point"] == [2] * 24
        assert res["cost"] == 0

    def test_decode_returns_leech_point(self):
        rng = random.Random(196560)
        for _ in range(4):
            target = [rng.randint(-4 * SCALE, 4 * SCALE) for _ in range(24)]
            res = decode(target)
            assert is_leech(res["point"]) is True

    def test_pruned_agrees_with_exhaustive(self):
        """§4 executable: early-abort pruning never changes the answer."""
        rng = random.Random(8192)
        for _ in range(3):
            target = [rng.randint(-3 * SCALE, 3 * SCALE) for _ in range(24)]
            a = decode(target)
            b = decode_exhaustive(target)
            assert a["point"] == b["point"]
            assert a["cost"] == b["cost"]
            assert a["trials"] == 8192 and b["trials"] == 8192
            assert a["pruned"] > 0          # the pruning actually fires

    def test_decode_closer_than_integer_rounding(self):
        """Nearest lattice point beats naive rounding on a crafted target."""
        target = [int(1.9 * SCALE)] * 24
        res = decode(target)
        naive_cost = sum((SCALE * 2 - t) ** 2 for t in target)
        assert res["cost"] <= naive_cost


# ── ledger ──────────────────────────────────────────────────────────────────

class TestLedger:
    def test_items_match_v5(self):
        assert len(LEDGER_ITEMS) == 13
        assert LEDGER_ITEMS[7] == "table_lookup"

    def test_syndrome_costs_twelve_parities(self):
        led = Ledger()
        syndrome(0x123456, led)
        assert led.count("parity_check") == 12
        assert led.count("popcount") == 12
        assert led.count("table_lookup") == 0

    def test_decode_ledger_shape(self):
        led = Ledger()
        decode([SCALE] * 24, ledger=led)
        assert led.count("coset_trial") == 8192
        assert led.count("word_xor") == 8192
        assert led.count("coordinate_pass") > 0
        assert led.count("table_lookup") == 0
        assert led.count("coset_pruned") > 0

    def test_storage_audit_zero_lookups(self):
        led = Ledger()
        syndrome(0xABC, led); is_golay(0xABC, led)
        decode([0] * 24, ledger=led)
        assert "ratio" in led.storage_audit()
        assert led.count("table_lookup") == 0


# ── NRCI (one definition, dyadic enclosure) ─────────────────────────────────

class TestNRCI:
    def test_zero_residual_is_one(self):
        lo, hi = nrci([1, 2, 3], [0, 0, 0])
        assert lo == hi == Fraction(1)

    def test_enclosure_width(self):
        lo, hi = nrci([100, 200, 300], [3, 1, 4])
        assert hi - lo == Fraction(1, 2**32)
        assert lo <= hi

    def test_enclosure_brackets_value(self):
        x = [7, 11, 13, 17]
        r = [1, 0, 1, 2]
        lo, hi = nrci(x, r)
        xs, rs = sum(v*v for v in x), sum(v*v for v in r)
        import math
        val = 1 - math.sqrt(rs / xs)
        assert float(lo) <= val <= float(hi)

    def test_ds_stream_bound_and_nrci(self):
        """The v5 stream: Δ-Σ average, target 2/7, N=512."""
        out = ds_average_stream(Fraction(2, 7), 512)
        assert out["bound_ok"] is True
        assert 0.9 < out["nrci_mid"] < 1.0

    def test_dyadic_tower_stream(self):
        out = dyadic_tower_stream(16)
        assert 0.0 < out["nrci_mid"] < 1.0


# ── ISA-level integration ───────────────────────────────────────────────────

class TestOpcodes:
    def test_syn_isgolay(self):
        cpu = CPU(substrate_mode=False)
        src = """
            LOAD    R0, #0
            ISGOLAY R1, R0
            LOAD    R0, #1
            ISGOLAY R2, R0
            HALT
        """
        cpu.run(assemble(src).instructions)
        assert cpu._read_reg(1) == 1
        assert cpu._read_reg(2) == 0
        assert cpu.ledger.count("parity_check") == 24
        assert cpu.ledger.count("table_lookup") == 0

    def test_decode_opcode_on_zero_target(self):
        cpu, _ = run_program("""
.data tgt 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
            LOAD    R3, tgt
            DECODE  R4, R3
            LOAD_MEM R5, tgt
            HALT
        """, substrate_mode=False)
        assert cpu._read_reg(4) == 0      # cost 0
        assert cpu._read_reg(5) == 0      # coord 0 is 0

    def test_mdsbit_mdsrt(self):
        cpu = CPU(substrate_mode=False)
        src = """
            MDSRT   #1, #7
            MDSBIT  R0
            MDSBIT  R1
            MDSBIT  R2
            MDSBIT  R3
            MDSBIT  R4
            MDSBIT  R5
            MDSBIT  R6
            HALT
        """
        cpu.run(assemble(src).instructions)
        bits = [cpu._read_reg(i) for i in range(7)]
        assert bits == [0, 0, 0, 0, 0, 0, 1]      # 1/7 wobble, 7 ticks
        assert cpu.ledger.count("ds_tick") == 7

    def test_ledger_and_cost_opcodes(self):
        cpu, _ = run_program("""
            LOAD    R0, #0
            ISGOLAY R1, R0
            LEDGER  R2, #0
            COST    R3
            HALT
        """, substrate_mode=False)
        assert cpu._read_reg(2) == 12            # parity_check count
        assert cpu._read_reg(3) == cpu.ledger.total()


def test_example_11_zero_storage():
    import os
    ex = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "examples", "11_zero_storage_decode.nca")
    with open(ex) as f:
        src = f.read()
    cpu, info = run_program(src, substrate_mode=False, max_cycles=5_000_000)
    assert cpu.console.output() == "1 0 0 24 0\n"
    assert cpu.ledger.count("table_lookup") == 0
