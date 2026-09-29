"""
Verification of the delta-sigma / Sturmian / mantissa-wall subsystem.

Every test corresponds to a theorem in `DeltaSigma.lean`, `Sturmian.lean`,
`Mantissa.lean`, or the GLM evidence doc's measured tables.  All arithmetic
is exact (Fractions, integers) — no floats.
"""
import math
from fractions import Fraction

import pytest

from noisecore_vm.delta_sigma import (
    DeltaSigma, wobble_entropy_truncated,
    dyadic_orbit, dyadic_orbit_collapses_at, odd_orbit, odd_orbit_period,
    compare_orbits, odd_primes_below_100,
    TARGET_SQRT2_MINUS_1, TARGET_PHI_MINUS_1, TARGET_PI_MINUS_3,
    bitstream_to_words, pipeline_walk,
)


# ── The Sturmian bridge: the GLM §2.4 table, recomputed ────────────────────

class TestSturmianTable:
    """All 24 odd primes below 100, N=500 ticks, exact ⌊N·t⌋ prediction."""

    @pytest.mark.parametrize("p", odd_primes_below_100())
    def test_ones_match_floor_500_over_p(self, p):
        ds = DeltaSigma(Fraction(1, p))
        expected = 500 // p          # ⌊500/p⌋
        measured = sum(ds.run(500))  # actual count of 1s
        assert measured == expected, f"p={p}: {measured} ≠ {expected}"

    @pytest.mark.parametrize("p", odd_primes_below_100())
    def test_ones_via_closed_form(self, p):
        """The closed-form accessor agrees with simulation."""
        ds = DeltaSigma(Fraction(1, p))
        assert ds.ones(500) == 500 // p

    # Run-length bound is ATTAINED (not merely respected) — per GLM §2.4
    @pytest.mark.parametrize("p,longest_zero_expected", [
        (3, 2), (5, 4), (7, 6), (11, 10), (13, 12),
        (17, 16), (19, 18), (23, 22), (29, 28), (31, 30),
        (37, 36), (41, 40), (43, 42), (47, 46), (53, 52),
        (59, 58), (61, 60), (67, 66), (71, 70), (73, 72),
        (79, 78), (83, 82), (89, 88), (97, 96),
    ])
    def test_zero_run_attains_bound(self, p, longest_zero_expected):
        ds = DeltaSigma(Fraction(1, p))
        # bound: L < 1/t = p  →  L ≤ p − 1  →  we expect L = p − 1
        assert ds.longest_zero_run(500) == longest_zero_expected


# ── DeltaSigma.lean theorems ────────────────────────────────────────────────

class TestBoundedness:
    """dsState_mem_Ico: the accumulator never escapes [0, 1)."""

    @pytest.mark.parametrize("t", [
        Fraction(1, 7), Fraction(1, 2), Fraction(99, 100),
        TARGET_SQRT2_MINUS_1, TARGET_PHI_MINUS_1, TARGET_PI_MINUS_3,
    ])
    def test_state_bounded_500_ticks(self, t):
        ds = DeltaSigma(t)
        for n in range(500):
            s = ds.state(n)
            assert Fraction(0) <= s < Fraction(1)


class TestExactBitBudget:
    """dsSum_eq: Σ_{i<n} bit_i = n·t − s_n."""

    @pytest.mark.parametrize("t", [Fraction(1, 7), Fraction(2, 5)])
    def test_bit_eq_floor_diff(self, t):
        ds = DeltaSigma(t)
        for n in range(50):
            expected = math.floor(float((n + 1) * t)) - math.floor(float(n * t))
            # exact path
            expected_exact = ((n + 1) * t).numerator // ((n + 1) * t).denominator \
                           - (n * t).numerator // (n * t).denominator
            assert ds.bit(n) == expected_exact


# ── Mantissa.lean — the doubling map ───────────────────────────────────────

class TestMantissaWall:
    """Dyadic orbits die; odd orbits cycle forever."""

    @pytest.mark.parametrize("k,m,expected_steps", [
        (1, 1, 1),      # 1/2   dies in 1 step
        (2, 1, 2),      # 1/4   dies in 2 steps
        (2, 3, 2),      # 3/4   dies in 2 steps
        (3, 1, 3),      # 1/8   dies in 3 steps
        (4, 1, 4),      # 1/16  dies in 4 steps
        (10, 1, 10),    # 1/1024 dies in 10 steps
    ])
    def test_dyadic_orbit_collapses_in_k_steps(self, k, m, expected_steps):
        assert dyadic_orbit_collapses_at(k, m) == expected_steps

    @pytest.mark.parametrize("p,expected_period", [
        (3, 2), (5, 4), (7, 3), (11, 10), (13, 12),
        (17, 8), (19, 18), (23, 11), (29, 28), (31, 5),
    ])
    def test_odd_orbit_period_is_ord_p_2(self, p, expected_period):
        assert odd_orbit_period(p) == expected_period

    @pytest.mark.parametrize("p", [3, 5, 7, 11, 13])
    def test_odd_orbit_never_zero(self, p):
        for n in range(100):
            assert odd_orbit(p, n) != 0

    def test_dyadic_vs_odd_diverge(self):
        """The two behaviours are incompatible — witness at every p,k,m."""
        for p in (3, 5, 7):
            for k in (1, 2, 3):
                n = compare_orbits(p, k, 1, n_max=20)
                assert n != -1, f"no divergence found for p={p}, k={k}"


# ── Wobble entropy (GLM §9.2) ──────────────────────────────────────────────

class TestWobbleEntropy:
    """Spot-checks against GLM §9.2 (truncated to 3 decimals)."""

    @pytest.mark.parametrize("p,expected_str", [
        (3, "0.918"), (5, "0.721"), (7, "0.591"),
        (11, "0.439"), (13, "0.391"), (97, "0.082"),
    ])
    def test_entropy_matches_glm_table(self, p, expected_str):
        assert wobble_entropy_truncated(Fraction(1, p), 3) == expected_str


# ── Pipeline walk — the §14 worked example ─────────────────────────────────

class TestPipelineWalk:
    def test_one_seventh_walk(self):
        """Reproduce the §14 transcript for t = 1/7, 24 ticks."""
        result = pipeline_walk(Fraction(1, 7), n_ticks=24)
        assert result["ones"] == 3                       # floor(24/7)
        assert result["ones_law_holds"] is True
        assert result["longest_zero_run"] == 6           # attains bound
        assert result["word_hex"] == "0x102040"          # matches §14
        assert result["hamming_weight"] == 3
        assert result["arithmetic"]["binary_period"] == 3
        assert result["arithmetic"]["class"] == "odd-denominator"
        # 4/27 shares the first 24 bits (both floor to 3)
        assert any(p == 4 and q == 27 for p, q, _ in result["shares_word_with"])

    def test_dyadic_walk_differs(self):
        """Dyadic targets take a different path through the pipeline."""
        result = pipeline_walk(Fraction(1, 4), n_ticks=24)
        assert result["arithmetic"]["class"] == "dyadic"
        assert result["arithmetic"]["binary_period"] == 0

    def test_irrational_walk(self):
        """√2−1 to 16 dp — exact rational approximation, not float."""
        result = pipeline_walk(TARGET_SQRT2_MINUS_1, n_ticks=24)
        assert result["ones_law_holds"] is True
        # √2−1 ≈ 0.41421..., so ⌊24·0.414…⌋ = 9
        assert result["ones"] == 9
