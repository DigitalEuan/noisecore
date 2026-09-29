"""
ISA-level delta-sigma / mantissa opcodes.

These are added to the CPU's execute() dispatcher as opcodes 0x60–0x63.
They all operate on exact integer arithmetic and call into the Fraction-based
delta_sigma module.  The "register value" they write is always an integer
(never a float), so the existing sign-magnitude substrate registers handle
them without modification.
"""

from fractions import Fraction

from ..delta_sigma import DeltaSigma, dyadic_orbit, odd_orbit


def _fixed_point(frac: Fraction, scale: int = 1_000_000) -> int:
    """Convert an exact Fraction to a scaled integer (floor)."""
    return (frac.numerator * scale) // frac.denominator


def op_dsstate(cpu, r, num, den):
    """Rd = floor(state_n at tick=0 of modulator on num/den × 10^6).
    At tick 0, state is always 0 — this is mostly a sanity opcode."""
    ds = DeltaSigma(Fraction(num, den))
    v = _fixed_point(ds.state(0))
    cpu._write_reg(r, v)
    cpu._update_flags(v)


def op_dsbit(cpu, r, n, num, den):
    """Rd = bit_n of the delta-sigma modulator on target num/den."""
    ds = DeltaSigma(Fraction(num, den))
    v = ds.bit(cpu._read_reg(n))
    cpu._write_reg(r, v)
    cpu._update_flags(v)


def op_dsavg(cpu, r, n, num, den):
    """Rd = average of first n bits of num/den × 10^6 (floor)."""
    ds = DeltaSigma(Fraction(num, den))
    v = _fixed_point(ds.average(n))
    cpu._write_reg(r, v)
    cpu._update_flags(v)


def op_dsones(cpu, r, n, num, den):
    """Rd = count of 1s in first n bits of num/den (= ⌊n·num/den⌋ exactly)."""
    ds = DeltaSigma(Fraction(num, den))
    v = ds.ones(n)
    cpu._write_reg(r, v)
    cpu._update_flags(v)


def op_dyorbit(cpu, r, k, n, m):
    """Rd = (2^n · m) mod 2^k.   Dyadic orbit step n."""
    v = dyadic_orbit(k, cpu._read_reg(n), m)
    cpu._write_reg(r, v)
    cpu._update_flags(v)


def op_odorbit(cpu, r, p, n):
    """Rd = 2^n mod p.   Odd orbit step n."""
    v = odd_orbit(p, cpu._read_reg(n))
    cpu._write_reg(r, v)
    cpu._update_flags(v)


# Dispatch table — inserted into CPU.execute()
DELTA_SIGMA_OPS = {
    0x60: op_dsstate,    # DSSTATE  R, #num, #den        (target init, sanity)
    0x61: op_dsbit,      # DSBIT    R, #n, #num, #den    (single bit)
    0x62: op_dsavg,      # DSAVG    R, #n, #num, #den    (avg × 10^6)
    0x63: op_dsones,     # DSONES   R, #n, #num, #den    (exact ⌊n·t⌋)
    0x64: op_dyorbit,    # DYORBIT  R, #k, #n, #m        (dyadic doubling map)
    0x65: op_odorbit,    # ODORBIT  R, #p, #n            (odd doubling map)
}
