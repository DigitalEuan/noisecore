"""Cesàro dynamics on syndrome space (Golay/Cesaro.lean, executable)."""
from fractions import Fraction
from noisecore_vm.cesaro import (
    columns, delta_law, total_mass, step, iterate, cesaro,
    cesaro_error, bound_holds, N_SYN,
)


class TestChainBasics:
    def test_columns_are_24_syndromes(self):
        c = columns()
        assert len(c) == 24
        assert all(0 <= v < N_SYN for v in c)

    def test_step_preserves_mass(self):
        for start in (delta_law(0), delta_law(1234)):
            assert total_mass(step(start)) == 1
            assert total_mass(iterate(start, 5)) == 1

    def test_cesaro_is_a_law(self):
        assert total_mass(cesaro(delta_law(0), 16)) == 1


class TestCesaroConverges:
    """|cesaro μ N f − 1/4096| ≤ 24/N — at several starts, targets, N."""

    def test_bound_at_delta_law(self):
        mu = delta_law(0)
        for N in (4, 8, 16, 32, 64):
            assert bound_holds(mu, N, 0)

    def test_bound_at_biased_start(self):
        mu = delta_law(0xABC)
        for N in (8, 16, 32):
            for f in (0, 0xABC, 0xFFF):
                assert bound_holds(mu, N, f)

    def test_bound_at_two_point_law(self):
        mu = {0: Fraction(1, 3), 7: Fraction(2, 3)}
        for N in (8, 16, 32):
            assert bound_holds(mu, N, 3)

    def test_error_decreases(self):
        mu = delta_law(0)
        e16 = cesaro_error(mu, 16, 0)
        e64 = cesaro_error(mu, 64, 0)
        assert e64 < e16
