"""
================================================================================
NRCI — one written-down definition, dyadic enclosure  (zero-storage v5 §3)
================================================================================
The v5 study retires the family of older NRCI formulas and keeps exactly one:

    NRCI(x, r) = 1 − sqrt( Σ rᵢ² / Σ xᵢ² )

where x is the reference stream and r the residual stream.  Irrational in
general, so every value is reported as a dyadic enclosure [lo, hi] with
hi − lo = 2⁻³², computed with integer square roots only (no floats, D7).

The three v5 streams are reproduced:
  • ds_average_stream  — NRCI between a delta-sigma running average and its
                         target, with the proved per-tick bound |rₙ| < 1/n;
  • decode_residual    — NRCI of a decode's residual;
  • dyadic_tower       — NRCI of the dyadic tower's residual.
"""

from __future__ import annotations
from fractions import Fraction
from math import isqrt
from typing import Iterable, List, Sequence, Tuple

DYADIC_BITS = 32
_SCALE = 1 << DYADIC_BITS


def nrci_enclosure(x_sq_sum: int, r_sq_sum: int) -> Tuple[Fraction, Fraction]:
    """
    Dyadic enclosure of 1 − sqrt(r_sq_sum / x_sq_sum).
    Returns (lo, hi) with hi − lo = 2^-32, exact Fractions.
    """
    if x_sq_sum <= 0:
        raise ValueError("reference stream has zero energy")
    if r_sq_sum < 0:
        raise ValueError("residual energy negative")
    if r_sq_sum == 0:
        return Fraction(1), Fraction(1)
    # k/2^32 ≤ sqrt(r/x) < (k+1)/2^32  ⟺  k² ≤ r·2⁶⁴/x < (k+1)²
    num = r_sq_sum << (2 * DYADIC_BITS)
    k = isqrt(num // x_sq_sum)
    # correct off-by-one from the integer division
    while (k + 1) * (k + 1) * x_sq_sum <= num:
        k += 1
    while k * k * x_sq_sum > num:
        k -= 1
    hi = Fraction(1) - Fraction(k, _SCALE)
    lo = Fraction(1) - Fraction(k + 1, _SCALE)
    return lo, hi


def nrci(x: Sequence[int], r: Sequence[int], ledger=None) -> Tuple[Fraction, Fraction]:
    """NRCI between integer streams x (reference) and r (residual)."""
    if len(x) != len(r):
        raise ValueError("streams must have equal length")
    xs = sum(v * v for v in x)
    rs = sum(v * v for v in r)
    if ledger is not None:
        ledger.coordinate_pass(len(x))
        ledger.int_sqrt()
    return nrci_enclosure(xs, rs)


def nrci_scaled(x: Sequence[int], r: Sequence[int]) -> int:
    """Midpoint of the enclosure × 10⁶ (for register-sized returns)."""
    lo, hi = nrci(x, r)
    mid = (lo + hi) / 2
    return int(mid * 1_000_000)


# ── the three v5 streams ─────────────────────────────────────────────────────

def ds_average_stream(target: Fraction, n_max: int) -> dict:
    """
    NRCI of the delta-sigma running average against its target, with the
    Lean bound |avg_n − t| ≤ 1/n verified at every tick (dsAverage_error_le).
    """
    from .delta_sigma import DeltaSigma
    ds = DeltaSigma(target)
    x: List[int] = []
    r: List[int] = []
    bound_ok = True
    S = 10**6                     # fixed-point scale, keeps everything integral
    for n in range(1, n_max + 1):
        avg = ds.average(n)
        err = avg - target
        if abs(err) > Fraction(1, n):
            bound_ok = False
        x.append(int(target * S))
        r.append(int(abs(err) * S))
    lo, hi = nrci(x, r)
    return {
        "target": str(target),
        "n_max": n_max,
        "nrci_lo": lo, "nrci_hi": hi,
        "nrci_mid": float((lo + hi) / 2),
        "bound_ok": bound_ok,
    }


def decode_residual_stream(target: Sequence[int], point: Sequence[int]) -> dict:
    """NRCI of a decode's residual (target − nearest lattice point)."""
    r = [t - p for t, p in zip(target, point)]
    lo, hi = nrci(list(target), r)
    return {"nrci_lo": lo, "nrci_hi": hi, "nrci_mid": float((lo + hi) / 2)}


def dyadic_tower_stream(depth: int) -> dict:
    """
    NRCI of the dyadic tower's residual: t approximated by ⌊2ᵏt⌋/2ᵏ at each
    level k = 1..depth, residuals measured against t = 1/7 (canonical).
    """
    t = Fraction(1, 7)
    x, r = [], []
    S = 10**6
    for k in range(1, depth + 1):
        approx = Fraction(int(t * (1 << k)), 1 << k)
        err = t - approx
        x.append(int(t * S))
        r.append(int(abs(err) * S))
    lo, hi = nrci(x, r)
    return {"depth": depth, "nrci_lo": lo, "nrci_hi": hi,
            "nrci_mid": float((lo + hi) / 2)}
