"""
================================================================================
Leech Λ₂₄ coset decoder  (zero-storage v5 §3–§4)
================================================================================
Nearest-lattice-point decoding by exhaustion over the 8192 Construction-C
cosets — with the two facts the Lean development proves:

  §3  coset_cost_ge / coset_repair_attained:
      inside a coset, per-coordinate nearest + (when the mod-8 sum demands
      it) ONE cheapest ±4 repair is optimal.  No odd repair can beat the
      cheapest single move, and that move attains the minimum.

  §4  coset_min_cost / coset_min_attained / leech_in_coset / lattice_dist_ge:
      minimising over the 8192 cosets gives the distance to the nearest
      point of Λ₂₄ — nothing in the lattice escapes the cosets.

Arithmetic is exact-integer throughout: the target enters as 24 integers in
units of 1/256 (SCALE = 256), costs are squared errors in those units.

Pruning: cosets are evaluated with an early-abort partial sum — as soon as
the running cost exceeds the best seen, the coset is abandoned (and the
`coset_pruned` ledger counter takes the credit).  The reference
`decode_exhaustive` evaluates every coset in full so tests can assert the
two routes agree (§4, executable form).
"""

from __future__ import annotations
from typing import List, Optional, Tuple

from .core.golay_engine import GOLAY_ENGINE
from .core.syndrome import bits_to_word

SCALE = 256          # fixed-point denominator for targets
DIM = 24


def _nearest_in_class(target_scaled: int, m: int, ci: int) -> Tuple[int, int]:
    """
    Nearest integer z to target_scaled/256 with z ≡ m + 2·ci (mod 4).
    Returns (z, cost) where cost = (256·z − target_scaled)².
    Class spacing is 4, so the nearest is within ±3 of the rounded value.
    """
    a = (m + 2 * ci) % 4
    t = target_scaled
    z0 = t // SCALE if t >= 0 else -((-t) // SCALE)   # floor toward zero-ish
    best_z, best_c = None, None
    for cand in range(z0 - 3, z0 + 4):
        if (cand - a) % 4 == 0:
            c = (SCALE * cand - t) ** 2
            if best_c is None or c < best_c:
                best_z, best_c = cand, c
    return best_z, best_c


def _decode_coset(target: List[int], m: int, codeword_word: int,
                  ledger=None, partial_best: Optional[int] = None) -> Tuple[List[int], int, bool]:
    """
    Decode one coset.  Returns (point, cost, pruned).
    `pruned` is True when the early-abort bound fired (partial_best given).
    """
    z: List[int] = [0] * DIM
    cost = 0
    for i in range(DIM):
        ci = (codeword_word >> (23 - i)) & 1
        zi, c = _nearest_in_class(target[i], m, ci)
        z[i] = zi
        cost += c
        if ledger is not None:
            ledger.coordinate_pass()
        if partial_best is not None and cost >= partial_best:
            return z, cost, True
    # §3: mod-8 sum coupling — flips exactly when the number of ±4 moves is odd
    if (sum(z) - 4 * m) % 8 != 0:
        best_i, best_s, best_delta = 0, 4, None
        for i in range(DIM):
            ci = (codeword_word >> (23 - i)) & 1
            for s in (4, -4):
                zn = z[i] + s
                # the ±4 move keeps the coordinate in its mod-4 class
                delta = (SCALE * zn - target[i]) ** 2 - (SCALE * z[i] - target[i]) ** 2
                if best_delta is None or delta < best_delta:
                    best_i, best_s, best_delta = i, s, delta
        z[best_i] += best_s
        cost += best_delta
        if ledger is not None:
            ledger.pm4_repair()
    return z, cost, False


def decode(target: List[int], ledger=None, exhaustive: bool = False) -> dict:
    """
    Nearest Leech point to `target` (24 ints, units of 1/256).

    Returns dict with point (24 ints), cost, coset (m, codeword), and
    coset statistics.  With exhaustive=True the early-abort bound is
    disabled (reference route for tests).
    """
    if len(target) != DIM:
        raise ValueError("target must have 24 coordinates")
    best = {"point": None, "cost": None, "m": 0, "codeword": 0}
    trials = pruned = 0
    for m in (0, 1):
        for msg in range(4096):
            bits = [(msg >> (11 - j)) & 1 for j in range(12)]
            cw_bits = GOLAY_ENGINE.encode(bits)          # generated, not stored
            cw = bits_to_word(cw_bits)
            if ledger is not None:
                ledger.word_xor()
                ledger.coset_trial()
            trials += 1
            bound = None if exhaustive else best["cost"]
            z, cost, was_pruned = _decode_coset(target, m, cw, ledger, bound)
            if was_pruned:
                pruned += 1
                if ledger is not None:
                    ledger.coset_pruned()
                continue
            if best["cost"] is None or cost < best["cost"]:
                best.update(point=z, cost=cost, m=m, codeword=cw)
    best["trials"] = trials
    best["pruned"] = pruned
    return best


def decode_exhaustive(target: List[int], ledger=None) -> dict:
    """Reference: every coset evaluated in full.  §4 says the answers agree."""
    return decode(target, ledger=ledger, exhaustive=True)
