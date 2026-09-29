"""v1.3.0 — zero storage all the way down: cells verify by syndrome, not table."""
import random

from noisecore_vm.core.zs import (
    verify_cell_zero_storage, golay_weight_census, zero_storage_audit,
)
from noisecore_vm.core.syndrome import syndrome, is_golay, bits_to_word, word_to_bits
from noisecore_vm.core.golay_engine import GOLAY_ENGINE
from noisecore_vm.core.substrate import NoiseCellV3, NoiseRegisterV3, SubstrateLibrary
from noisecore_vm.ledger import Ledger
from noisecore_vm import CPU


class TestCellLevelSyndromeRoute:
    def test_perfect_substrate_verifies_without_table(self):
        led = Ledger()
        cell = NoiseCellV3(SubstrateLibrary.PERFECT_V1)
        out = cell.substrate_verify_zs(led)
        assert out["route"] == "syndrome (zero-storage)"
        assert out["table_lookups"] == 0
        assert led.count("table_lookup") == 0
        assert led.count("parity_check") == 12          # exactly 12 parities

    def test_codeword_cells_detected(self):
        octad = GOLAY_ENGINE.get_octads()[0]
        out = verify_cell_zero_storage(octad)
        assert out["is_codeword"] is True
        assert out["lattice_class"] == "Octad"

    def test_non_codeword_cell_carries_syndrome(self):
        bits = word_to_bits(0x000001)                     # weight 1
        out = verify_cell_zero_storage(bits)
        assert out["is_codeword"] is False
        assert out["syndrome"] != 0                       # syndrome IS the info

    def test_route_agrees_with_engine_membership(self):
        """Syndrome route vs the engine's decoder on 512 random cells."""
        rng = random.Random(0x1EEC4)
        for _ in range(512):
            bits = [rng.randint(0, 1) for _ in range(24)]
            zs = verify_cell_zero_storage(bits)
            msg, ok, errs = GOLAY_ENGINE.decode(bits)
            assert zs["is_codeword"] == (errs == 0)

    def test_register_audit_all_cells(self):
        led = Ledger()
        reg = NoiseRegisterV3()
        reg.write(42)
        audit = reg.substrate_audit_zs(led)
        assert audit["logical_value"] == 42
        assert led.count("table_lookup") == 0
        assert len(audit["cells"]) == len(reg.cells)


class TestCensus:
    def test_weight_distribution_matches_theory(self):
        """Golay.Census: counts at weights 0,8,12,16,24 = 1,759,2576,759,1."""
        c = golay_weight_census()
        assert c[0] == 1 and c[8] == 759 and c[12] == 2576
        assert c[16] == 759 and c[24] == 1
        assert sum(c.values()) == 4096
        assert set(c) == {0, 8, 12, 16, 24}               # minimum distance 8

    def test_every_codeword_zero_syndrome_all_down(self):
        for cw in GOLAY_ENGINE.get_all_codewords():
            assert verify_cell_zero_storage(cw)["is_codeword"] is True


class TestCPUTripWire:
    def test_substrate_mode_run_keeps_table_lookup_zero(self):
        cpu = CPU(substrate_mode=True)
        cpu._op_load(0, 42)
        cpu._op_load(1, 7)
        cpu._op_add(2, 0, 1)
        # verify every register through the zero-storage route
        for reg in cpu.registers:
            reg.substrate_audit_zs(cpu.ledger)
        assert cpu._read_reg(2) == 49
        assert cpu.ledger.count("table_lookup") == 0

    def test_audit_reports_ratio_and_tripwire(self):
        led = Ledger()
        syndrome(0xABCDEF, led)
        audit = zero_storage_audit(led)
        assert audit["zero_storage_intact"] is True
        assert audit["census"][8] == 759
        assert "ratio" in audit["audit_text"]
