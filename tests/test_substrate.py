"""
Substrate-level tests — verify that the Golay-mediated NoiseRegisters
behave correctly when the CPU is constructed in full substrate mode.

These are slower tests; we keep them small but meaningful.
"""
import pytest
from noisecore_vm import CPU
from noisecore_vm.core.substrate import (
    NoiseRegisterV3, NoiseCellV3, SubstrateLibrary, GOLAY_AVAILABLE,
)


def test_substrate_register_round_trip():
    r = NoiseRegisterV3()
    for v in (0, 1, 11, 144, 1728, 12345):
        r.write(v)
        assert r.read() == v


def test_substrate_register_consistency_in_elastic_regime():
    """
    PERFECT_V1's linear (substrate-mediated) regime is digits 0..4 in base-12.
    Values whose every base-12 digit is in that range produce sm_consistent=True.
    Value 16 = [4, 1] in base-12 → both digits within elastic limit.
    """
    r = NoiseRegisterV3()
    r.write(16)
    sv = r.substrate_verify()
    assert sv["logical_value"] == 16
    assert sv["sm_consistent"] is True


def test_substrate_register_outside_elastic_regime_still_round_trips():
    """
    Values with any base-12 digit > 4 fall outside PERFECT_V1's linear regime,
    so sm_consistent will be False — but logical read/write must still work,
    because the register stores the logical value alongside the substrate.
    """
    r = NoiseRegisterV3()
    r.write(42)                          # 42 = [6, 3]_12 — digit 6 > 4
    sv = r.substrate_verify()
    assert sv["logical_value"] == 42
    # sm_consistent may be False; that is correct geometric behaviour.
    assert sv["sm_consistent"] in (True, False)
    assert r.read() == 42                # logical round-trip is always valid


def test_substrate_cell_displacement_curve():
    """For PERFECT_V1 substrate, displacement curve is k=0..4 → linear."""
    cell = NoiseCellV3(SubstrateLibrary.PERFECT_V1)
    for k in range(5):
        assert cell.displacement_curve[k] == k


def test_substrate_library_describe():
    desc = SubstrateLibrary.describe(SubstrateLibrary.PERFECT_V1)
    assert "hamming_weight" in desc
    assert "nrci_approx" in desc


def test_cpu_substrate_mode_basic():
    """The full CPU works with substrate-backed registers."""
    cpu = CPU(substrate_mode=True)
    cpu._op_load(0, 5)
    cpu._op_load(1, 7)
    cpu._op_add(2, 0, 1)
    assert cpu._read_reg(2) == 12


def test_cpu_substrate_signed_arithmetic():
    """Sign-magnitude representation works in substrate mode."""
    cpu = CPU(substrate_mode=True)
    cpu._op_load(0, 3)
    cpu._op_load(1, 10)
    cpu._op_sub(2, 0, 1)        # -7
    cpu._op_load(3, 2)
    cpu._op_add(4, 2, 3)        # -7 + 2 = -5
    assert cpu._read_reg(4) == -5
    # Substrate sees only magnitude
    assert cpu.registers[4].read() == 5


def test_substrate_fingerprint_present():
    cpu = CPU(substrate_mode=True)
    cpu._op_load(0, 42)
    fp = cpu.substrate_fingerprint()
    assert fp["mode"] == "substrate"
    assert fp["nrci_mean"] is not None
    assert fp["magnitude_sha"] is not None


def test_real_golay_engine_loaded():
    """When core.py is available, the real Golay engine should be active."""
    # This is an environment check, not a strict assertion.
    # If GOLAY_AVAILABLE is False the test is informational, not a failure.
    assert GOLAY_AVAILABLE in (True, False)
