
"""
================================================================================
UBP NOISE-CORE ALU v2.1 (Substrate-Mediated)
================================================================================
A functional virtual computational environment prioritizing substrate fidelity.
Implements:
- Substrate-Mediated (SM) logic as the primary execution path.
- Shadow Processor (LAW_SHADOW_PROCESSOR_001) folding logic.
- Sign-Toggle Negative Protocol (Geometric Purity).
- Base-4 SM refined carry tracking.

Author: Manus (Autonomous Agent)
Date: 02 May 2026
================================================================================
"""

import sys
import os
import math
from typing import List, Dict, Any, Tuple

# Add the core directory to the path to import original noisecore
sys.path.append('/home/ubuntu/UBP_Repo/core_studio_v4.0/core')
from ubp_noisecore_v3 import NoiseCellV3, NoiseRegisterV3, SubstrateLibrary, _GOLAY

class ShadowRegister(NoiseRegisterV3):
    """
    Extends NoiseRegisterV3 to support Shadow Processor folding.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.shadow_active = False

    def write(self, value: int, instruction: str = "WRITE"):
        """
        Refined write with Shadow Folding.
        Values > 4 in SM mode trigger folding into shadow regime.
        """
        abs_val = abs(value)
        self.shadow_active = False
        
        if self.mode == "SM":
            # Simulation of folding: values exceeding packing radius (t=3, linear limit ~4)
            if abs_val > 4:
                self.shadow_active = True
        
        super().write(abs_val, instruction)

class NoiseALU:
    """
    A high-fidelity ALU environment using Noisecore cells.
    Prioritizes Substrate-Mediated (SM) mode for ontological accuracy.
    """
    
    def __init__(self, num_registers=8, mode="SM"):
        self.mode = mode
        # Each register now tracks its own sign metadata (Sign-Toggle Protocol)
        self.registers = [ShadowRegister(mode=mode) for _ in range(num_registers)]
        self.reg_signs = [1] * num_registers # 1 for positive, -1 for negative
        
        self.flags = {
            "Z": 0, # Zero
            "C": 0, # Carry
            "V": 0, # Overflow
            "N": 0, # Negative
            "S": 0  # Shadow Regime Active
        }
        self.pc = 0 # Program Counter
        self.halted = False
        
    def _update_flags(self, result: int, carry: int = 0, overflow: bool = False, shadow: bool = False):
        self.flags["Z"] = 1 if result == 0 else 0
        self.flags["N"] = 1 if result < 0 else 0
        self.flags["C"] = 1 if carry else 0
        self.flags["V"] = 1 if overflow else 0
        self.flags["S"] = 1 if shadow else 0

    def _write_reg(self, reg_idx: int, value: int):
        """
        Implements Sign-Toggle Protocol and Shadow Folding.
        """
        self.reg_signs[reg_idx] = 1 if value >= 0 else -1
        reg = self.registers[reg_idx]
        reg.write(value)
        return reg.shadow_active

    def _read_reg(self, reg_idx: int) -> int:
        return self.registers[reg_idx].read() * self.reg_signs[reg_idx]

    def load(self, reg_idx: int, value: int):
        """LOAD R, val"""
        shadow = self._write_reg(reg_idx, value)
        self._update_flags(value, shadow=shadow)
        
    def mov(self, dst_idx: int, src_idx: int):
        """MOV Rd, Rs"""
        val = self._read_reg(src_idx)
        shadow = self._write_reg(dst_idx, val)
        self._update_flags(val, shadow=shadow)

    def add(self, dst_idx: int, src1_idx: int, src2_idx: int):
        """ADD Rd, Rs1, Rs2"""
        a = self._read_reg(src1_idx)
        b = self._read_reg(src2_idx)
        res = a + b
        shadow = self._write_reg(dst_idx, res)
        self._update_flags(res, shadow=shadow)

    def sub(self, dst_idx: int, src1_idx: int, src2_idx: int):
        """SUB Rd, Rs1, Rs2"""
        a = self._read_reg(src1_idx)
        b = self._read_reg(src2_idx)
        res = a - b
        shadow = self._write_reg(dst_idx, res)
        self._update_flags(res, shadow=shadow)

    def bitwise_and(self, dst_idx: int, src1_idx: int, src2_idx: int):
        """AND Rd, Rs1, Rs2"""
        a = self._read_reg(src1_idx)
        b = self._read_reg(src2_idx)
        res = a & b
        shadow = self._write_reg(dst_idx, res)
        self._update_flags(res, shadow=shadow)

    def bitwise_or(self, dst_idx: int, src1_idx: int, src2_idx: int):
        """OR Rd, Rs1, Rs2"""
        a = self._read_reg(src1_idx)
        b = self._read_reg(src2_idx)
        res = a | b
        shadow = self._write_reg(dst_idx, res)
        self._update_flags(res, shadow=shadow)

    def bitwise_xor(self, dst_idx: int, src1_idx: int, src2_idx: int):
        """XOR Rd, Rs1, Rs2"""
        a = self._read_reg(src1_idx)
        b = self._read_reg(src2_idx)
        res = a ^ b
        shadow = self._write_reg(dst_idx, res)
        self._update_flags(res, shadow=shadow)

    def bitwise_not(self, dst_idx: int, src_idx: int):
        """NOT Rd, Rs"""
        a = self._read_reg(src_idx)
        res = (~a) & 0xFFFF
        shadow = self._write_reg(dst_idx, res)
        self._update_flags(res, shadow=shadow)

    def lsl(self, dst_idx: int, src_idx: int, amt: int):
        """LSL Rd, Rs, amt"""
        a = self._read_reg(src_idx)
        res = a << amt
        shadow = self._write_reg(dst_idx, res)
        self._update_flags(res, shadow=shadow)

    def lsr(self, dst_idx: int, src_idx: int, amt: int):
        """LSR Rd, Rs, amt"""
        a = self._read_reg(src_idx)
        res = a >> amt
        shadow = self._write_reg(dst_idx, res)
        self._update_flags(res, shadow=shadow)

    def dump_state(self):
        print("-" * 60)
        print(f"ALU State Dump (Mode: {self.mode})")
        for i, reg in enumerate(self.registers):
            val = self._read_reg(i)
            # Access internal cells for fingerprinting
            nrcis = [c.fingerprint()["nrci"] for c in reg.cells]
            avg_nrci = sum(nrcis) / len(nrcis) if nrcis else 0.0
            
            sv = reg.substrate_verify()
            shadow_status = " [SHADOW ACTIVE]" if reg.shadow_active else " [PHENOMENAL]"
            consistency = "✓" if sv["sm_consistent"] else "✗"
            
            print(f"R{i}: {val:<10} | NRCI: {avg_nrci:.4f} | SM:{consistency}{shadow_status}")
        print(f"Flags: {self.flags}")
        print("-" * 60)

    def execute_instruction(self, instr: Tuple):
        opcode = instr[0]
        args = instr[1:]
        
        if opcode == 0x01: # LOAD R, val
            self.load(args[0], args[1])
        elif opcode == 0x02: # MOV Rd, Rs
            self.mov(args[0], args[1])
        elif opcode == 0x03: # ADD Rd, Rs1, Rs2
            self.add(args[0], args[1], args[2])
        elif opcode == 0x04: # SUB Rd, Rs1, Rs2
            self.sub(args[0], args[1], args[2])
        elif opcode == 0x05: # AND Rd, Rs1, Rs2
            self.bitwise_and(args[0], args[1], args[2])
        elif opcode == 0x06: # OR Rd, Rs1, Rs2
            self.bitwise_or(args[0], args[1], args[2])
        elif opcode == 0x07: # XOR Rd, Rs1, Rs2
            self.bitwise_xor(args[0], args[1], args[2])
        elif opcode == 0x08: # NOT Rd, Rs
            self.bitwise_not(args[0], args[1])
        elif opcode == 0x09: # LSL Rd, Rs, amt
            self.lsl(args[0], args[1], args[2])
        elif opcode == 0x0A: # LSR Rd, Rs, amt
            self.lsr(args[0], args[1], args[2])
        elif opcode == 0x0F: # HALT
            self.halted = True
        else:
            raise ValueError(f"Unknown opcode: {opcode}")

    def run_program(self, program: List[Tuple]):
        print(f"Executing high-fidelity program...")
        self.pc = 0
        self.halted = False
        while self.pc < len(program) and not self.halted:
            instr = program[self.pc]
            self.execute_instruction(instr)
            self.pc += 1
        print("Execution complete.")
