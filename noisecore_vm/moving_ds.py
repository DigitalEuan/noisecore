"""
================================================================================
Moving-target delta-sigma  (zero-storage v5 §2)
================================================================================
v1.1's DeltaSigma chased a fixed target.  v5's register does not zero the
accumulator on retarget: the loop carries its phase across a write.  The Lean
development proves the three facts this class implements:

  dsAcc_mem_Ico          0 ≤ acc < 1 whatever the target schedule does
  dsAcc_eq               Σ bits = Σ targets − accumulator   (exact identity)
  ds_track_bound         |average − mean target| < 1/N      (moving target)
  ds_track_moving_target |average − s| ≤ 1/N + (1/N)Σ|tᵢ − s|  (fixed s)

Everything is exact Fraction arithmetic; the class also maintains the ledger
(ds_tick once per tick).
"""

from __future__ import annotations
from fractions import Fraction
from typing import List, Optional


class MovingDeltaSigma:
    """
    First-order delta-sigma with a *schedule* of targets.

    acc starts at 0; retarget(t) changes the target WITHOUT touching acc —
    this is the v5 gene, and it is what makes the tracker a homeostat rather
    than a sequence of restarts.
    """

    def __init__(self, t: Fraction, ledger=None):
        t = Fraction(t)
        if not (Fraction(0) <= t < Fraction(1)):
            raise ValueError(f"target must be in [0,1), got {t}")
        self.t = t
        self.acc = Fraction(0)
        self.sum_bits = 0
        self.sum_targets = Fraction(0)
        self.n = 0
        self.ledger = ledger
        self.history: List[Fraction] = []

    def retarget(self, t: Fraction) -> None:
        """Change target; accumulator is preserved (v5 §2)."""
        t = Fraction(t)
        if not (Fraction(0) <= t < Fraction(1)):
            raise ValueError(f"target must be in [0,1), got {t}")
        self.t = t

    def tick(self) -> int:
        """Emit one bit, advance the accumulator.  [dsAcc_mem_Ico preserved]"""
        bit = 1 if self.acc + self.t >= 1 else 0
        self.acc += self.t - bit
        self.sum_bits += bit
        self.sum_targets += self.t
        self.n += 1
        self.history.append(self.t)
        if self.ledger is not None:
            self.ledger.ds_tick()
        assert Fraction(0) <= self.acc < Fraction(1), "dsAcc_mem_Ico violated"
        assert Fraction(self.sum_bits) == self.sum_targets - self.acc, \
            "dsAcc_eq violated"
        return bit

    def run(self, ticks: int) -> List[int]:
        return [self.tick() for _ in range(ticks)]

    # ── the proved identities, as executable checks ──────────────────────

    def average(self) -> Fraction:
        return Fraction(self.sum_bits, self.n) if self.n else Fraction(0)

    def mean_target(self) -> Fraction:
        return self.sum_targets / self.n if self.n else Fraction(0)

    def track_error(self) -> Fraction:
        """|average − mean target|;  theorem: < 1/n."""
        if not self.n:
            return Fraction(0)
        return abs(self.average() - self.mean_target())

    def track_bound_holds(self) -> bool:
        """ds_track_bound: |avg − mean target| < 1/N."""
        if not self.n:
            return True
        return self.track_error() < Fraction(1, self.n)

    def moving_error_bound(self, s: Fraction) -> Fraction:
        """
        ds_track_moving_target: against a fixed s the error is bounded by
        1/N + mean deviation of the trajectory from s.
        """
        s = Fraction(s)
        if not self.n:
            return Fraction(0)
        drift = sum(abs(t - s) for t in self.history) / self.n
        return Fraction(1, self.n) + drift

    def error_against(self, s: Fraction) -> Fraction:
        s = Fraction(s)
        return abs(self.average() - s) if self.n else Fraction(0)
