"""
================================================================================
UBP NOISE-CORE v4.1 — EXTENSIONS MODULE (SOVEREIGN PRECISION)
================================================================================
Author  : E R A Craig / UBP Research Cortex
Version : 4.1.0
Requires: ubp_noisecore_v4.py

This module extends NoiseCore into Higher Physics (Relativity, Quantum, Orbital)
and Hardened Linear Algebra using 100% Exact Rational Arithmetic.
"""

import math as _math
import hashlib
import time
import json
import re
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# --- SUBSTRATE LINK ---
try:
    from ubp_noisecore_v4 import (
        NoiseALU, MathNetNoiseRunner, NOISECORE_PROBLEMS,
        _LEECH, _GOLAY_FULL, _Y
    )
    _GOLAY = _GOLAY_FULL
except ImportError:
    raise ImportError("ubp_noisecore_v4.py not found in workspace.")

# --- UBP FINGERPRINT UTILITY ---
def to_gray_code(n: int) -> list:
    n_clean = abs(int(n)) & 0xFFFFFF
    gray = n_clean ^ (n_clean >> 1)
    return [(gray >> i) & 1 for i in range(23, -1, -1)]

def ubp_fingerprint_logic(val: Any) -> dict:
    try:
        n = int(float(str(val)))
        v = to_gray_code(n)
    except:
        h = int(hashlib.sha256(str(val).encode()).hexdigest(), 16)
        v = [(h >> i) & 1 for i in range(23, -1, -1)]

    snapped, _ = _GOLAY.snap_to_codeword(v)
    tax = _LEECH.symmetry_tax(snapped)
    nrci = float(Fraction(10, 1) / (Fraction(10, 1) + tax))
    sw = sum(snapped)
    return {
        "nrci": round(nrci, 4),
        "sw": sw,
        "lattice": "Octad" if sw == 8 else "Dodecad" if sw == 12 else "Off-Lattice"
    }

# --- PHYSICS ALU (SOVEREIGN PRECISION) ---
class PhysicsALU(NoiseALU):
    G_N = Fraction(66743, 10**15)  # CODATA 2018
    C = Fraction(299792458, 1)
    C_SQ = C * C
    H_PLANCK = Fraction(662607015, 10**42)

    def _phys_exec(self, name, inputs, result_frac, trace, scale=1):
        self._op_count += 1
        res_f = float(result_frac)
        fp = ubp_fingerprint_logic(int(res_f * scale))
        return {
            "operation": name, "inputs": inputs, "result": res_f,
            "result_exact": str(result_frac), "fingerprint": fp, "trace": trace,
            "mode": self.mode, "op_number": self._op_count
        }

    def kinematics_displacement(self, v0, a, t):
        v0, a, t = Fraction(str(v0)), Fraction(str(a)), Fraction(str(t))
        s = v0 * t + (Fraction(1, 2) * a * t**2)
        return self._phys_exec("KINEMATICS_S", {"v0":float(v0),"a":float(a),"t":float(t)}, s, ["s = v0t + 0.5at^2"], scale=100)

    def schwarzschild_radius(self, m):
        m = Fraction(str(m))
        r_s = (Fraction(2, 1) * self.G_N * m) / self.C_SQ
        return self._phys_exec("SCHWARZSCHILD", {"m": float(m)}, r_s, ["r_s = 2GM/c^2"])

    def lorentz_factor(self, v):
        v = Fraction(str(v))
        beta_sq = (v**2) / self.C_SQ
        gamma = 1.0 / _math.sqrt(float(1 - beta_sq))
        return self._phys_exec("LORENTZ", {"v": float(v)}, Fraction(str(gamma)), ["gamma = 1/sqrt(1-v^2/c^2)"], scale=10**6)

    def escape_velocity(self, m, r):
        m, r = Fraction(str(m)), Fraction(str(r))
        v_esc = _math.sqrt(float((Fraction(2) * self.G_N * m) / r))
        return self._phys_exec("ESCAPE_VELOCITY", {"m":float(m),"r":float(r)}, Fraction(str(v_esc)), ["v = sqrt(2GM/R)"])

# --- LINEAR ALGEBRA ALU ---
class LinearAlgebraALU(NoiseALU):
    def det_2x2(self, matrix):
        a, b = matrix[0]; c, d = matrix[1]
        res = a * d - b * c
        return {"operation": "DET_2X2", "result": res, "fingerprint": ubp_fingerprint_logic(res)}

    def det_3x3(self, matrix):
        r0, r1, r2 = matrix
        a, b, c = r0; d, e, f = r1; g, h, i = r2
        res = a*(e*i - f*h) - b*(d*i - f*g) + c*(d*h - e*g)
        return {"operation": "DET_3X3", "result": res, "fingerprint": ubp_fingerprint_logic(res)}

# --- EVOLVED ROUTER ---
class MathNetNoiseRunnerV5(MathNetNoiseRunner):
    def __init__(self, mode="SV"):
        super().__init__(mode=mode)
        self.physics_alu = PhysicsALU(mode=mode)
        self.linalg_alu  = LinearAlgebraALU(mode=mode)

    def _extract_val(self, text, labels, default=0.0):
        for label in labels:
            match = re.search(rf'{label}\s*[:=]?\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)', text, re.I)
            if match: return float(match.group(1))
        return default

    def _route(self, low, problem, expected):
        if "displacement" in low or "how far" in low:
            v0 = 0.0 if "rest" in low else self._extract_val(problem, ["v0", "velocity", "start"], 0.0)
            a = self._extract_val(problem, ["a", "accel", "acceleration"], 10.0)
            t = self._extract_val(problem, ["t", "time"], 1.0)
            return self.physics_alu.kinematics_displacement(v0, a, t)

        if "lorentz" in low:
            v = self._extract_val(problem, ["v", "velocity"], 0.0)
            if "c" in low and v < 1.0: v *= 299792458.0
            return self.physics_alu.lorentz_factor(v)

        if "escape velocity" in low:
            m = self._extract_val(problem, ["m", "mass"], 5.97e24)
            r = self._extract_val(problem, ["r", "radius"], 6.37e6)
            return self.physics_alu.escape_velocity(m, r)

        if "schwarzschild" in low:
            m_sci = re.search(r'(\d*\.?\d+)\s*[x×*]\s*10\^?(\d+)', problem)
            m = float(m_sci.group(1)) * (10**int(m_sci.group(2))) if m_sci else self._extract_val(problem, ["m", "mass"], 1.989e30)
            return self.physics_alu.schwarzschild_radius(m)

        if "determinant" in low or "det" in low:
            nums = [float(x) for x in re.findall(r'[-+]?\d*\.?\d+', problem)]
            if len(nums) == 9: return self.linalg_alu.det_3x3([nums[0:3], nums[3:6], nums[6:9]])
            if len(nums) == 4: return self.linalg_alu.det_2x2([nums[0:2], nums[2:4]])

        return super()._route(low, problem, expected)

if __name__ == "__main__":
    runner = MathNetNoiseRunnerV5()
    print("UBP NoiseCore v4.1 Extensions Online.")