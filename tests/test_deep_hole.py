"""Deep-hole classifier machinery (DeepHoleClassifier.lean, executable)."""
from fractions import Fraction
import pytest
from noisecore_vm.deep_hole import l1, DeepHoleClassifier


# small exact reference table, pairwise L1 = 10 apart, radius r = 2
REFS = {
    "A1": [Fraction(0), Fraction(0), Fraction(0)],
    "D4": [Fraction(10), Fraction(0), Fraction(0)],
    "E8": [Fraction(0), Fraction(10), Fraction(0)],
}


class TestL1:
    def test_exact_rational_distance(self):
        assert l1([Fraction(1, 3)], [Fraction(1, 2)]) == Fraction(1, 6)
        assert l1([0, -5], [3, 5]) == 13


class TestSeparation:
    def test_table_is_separated(self):
        c = DeepHoleClassifier(REFS, radius=2)
        assert c.separated is True

    def test_unseparated_table_detected(self):
        c = DeepHoleClassifier({"X": [0, 0], "Y": [1, 0]}, radius=2)
        assert c.separated is False


class TestTheorems:
    def test_named_of_separated(self):
        """classify_named_of_separated: within r ⇒ named, never ambiguous."""
        c = DeepHoleClassifier(REFS, radius=2)
        q = [Fraction(1), Fraction(1), Fraction(0)]      # L1 to A1 = 2 ≤ r
        assert c.classify_named_of_separated("A1", q) is True
        verdict, label = c.classify(q)
        assert (verdict, label) == ("named", "A1")

    def test_absent_certifies(self):
        """absent_certifies: absent ⇒ nothing within r of the query."""
        c = DeepHoleClassifier(REFS, radius=2)
        q = [Fraction(5), Fraction(5), Fraction(0)]
        assert c.classify(q)[0] == "absent"
        assert c.absent_certifies(q) is True

    def test_absent_verdict_is_total_and_single_valued(self):
        c = DeepHoleClassifier(REFS, radius=2)
        for q in ([0, 0, 0], [3, 3, 3], [Fraction(1, 2)] * 3, [-7, 2, 1]):
            v, _ = c.classify(q)
            assert v in ("named", "ambiguous", "absent")

    def test_far_query_absent(self):
        c = DeepHoleClassifier(REFS, radius=2)
        assert c.classify([Fraction(50), Fraction(50), Fraction(50)])[0] == "absent"
