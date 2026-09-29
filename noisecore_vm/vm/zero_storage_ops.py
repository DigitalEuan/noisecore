"""
Zero-storage opcodes (0x66–0x6D) — syndrome, Leech decode, ledger, moving DS.
All operate on plain integers in registers/memory; exact arithmetic throughout.
"""

from ..core.syndrome import syndrome as _syndrome, is_golay as _is_golay
from ..decoder import decode as _decode, SCALE as _DEC_SCALE
from ..nrci import nrci_scaled as _nrci_scaled


def op_syn(cpu, rd, rs):
    """Rd = 12-bit syndrome of the 24-bit word in Rs (G-row route)."""
    word = cpu._read_reg(rs) & 0xFFFFFF
    v = _syndrome(word, cpu.ledger)
    cpu._write_reg(rd, v)
    cpu._update_flags(v)


def op_isgolay(cpu, rd, rs):
    """Rd = 1 iff the word in Rs is a Golay codeword (no table)."""
    word = cpu._read_reg(rs) & 0xFFFFFF
    v = 1 if _is_golay(word, cpu.ledger) else 0
    cpu._write_reg(rd, v)
    cpu._update_flags(v)


def op_decode(cpu, rd, rs):
    """
    Rs = base address of a 24-int target (units of 1/256).
    The nearest Leech point's 24 coords are written back to the same cells.
    Rd = total decode cost (Σ (256z−y)²).
    """
    base = cpu._read_reg(rs)
    target = [cpu._read_mem(base + i) for i in range(24)]
    res = _decode(target, ledger=cpu.ledger)
    for i, z in enumerate(res["point"]):
        cpu._write_mem(base + i, z)
    cpu._write_reg(rd, res["cost"])
    cpu._update_flags(res["cost"])


def op_ledger(cpu, rd, item):
    """Rd = current count of ledger item #item."""
    v = cpu.ledger.count(item)
    cpu._write_reg(rd, v)
    cpu._update_flags(v)


def op_mdsbit(cpu, rd):
    """Rd = next bit of the CPU's moving delta-sigma modulator."""
    if cpu._mds is None:
        raise RuntimeError("MDSRT must set a target before MDSBIT")
    v = cpu._mds.tick()
    cpu._write_reg(rd, v)
    cpu._update_flags(v)


def op_mdsrt(cpu, num, den):
    """Retarget the CPU's moving modulator to num/den WITHOUT zeroing acc."""
    from ..moving_ds import MovingDeltaSigma
    from fractions import Fraction
    if cpu._mds is None:
        cpu._mds = MovingDeltaSigma(Fraction(num, den), ledger=cpu.ledger)
    else:
        cpu._mds.retarget(Fraction(num, den))


def op_nrci2(cpu, rd, ra, rb):
    """
    Rd = 10⁶·NRCI between two 16-cell integer streams:
    reference at mem[Ra..Ra+15], residual at mem[Rb..Rb+15].
    """
    ax, ar = cpu._read_reg(ra), cpu._read_reg(rb)
    x = [cpu._read_mem(ax + i) for i in range(16)]
    r = [cpu._read_mem(ar + i) for i in range(16)]
    v = _nrci_scaled(x, r)
    cpu.ledger.int_sqrt()
    cpu._write_reg(rd, v)
    cpu._update_flags(v)


def op_cost(cpu, rd):
    """Rd = total ledger cost since last clear."""
    v = cpu.ledger.total()
    cpu._write_reg(rd, v)
    cpu._update_flags(v)


ZERO_STORAGE_OPS = {
    0x66: op_syn,
    0x67: op_isgolay,
    0x68: op_decode,
    0x69: op_ledger,
    0x6A: op_mdsbit,
    0x6B: op_mdsrt,
    0x6C: op_nrci2,
    0x6D: op_cost,
}
