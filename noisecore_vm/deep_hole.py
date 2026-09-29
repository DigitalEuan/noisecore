"""
================================================================================
Deep-hole classifier machinery  (DeepHoleClassifier.lean, executable)
================================================================================
Profiles are exact-rational vectors; distance is L1 over ℚ.  The classifier
is total and single-valued with three verdicts:

    named(label)   — exactly one reference within radius r
    ambiguous      — two or more references within r
    absent         — none within r

Under the separation hypothesis (distinct references more than 2r apart) the
two proved properties become executable checks:

    classify_named_of_separated — within r of a reference ⇒ named, and
                                  ambiguous cannot occur;
    absent_certifies            — verdict absent ⇒ no tabulated reference is
                                  within r of the query.
"""

from __future__ import annotations
from fractions import Fraction
from typing import Dict, List, Sequence, Tuple


def l1(p: Sequence, q: Sequence) -> Fraction:
    """L1 distance over exact rationals."""
    if len(p) != len(q):
        raise ValueError("profiles must have equal length")
    return sum((abs(Fraction(a) - Fraction(b)) for a, b in zip(p, q)),
               Fraction(0))


class DeepHoleClassifier:
    def __init__(self, references: Dict[str, Sequence], radius):
        if not references:
            raise ValueError("reference table must be non-empty")
        self.refs = {k: tuple(Fraction(c) for c in v)
                     for k, v in references.items()}
        self.r = Fraction(radius)
        self.separated = self._check_separation()

    def _check_separation(self) -> bool:
        """distinct labels more than 2r apart (the r* hypothesis)."""
        items = list(self.refs.items())
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                if l1(items[i][1], items[j][1]) <= 2 * self.r:
                    return False
        return True

    def classify(self, query: Sequence) -> Tuple[str, object]:
        q = tuple(Fraction(c) for c in query)
        hits = [name for name, ref in self.refs.items()
                if l1(q, ref) <= self.r]
        if len(hits) == 1:
            return ("named", hits[0])
        if len(hits) > 1:
            return ("ambiguous", hits)
        return ("absent", None)

    # ── the two theorems, as executable checks ──────────────────────────

    def classify_named_of_separated(self, name: str, query: Sequence) -> bool:
        """If separated and query within r of `name`, verdict is named:name."""
        if not self.separated:
            return False
        if l1(query, self.refs[name]) > self.r:
            return False
        verdict, label = self.classify(query)
        return verdict == "named" and label == name

    def absent_certifies(self, query: Sequence) -> bool:
        """If verdict is absent, no reference lies within r of the query."""
        verdict, _ = self.classify(query)
        if verdict != "absent":
            return True          # vacuous
        return all(l1(query, ref) > self.r for ref in self.refs.values())
