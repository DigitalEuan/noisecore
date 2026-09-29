"""
================================================================================
NoiseCore VM — Cost Ledger (zero-storage v5 §2)
================================================================================
Every generated answer carries an exact-integer ledger of what it cost.
Thirteen counters, matching glm_zero_storage_substrate_v5's LEDGER_ITEMS
verbatim so `--ledger` output is byte-comparable with the v5 study.

Design rule: the ledger counts work the VM *already does* — it never adds
computation. `table_lookup` exists as a counter precisely so that it can
stay at zero forever: any code path that consults a stored table must
increment it, and the audit will catch it.
"""

from __future__ import annotations
from typing import Dict, List

LEDGER_ITEMS: List[str] = [
    "parity_check",      #  0  one row-parity of a 24-bit word
    "popcount",          #  1  one popcount of a 24-bit word
    "word_xor",          #  2  one 24-bit XOR
    "coordinate_pass",   #  3  one per-coordinate decoder/arithmetic pass
    "coset_trial",       #  4  one coset considered by the decoder
    "coset_pruned",      #  5  one coset skipped by early-abort bound
    "pm4_repair",        #  6  one ±4 mod-8 repair move
    "table_lookup",      #  7  one consultation of a stored table — target: 0
    "int_sqrt",          #  8  one integer square root
    "series_term",       #  9  one term of a convergent series
    "big_div",           # 10  one multi-word division
    "ds_tick",           # 11  one delta-sigma tick
    "rational_op",       # 12  one exact-rational arithmetic op
]


class Ledger:
    """Exact-integer cost ledger. Counters only ever move up until cleared."""

    __slots__ = ("_c",)

    def __init__(self):
        self._c: List[int] = [0] * len(LEDGER_ITEMS)

    # ── recording ──────────────────────────────────────────────────────
    def add(self, item, n: int = 1) -> None:
        idx = LEDGER_ITEMS.index(item) if isinstance(item, str) else int(item)
        self._c[idx] += n

    # convenience names used throughout the VM
    def parity_check(self, n=1):    self._c[0] += n
    def popcount(self, n=1):        self._c[1] += n
    def word_xor(self, n=1):        self._c[2] += n
    def coordinate_pass(self, n=1): self._c[3] += n
    def coset_trial(self, n=1):     self._c[4] += n
    def coset_pruned(self, n=1):    self._c[5] += n
    def pm4_repair(self, n=1):      self._c[6] += n
    def table_lookup(self, n=1):    self._c[7] += n
    def int_sqrt(self, n=1):        self._c[8] += n
    def series_term(self, n=1):     self._c[9] += n
    def big_div(self, n=1):         self._c[10] += n
    def ds_tick(self, n=1):         self._c[11] += n
    def rational_op(self, n=1):     self._c[12] += n

    # ── reporting ──────────────────────────────────────────────────────
    def count(self, item) -> int:
        idx = LEDGER_ITEMS.index(item) if isinstance(item, str) else int(item)
        return self._c[idx]

    def total(self) -> int:
        return sum(self._c)

    def as_dict(self) -> Dict[str, int]:
        return {name: self._c[i] for i, name in enumerate(LEDGER_ITEMS)}

    def nonzero(self) -> Dict[str, int]:
        return {name: v for name, v in self.as_dict().items() if v}

    def clear(self) -> None:
        for i in range(len(self._c)):
            self._c[i] = 0

    def report(self) -> str:
        lines = ["item                count", "───────────────────────"]
        for i, name in enumerate(LEDGER_ITEMS):
            lines.append(f"{name:<20}{self._c[i]}")
        lines.append("───────────────────────")
        lines.append(f"{'TOTAL':<20}{self.total()}")
        return "\n".join(lines)

    def storage_audit(self) -> str:
        """The v5 storage audit: what is stored vs what is generated."""
        # Golay: generator matrix 12 rows × 24 bits = 36 bytes
        generator_bytes = 36
        # What a stored-table substrate would hold:
        codeword_table_bytes = 4096 * 3        # 12 KiB (24-bit words, packed)
        leech_minimal_bytes = 196560 * 24 * 2  # 16-bit coords × 24
        stored = codeword_table_bytes + leech_minimal_bytes
        ratio = stored // generator_bytes
        return "\n".join([
            f"stored {stored} B      generator {generator_bytes} B"
            f"      ratio {ratio} : 1",
            f"table_lookup counter: {self.count('table_lookup')}"
            f"  ({'ZERO — generated, not stored' if self.count('table_lookup') == 0 else 'NONZERO — audit failure'})",
        ])
