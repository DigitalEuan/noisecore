"""
================================================================================
Zero-Storage Cell Verification  (v1.3.0 — syndrome all the way down)
================================================================================
v1.2.0 made membership table-free at the ISA level (SYN / ISGOLAY / DECODE).
v1.3.0 routes the *substrate cells themselves* through the same path: every
NoiseCellV3 verification is now twelve parity checks against the 36-byte
generator, never a consult of the engine's stored 4096-codeword list.

Lean anchors:
  ZeroStorageV5.syndromeZero_iff_isGolay   — membership ⟺ zero syndrome
  ZeroStorage.refinedSieve_iff_isLeech     — the sieve IS Leech membership
  Golay.Census                             — coset census (proved in Lean);
                                             codeword weight census below is
                                             computed from generated codewords

The ledger is the trip-wire: any code path that falls back to a stored
table MUST increment `table_lookup`, and the audit reports it.
"""

from __future__ import annotations
from typing import List, Optional

from .syndrome import syndrome, is_golay, bits_to_word, word_to_bits, SELF_DUAL_VERIFIED


def verify_cell_zero_storage(bits: List[int], ledger=None) -> dict:
    """
    Zero-storage verification of a 24-bit cell state.
    Returns syndrome, membership, and lattice class — twelve parity checks,
    no table.  `table_lookup` stays zero by construction.
    """
    if len(bits) != 24:
        raise ValueError("cell state must be 24 bits")
    word = bits_to_word([b & 1 for b in bits])
    syn = syndrome(word, ledger)
    hw = bin(word).count("1")
    return {
        "word": word,
        "syndrome": syn,
        "is_codeword": syn == 0,
        "hamming_weight": hw,
        "lattice_class": (
            "Identity" if hw == 0 else "Octad" if hw == 8 else
            "Dodecad" if hw == 12 else "Hexadecad" if hw == 16 else
            "Universe" if hw == 24 else f"Off-lattice (HW={hw})"
        ),
        "route": "syndrome (zero-storage)",
        "self_dual_verified": SELF_DUAL_VERIFIED,
        "table_lookups": (ledger.count("table_lookup") if ledger else 0),
    }


def golay_weight_census() -> dict:
    """
    Codeword weight distribution of the extended code [24,12,8]:
    weights {0,8,12,16,24} with counts {1, 759, 2576, 759, 1}, computed
    from generated codewords (generation is encoding — not a table).
    (Note: Golay/Census.lean proves the *coset* census
    {0:1, 1:24, 2:276, 3:2024, 4:1771}, mean 3433/1024 — a different,
    complementary census; this function reports the codeword weights.)
    """
    from .golay_engine import GOLAY_ENGINE
    census = {}
    for cw in GOLAY_ENGINE.get_all_codewords():
        w = sum(cw)
        census[w] = census.get(w, 0) + 1
    return census


def zero_storage_audit(ledger) -> dict:
    """The v1.3.0 audit: storage ratio + the trip-wire count."""
    return {
        "audit_text": ledger.storage_audit(),
        "table_lookup": ledger.count("table_lookup"),
        "zero_storage_intact": ledger.count("table_lookup") == 0,
        "census": golay_weight_census(),
    }
