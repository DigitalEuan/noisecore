"""
accelerate.py — fidelity-preserving accelerators for the NoiseCore VM.

Three tiers, each proven by fidelity_test.py to leave every observable
result identical (values, cycles, CPU trace hash, substrate fingerprint):

  tier 0  raw        — the NoiseCore tree exactly as shipped.
  tier 1  exact      — (a) share the NoiseCellV3 calibration across cells,
                       (b) lazy displacement-curve lookup (the shipped code
                           evaluates the fallback eagerly on every read),
                       (c) O(1) NoiseRegisterV3.read() via the cached value.
                       These change *how* the same numbers are obtained,
                       never the numbers. Register-level traces are still
                       recorded, with identical content.
  tier 2  turbo      — tier 1, plus stop recording per-write register
                       traces (NoiseRegisterV3._record). Results, cycles,
                       CPU trace hashes and fingerprints are unchanged;
                       only the internal per-write trace list is not
                       populated (it grows without bound on long runs).

Why each change is safe
-----------------------
(a) NoiseCellV3's baseline_sw / displacement_curve / elastic_limit are
    pure functions of (substrate, base): every cell of every register and
    of every memory word receives the identical substrate
    (SubstrateLibrary.PERFECT_V1) and base (12). The shipped code computes
    the same 13-point curve 8x per register cell and 8x per memory cell
    (27,459 snap_to_codeword calls to build a default CPU). We compute it
    once per (substrate, base) and copy the result into each cell.
(b) substrate_read() calls displacement_curve.get(k, self.probe_displacement(k))
    — Python evaluates the default argument eagerly, so probe_displacement
    (and its snap_to_codeword round trip) runs even when k is in the curve.
    An explicit membership test is semantically identical and skips it.
(c) NoiseRegisterV3.write() stores self._value and syncs digits to cells;
    read() reconstructs the same number from those digits. Checked against
    2,000 random 31-bit writes: reconstruction == cached value, always.
    read() returns the cached value; read_reconstructed() keeps the old
    algorithm available for audit.

Nothing in the shipped noisecore/ tree is modified: these are opt-in
runtime patches applied by apply(tier).  reset() restores the raw classes.
"""

from __future__ import annotations

import time
from typing import Dict, Tuple

_tier_applied = 0
_orig: Dict[str, object] = {}
_CAL_CACHE: Dict[Tuple[Tuple[int, ...], int], tuple] = {}


def applied_tier() -> int:
    return _tier_applied


def _module():
    _ensure_noisecore()
    import noisecore_vm.core.substrate as substrate_mod
    return substrate_mod


def _ensure_noisecore() -> None:
    """Locate the noisecore tree: $NOISECORE_PATH, or known lab location."""
    import os
    import sys
    try:
        import noisecore_vm  # noqa: F401
        return
    except ImportError:
        pass
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.environ.get("NOISECORE_PATH", ""),
        os.path.join(here, "..", "glm-noisecore-lab", "noisecore"),
        os.path.join(here, "..", "noisecore"),
        os.path.join(here, "noisecore"),
    ]
    for cand in candidates:
        if cand and os.path.isdir(os.path.join(cand, "noisecore_vm")):
            sys.path.insert(0, os.path.abspath(cand))
            return
    raise ImportError("noisecore_vm not found: set NOISECORE_PATH to the "
                      "noisecore repo root")


# ── tier 1 (a): shared cell calibration ──────────────────────────────────────

def _patch_calibration_cache() -> None:
    m = _module()
    NoiseCellV3 = m.NoiseCellV3
    SubstrateLibrary = m.SubstrateLibrary
    if "cell_init" not in _orig:
        _orig["cell_init"] = NoiseCellV3.__init__
    orig_init = _orig["cell_init"]

    def cached_init(self, substrate=None, base=12):
        effective = substrate if substrate else SubstrateLibrary.PERFECT_V1
        key = (tuple(effective), base)
        entry = _CAL_CACHE.get(key)
        if entry is None:
            # compute with the shipped logic once (no duplication of formulas)
            dummy = object.__new__(NoiseCellV3)
            orig_init(dummy, substrate, base)
            entry = (dummy.baseline_sw, dict(dummy.displacement_curve),
                     dummy.elastic_limit)
            _CAL_CACHE[key] = entry
        self.substrate = (substrate or SubstrateLibrary.PERFECT_V1[:])
        self.base = base
        self._value = 0
        self.baseline_sw = entry[0]
        self.displacement_curve = dict(entry[1])   # own copy: no aliasing
        self.elastic_limit = entry[2]

    NoiseCellV3.__init__ = cached_init


# ── tier 1 (b): lazy displacement-curve lookup ───────────────────────────────

def _patch_lazy_curve() -> None:
    m = _module()
    NoiseCellV3 = m.NoiseCellV3
    if "substrate_read" not in _orig:
        _orig["substrate_read"] = NoiseCellV3.substrate_read

    def substrate_read(self) -> dict:
        k = self._value
        curve = self.displacement_curve
        if k in curve:                       # was: curve.get(k, probe(k))
            disp = curve[k]                  #   (eager fallback — wasteful)
        else:
            disp = self.probe_displacement(k)
        return {
            "logical_value": k,
            "displacement": disp,
            "syndrome_weight": self.baseline_sw - disp,
            "sm_consistent": (disp == k),
        }

    NoiseCellV3.substrate_read = substrate_read


# ── tier 1 (c): O(1) register read ───────────────────────────────────────────

def _patch_cached_read() -> None:
    m = _module()
    NoiseRegisterV3 = m.NoiseRegisterV3
    if "read" not in _orig:
        _orig["read"] = NoiseRegisterV3.read

    def read(self) -> int:
        return self._value

    def read_reconstructed(self) -> int:
        return sum(cell.read() * (12 ** i) for i, cell in enumerate(self.cells))

    NoiseRegisterV3.read = read
    NoiseRegisterV3.read_reconstructed = read_reconstructed


# ── tier 2: elide per-write register traces ──────────────────────────────────

def _patch_elide_record() -> None:
    m = _module()
    NoiseRegisterV3 = m.NoiseRegisterV3
    if "_record" not in _orig:
        _orig["_record"] = NoiseRegisterV3._record

    def _record_noop(self, instruction: str, value: int) -> None:
        return None

    NoiseRegisterV3._record = _record_noop


# ── public API ───────────────────────────────────────────────────────────────

def apply(tier: int = 1) -> int:
    """Apply acceleration tier 0/1/2 (idempotent, monotone). Returns tier."""
    global _tier_applied
    if tier <= _tier_applied:
        return _tier_applied
    if tier >= 1 and _tier_applied < 1:
        _patch_calibration_cache()
        _patch_lazy_curve()
        _patch_cached_read()
        _tier_applied = 1
    if tier >= 2 and _tier_applied < 2:
        _patch_elide_record()
        _tier_applied = 2
    return _tier_applied


def reset() -> None:
    """Restore the shipped classes (for A/B testing in one process)."""
    global _tier_applied
    if not _orig:
        _tier_applied = 0
        return
    m = _module()
    if "cell_init" in _orig:
        m.NoiseCellV3.__init__ = _orig["cell_init"]
    if "substrate_read" in _orig:
        m.NoiseCellV3.substrate_read = _orig["substrate_read"]
    if "read" in _orig:
        m.NoiseRegisterV3.read = _orig["read"]
    if "_record" in _orig:
        m.NoiseRegisterV3._record = _orig["_record"]
    if hasattr(m.NoiseRegisterV3, "read_reconstructed"):
        del m.NoiseRegisterV3.read_reconstructed
    _orig.clear()
    _tier_applied = 0


def timed_build(memory_size: int = 256, word_bits: int = 32) -> float:
    """Seconds to build a substrate CPU — the number the tiers move."""
    _ensure_noisecore()
    from noisecore_vm import CPU
    t0 = time.perf_counter()
    CPU(word_bits=word_bits, substrate_mode=True, memory_size=memory_size)
    return time.perf_counter() - t0
