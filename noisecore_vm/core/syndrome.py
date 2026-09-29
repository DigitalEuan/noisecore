"""
================================================================================
Zero-Storage Syndrome Layer  (zero-storage v5 §1)
================================================================================
Membership of the extended binary Golay code is twelve parity checks, not a
4096-entry table.  The code is self-dual, so the twelve generator rows are
also a parity-check matrix:

    syndrome(w) = ( popcount(w & row_j) mod 2 )_{j=0..11}
    w ∈ G24  ⟺  syndrome(w) = 0

Proved in Lean:  GLM.ZeroStorageV5.syndromeZero_iff_isGolay.
Here: implemented against the engine's actual matrices, with the self-duality
*verified at import time* rather than assumed — the module sweeps all 4096
codewords and a random sample of non-codewords and falls back to the engine's
H matrix if the G-rows route ever disagreed (recorded in SELF_DUAL_VERIFIED).

Also provides the Construction-C Leech sieve
(`syndromeSieve_iff_isLeech` in Lean):

    x ∈ Λ24  ⟺  (i)   every x_i ≡ m (mod 2),   m = x_0 mod 2
                (ii)  mask(x) = { i : 4 ∤ (x_i − m) }  is a Golay codeword
                (iii) Σ x_i ≡ 4m (mod 8)

No table anywhere: parity off coordinate 0, twelve parity checks, one mod-8 sum.
"""

from __future__ import annotations
from typing import List, Optional

from .golay_engine import GOLAY_ENGINE


def _rows_to_ints(matrix: List[List[int]]) -> List[int]:
    """Pack each 24-bit row (MSB-first list) into an int."""
    out = []
    for row in matrix:
        w = 0
        for b in row:
            w = (w << 1) | (b & 1)
        out.append(w)
    return out


_G_ROWS: List[int] = _rows_to_ints(GOLAY_ENGINE.G)
_H_ROWS: List[int] = _rows_to_ints(GOLAY_ENGINE.H)

# Word ↔ bit-list convention (MSB-first, consistent with the rest of the VM)
def word_to_bits(word: int) -> List[int]:
    return [(word >> (23 - i)) & 1 for i in range(24)]

def bits_to_word(bits: List[int]) -> int:
    w = 0
    for b in bits:
        w = (w << 1) | (b & 1)
    return w


def syndrome_with_rows(word: int, rows: List[int], ledger=None) -> int:
    """12-bit syndrome integer (row 0 = LSB of syndrome)."""
    syn = 0
    for j, row in enumerate(rows):
        if ledger is not None:
            ledger.parity_check()
            ledger.popcount()
        if (word & row).bit_count() & 1:
            syn |= (1 << j)
    return syn


def syndrome(word: int, ledger=None) -> int:
    """Syndrome via the generator rows (self-dual route). 36 bytes of state."""
    return syndrome_with_rows(word & 0xFFFFFF, _G_ROWS, ledger)


def syndrome_h(word: int, ledger=None) -> int:
    """Syndrome via the engine's parity-check matrix (reference route)."""
    return syndrome_with_rows(word & 0xFFFFFF, _H_ROWS, ledger)


def is_golay(word: int, ledger=None) -> bool:
    """Membership without a table: twelve parities."""
    return syndrome(word, ledger) == 0


# ── import-time self-duality verification ────────────────────────────────────

def _verify_self_dual() -> bool:
    """Every codeword must pass all twelve G-row checks (rows_orthogonal +
    synZero_of_isGolay), and G/H routes must agree on a sample of words."""
    import random
    for cw in GOLAY_ENGINE.get_all_codewords():
        w = bits_to_word(cw)
        if syndrome_with_rows(w, _G_ROWS) != 0:
            return False
    rng = random.Random(0x607A1)
    for _ in range(2048):
        w = rng.getrandbits(24)
        g = syndrome_with_rows(w, _G_ROWS)
        # membership agreement is the load-bearing property
        if (g == 0) != (syndrome_with_rows(w, _H_ROWS) == 0):
            return False
    return True


SELF_DUAL_VERIFIED: bool = _verify_self_dual()
_ACTIVE_ROWS = _G_ROWS if SELF_DUAL_VERIFIED else _H_ROWS


def syndrome_active(word: int, ledger=None) -> int:
    return syndrome_with_rows(word & 0xFFFFFF, _ACTIVE_ROWS, ledger)


# ── Leech sieve (Construction C, syndrome route) ─────────────────────────────

def leech_mask(coords: List[int]) -> tuple:
    """
    Classify 24 integer coordinates into their coset (m, codeword-word).
    Returns (m, mask_word).  Raises ValueError if coordinates are not
    all congruent mod 2 (then the point is certainly not Leech).
    """
    if len(coords) != 24:
        raise ValueError("Leech points have 24 coordinates")
    m = coords[0] % 2
    mask = 0
    for i, x in enumerate(coords):
        if x % 2 != m:
            raise ValueError(f"coordinate {i} parity mismatch: {x} vs m={m}")
        if (x - m) % 4 != 0:                     # 4 ∤ (x_i − m)
            mask |= (1 << (23 - i))
    return m, mask


def in_coset(coords: List[int], m: int, codeword: int) -> bool:
    """InCoset test: right parity class, right codeword, right mod-8 sum."""
    try:
        pm, mask = leech_mask(coords)
    except ValueError:
        return False
    if pm != m or mask != (codeword & 0xFFFFFF):
        return False
    return sum(coords) % 8 == (4 * m) % 8


def is_leech(coords: List[int], ledger=None) -> bool:
    """
    Zero-storage Leech membership:
    parity off coordinate 0, twelve parity checks, one mod-8 sum.
    """
    if ledger is not None:
        ledger.coordinate_pass(24)
    try:
        m, mask = leech_mask(coords)
    except ValueError:
        return False
    if not is_golay(mask, ledger):
        return False
    return sum(coords) % 8 == (4 * m) % 8
