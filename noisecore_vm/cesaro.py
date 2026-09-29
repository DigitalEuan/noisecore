"""
================================================================================
Cesàro dynamics on syndrome space  (Golay/Cesaro.lean, executable)
================================================================================
The perturbation chain on Syn = (ZMod 2)^12:

    step μ = f ↦ (∑_{k : Fin 24} μ(f + col k)) / 24

where `col k` is the k-th column of the parity-check matrix — obtained here
as syndrome(e_k), no table.  The chain is periodic and does NOT converge
pointwise; its time averages do:

    cesaro μ N f = (1/N) ∑_{n<N} (step^[n] μ) f  →  1/4096

with the proved explicit rate  |cesaro μ N f − 1/4096| ≤ 24/N
(cesaro_converges).  All laws are exact: dict[int, Fraction] over the
4096 syndromes.
"""

from __future__ import annotations
from fractions import Fraction
from typing import Dict

from .core.syndrome import syndrome

N_SYN = 4096
_COLS = None


def columns():
    """The 24 parity-check columns, generated as syndrome(e_k)."""
    global _COLS
    if _COLS is None:
        _COLS = [syndrome(1 << (23 - k)) for k in range(24)]
    return _COLS


Law = Dict[int, Fraction]


def delta_law(f: int = 0) -> Law:
    return {f & 0xFFF: Fraction(1)}


def total_mass(law: Law) -> Fraction:
    return sum(law.values(), Fraction(0))


def step(law: Law) -> Law:
    """One perturbation step: average over XOR with each of the 24 columns."""
    cols = columns()
    out: Law = {}
    inv24 = Fraction(1, 24)
    for f, p in law.items():
        for c in cols:
            g = f ^ c          # group addition in (ZMod 2)^12 is XOR
            out[g] = out.get(g, Fraction(0)) + p * inv24
    return out


def iterate(law: Law, n: int) -> Law:
    for _ in range(n):
        law = step(law)
    return law


def cesaro(law0: Law, N: int) -> Law:
    """(1/N) ∑_{n<N} step^[n] law0 — exact."""
    if N < 1:
        raise ValueError("N ≥ 1 required")
    acc: Law = {}
    law = law0
    inv = Fraction(1, N)
    for _ in range(N):
        for f, p in law.items():
            acc[f] = acc.get(f, Fraction(0)) + p
        law = step(law)
    return {f: p * inv for f, p in acc.items()}


def cesaro_value(law0: Law, N: int, f: int) -> Fraction:
    return cesaro(law0, N).get(f & 0xFFF, Fraction(0))


def cesaro_error(law0: Law, N: int, f: int) -> Fraction:
    """|cesaro_N(f) − 1/4096| — the quantity the theorem bounds."""
    return abs(cesaro_value(law0, N, f) - Fraction(1, N_SYN))


def bound_holds(law0: Law, N: int, f: int) -> bool:
    """cesaro_converges, executable: |err| ≤ 24/N."""
    return cesaro_error(law0, N, f) <= Fraction(24, N)
