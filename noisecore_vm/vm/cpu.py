"""
================================================================================
NoiseCore VM — CPU (Central Processing Unit)
================================================================================
The full virtual processor.  Builds on the substrate-mediated NoiseRegisterV3
from noisecore_vm.core.substrate, adding:

  • A complete, signed-aware ISA (see vm/isa.py)
  • A flag register {Z, N, C, V}
  • A program counter (PC) and configurable stack pointer (R7 by convention)
  • A 256-cell main memory (also substrate-backed)
  • A device bus for memory-mapped I/O (console, etc.)
  • A trace recorder (every instruction + flag transition + NRCI snapshot)
  • Configurable word width (8, 16, 32, 64 bits)
  • Cycle counter & instruction counter

Sign-magnitude representation
-----------------------------
The Golay substrate inherently stores unsigned magnitudes (geometric
displacement is non-negative).  Sign lives in a parallel bit array at the
CPU layer — this is the cleanest way to keep the substrate physically valid
while allowing full integer arithmetic at the ISA level.

Author: E R A Craig / UBP Research Cortex — May 2026
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..core.substrate import NoiseRegisterV3, ShadowRegister, SubstrateALU
from .isa import ISA, SYSCALL_NAMES


# ── DEVICE BUS ──────────────────────────────────────────────────────────────

class Device:
    """Base class for memory-mapped or syscall-driven devices."""

    name: str = "device"

    def on_syscall(self, cpu: "CPU", syscall_num: int) -> None:
        """Called when a SYSCALL instruction targets this device."""
        raise NotImplementedError

    def reset(self) -> None:
        """Reset device state."""
        pass


class ConsoleDevice(Device):
    """
    Buffered console.  Captures everything the running program prints so we
    can verify output in tests without going through stdout.
    """

    name = "console"

    def __init__(self, echo: bool = False):
        self.buffer: List[str] = []
        self.echo = echo
        self.input_queue: List[int] = []   # pre-loaded values for READ_INT

    def write(self, s: str) -> None:
        self.buffer.append(s)
        if self.echo:
            import sys as _sys
            _sys.stdout.write(s)
            _sys.stdout.flush()

    def reset(self) -> None:
        self.buffer.clear()

    def output(self) -> str:
        return "".join(self.buffer)

    def on_syscall(self, cpu: "CPU", syscall_num: int) -> None:
        if syscall_num == 1:        # PRINT_INT
            self.write(str(cpu._read_reg(0)))
        elif syscall_num == 2:      # PRINT_CHAR
            cp = cpu._read_reg(0) & 0x10FFFF
            self.write(chr(cp))
        elif syscall_num == 3:      # PRINT_STR (zero-terminated)
            addr = cpu._read_reg(0) & 0xFFFF
            chars: List[str] = []
            while addr < len(cpu.memory):
                ch = cpu._read_mem(addr)
                if ch == 0:
                    break
                chars.append(chr(ch & 0x10FFFF))
                addr += 1
            self.write("".join(chars))
        elif syscall_num == 4:      # READ_INT
            v = self.input_queue.pop(0) if self.input_queue else 0
            cpu._write_reg(0, v)
        elif syscall_num == 5:      # EXIT
            cpu.halted = True
            cpu.exit_code = cpu._read_reg(0)
        elif syscall_num == 6:      # PRINT_NL
            self.write("\n")
        elif syscall_num == 7:      # DUMP_REGS
            self.write(cpu.format_state() + "\n")
        else:
            raise ValueError(f"Unknown syscall: {syscall_num}")


# ── CPU CORE ────────────────────────────────────────────────────────────────

@dataclass
class TraceEntry:
    pc: int
    instr: Tuple
    mnemonic: str
    flags_before: Dict[str, int]
    flags_after: Dict[str, int]
    cycle: int


class CPU:
    """
    NoiseCore Virtual CPU.

    Public attributes
    -----------------
    registers      : list[ShadowRegister]    — R0..R(N-1)  (substrate_mode=True)
                     list[_PlainReg]          — R0..R(N-1)  (substrate_mode=False)
    memory         : list[NoiseRegisterV3]   — main memory cells
    flags          : dict[str,int]           — {'Z','N','C','V','S'}
    pc             : int                     — program counter
    halted         : bool
    cycles         : int                     — instructions executed
    word_bits      : int                     — 8, 16, 32, 64
    sp_register    : int                     — index of register used as SP (default 7)
    devices        : list[Device]
    trace          : list[TraceEntry]        — populated when trace=True

    Flags
    -----
    Z  Zero          — result == 0
    N  Negative      — result < 0
    C  Carry/Borrow  — unsigned overflow on add / borrow on sub
    V  Overflow      — signed overflow
    S  Shadow        — one or more registers are in the Shadow Regime
                       (LAW_SHADOW_PROCESSOR_001): their stored digit(s)
                       exceed the Golay elastic limit (4), meaning the
                       computation has crossed the Voronoi boundary of the
                       linear phenomenal plane.  S is a *latching* flag —
                       once set it remains set until an explicit CLRS
                       instruction (opcode 0x52) or a cpu.reset().
                       Only meaningful when substrate_mode=True; always 0
                       in plain-int mode.

    Conventions
    -----------
    • R7 is the stack pointer (SP) by convention — initialised to MEMORY_SIZE-1
      and grows downward (PUSH decrements, POP increments).
    • The dedicated `call_stack` list holds return addresses for CALL/RET,
      kept separate from the data stack (R7/SP) as a deliberate ABI choice:
      this prevents a data-stack imbalance from corrupting control flow,
      matches the behaviour of hardware CPUs that use a link-register or
      separate call stack (e.g. ARM Cortex-M), and simplifies recursive
      programs (see examples/03_factorial_recursive.nca). If you want the
      return address visible on the data stack for inspection, PUSH the
      return address manually before CALL and pop it after RET.
    """

    DEFAULT_NUM_REGISTERS = 8
    DEFAULT_MEMORY_SIZE   = 256
    DEFAULT_WORD_BITS     = 16
    SP_REGISTER           = 7   # R7 is SP

    def __init__(
        self,
        num_registers: int = DEFAULT_NUM_REGISTERS,
        memory_size:   int = DEFAULT_MEMORY_SIZE,
        word_bits:     int = DEFAULT_WORD_BITS,
        mode:          str = "SV",
        substrate_mode: bool = True,
        trace:         bool = False,
        max_cycles:    int = 1_000_000,
    ):
        self.mode = mode
        self.word_bits = word_bits
        self._word_max = (1 << word_bits) - 1
        self._word_signed_max =  (1 << (word_bits - 1)) - 1
        self._word_signed_min = -(1 << (word_bits - 1))
        self.num_registers = num_registers
        self.memory_size = memory_size
        self.substrate_mode = substrate_mode  # if False, use plain ints (much faster)
        self.max_cycles = max_cycles

        # Registers
        if substrate_mode:
            self.registers: List[ShadowRegister] = [
                ShadowRegister(mode=mode) for _ in range(num_registers)
            ]
        else:
            self.registers = [_PlainReg() for _ in range(num_registers)]
        self._signs: List[bool] = [False] * num_registers

        # Memory (NoiseRegisterV3 — no shadow tracking needed for memory cells)
        if substrate_mode:
            self.memory: List[NoiseRegisterV3] = [
                NoiseRegisterV3(mode=mode) for _ in range(memory_size)
            ]
        else:
            self.memory = [_PlainReg() for _ in range(memory_size)]
        self._mem_signs: List[bool] = [False] * memory_size

        # CPU state — S flag added for Shadow Processor (LAW_SHADOW_PROCESSOR_001)
        self.flags: Dict[str, int] = {"Z": 0, "C": 0, "V": 0, "N": 0, "S": 0}
        self.pc = 0
        self.halted = False
        self.exit_code = 0
        self.cycles = 0

        # Stack pointer initialised to last memory cell
        self._signs[self.SP_REGISTER] = False
        self.registers[self.SP_REGISTER].write(memory_size - 1)

        # Subroutine call stack (separate from data stack)
        self.call_stack: List[int] = []

        # Devices
        self.console = ConsoleDevice()
        self.devices: List[Device] = [self.console]

        # Trace
        self.do_trace = trace
        self.trace: List[TraceEntry] = []

    # ── REGISTER / MEMORY ACCESSORS ─────────────────────────────────────

    def _write_reg(self, idx: int, value: int) -> None:
        self._signs[idx] = value < 0
        self.registers[idx].write(abs(value))
        # Latch the S (Shadow) flag if this register entered the Shadow Regime.
        # S is latching: once set it stays set until CLRS or reset().
        # Only ShadowRegister (substrate_mode=True) carries shadow_active.
        if self.substrate_mode and hasattr(self.registers[idx], "shadow_active"):
            if self.registers[idx].shadow_active:
                self.flags["S"] = 1

    def _read_reg(self, idx: int) -> int:
        mag = self.registers[idx].read()
        return -mag if self._signs[idx] and mag != 0 else mag

    def _write_mem(self, addr: int, value: int) -> None:
        if not (0 <= addr < self.memory_size):
            raise IndexError(f"Memory write out of bounds: addr={addr}")
        self._mem_signs[addr] = value < 0
        self.memory[addr].write(abs(value))

    def _read_mem(self, addr: int) -> int:
        if not (0 <= addr < self.memory_size):
            raise IndexError(f"Memory read out of bounds: addr={addr}")
        mag = self.memory[addr].read()
        return -mag if self._mem_signs[addr] and mag != 0 else mag

    # ── FLAGS ──────────────────────────────────────────────────────────

    def _update_flags(self, result: int, *, carry: int = 0,
                      overflow: bool = False) -> None:
        self.flags["Z"] = 1 if result == 0 else 0
        self.flags["N"] = 1 if result < 0 else 0
        self.flags["C"] = 1 if carry else 0
        self.flags["V"] = 1 if overflow else 0

    def _add_flags(self, a: int, b: int, result: int, *,
                   carry_out: bool = None) -> None:
        if carry_out is None:
            carry_out = (abs(a) + abs(b)) > self._word_max
        overflow = (
            (a >= 0 and b >= 0 and result < 0) or
            (a < 0 and b < 0 and result >= 0) or
            result > self._word_signed_max or result < self._word_signed_min
        )
        self._update_flags(result, carry=int(carry_out), overflow=overflow)

    def _sub_flags(self, a: int, b: int, result: int, *,
                   borrow_out: bool = None) -> None:
        if borrow_out is None:
            borrow_out = a < b
        overflow = (
            (a >= 0 and b < 0 and result < 0) or
            (a < 0 and b >= 0 and result >= 0) or
            result > self._word_signed_max or result < self._word_signed_min
        )
        self._update_flags(result, carry=int(borrow_out), overflow=overflow)

    # ── INSTRUCTION EXECUTION ──────────────────────────────────────────

    def execute(self, instr: Tuple) -> None:
        """Decode + dispatch a single instruction tuple."""
        opcode = instr[0]
        args = instr[1:]
        flags_before = dict(self.flags) if self.do_trace else None

        # ── arithmetic / logic ──
        if   opcode == 0x01: self._op_load(*args)
        elif opcode == 0x02: self._op_mov(*args)
        elif opcode == 0x03: self._op_add(*args)
        elif opcode == 0x04: self._op_sub(*args)
        elif opcode == 0x05: self._op_and(*args)
        elif opcode == 0x06: self._op_or(*args)
        elif opcode == 0x07: self._op_xor(*args)
        elif opcode == 0x08: self._op_not(*args)
        elif opcode == 0x09: self._op_lsl(*args)
        elif opcode == 0x0A: self._op_lsr(*args)
        elif opcode == 0x0B: self._op_mul(*args)
        elif opcode == 0x0C: self._op_div(*args)
        elif opcode == 0x0D: self._op_mod(*args)
        elif opcode == 0x0E: self._op_cmp(*args)
        elif opcode == 0x0F: self.halted = True
        # ── control flow ──
        elif opcode == 0x10: self.pc = args[0] - 1
        elif opcode == 0x11:
            if self.flags["Z"]: self.pc = args[0] - 1
        elif opcode == 0x12:
            if not self.flags["Z"]: self.pc = args[0] - 1
        elif opcode == 0x13:
            if self.flags["N"]: self.pc = args[0] - 1
        elif opcode == 0x14:
            if not self.flags["N"]: self.pc = args[0] - 1
        elif opcode == 0x15:
            if self.flags["C"]: self.pc = args[0] - 1
        elif opcode == 0x16:                                       # JE
            if self.flags["Z"]: self.pc = args[0] - 1
        elif opcode == 0x17:                                       # JNE
            if not self.flags["Z"]: self.pc = args[0] - 1
        elif opcode == 0x18:                                       # JG  (signed >)
            if (not self.flags["Z"]) and (self.flags["N"] == self.flags["V"]):
                self.pc = args[0] - 1
        elif opcode == 0x19:                                       # JL  (signed <)
            if self.flags["N"] != self.flags["V"]:
                self.pc = args[0] - 1
        elif opcode == 0x1A:                                       # JGE
            if self.flags["N"] == self.flags["V"]:
                self.pc = args[0] - 1
        elif opcode == 0x1B:                                       # JLE
            if self.flags["Z"] or (self.flags["N"] != self.flags["V"]):
                self.pc = args[0] - 1
        # ── immediate-mode ──
        elif opcode == 0x20: self._op_addi(*args)
        elif opcode == 0x21: self._op_subi(*args)
        elif opcode == 0x22: self._op_muli(*args)
        elif opcode == 0x23: self._op_andi(*args)
        elif opcode == 0x24: self._op_ori(*args)
        elif opcode == 0x25: self._op_cmpi(*args)
        # ── memory ──
        elif opcode == 0x30: self._op_store(*args)
        elif opcode == 0x31: self._op_load_mem(*args)
        elif opcode == 0x32: self._op_storei(*args)
        elif opcode == 0x33: self._op_loadi(*args)
        elif opcode == 0x34: self._op_storex(*args)
        elif opcode == 0x35: self._op_loadx(*args)
        # ── stack & subroutines ──
        elif opcode == 0x40: self._op_push(*args)
        elif opcode == 0x41: self._op_pop(*args)
        elif opcode == 0x42: self._op_call(*args)
        elif opcode == 0x43: self._op_ret()
        # ── syscalls ──
        elif opcode == 0x50: self._op_syscall(*args)
        elif opcode == 0x51: pass   # NOP
        elif opcode == 0x52: self.flags["S"] = 0  # CLRS — clear Shadow flag

        else:
            raise ValueError(f"Unknown opcode: 0x{opcode:02X}")

        if self.do_trace and flags_before is not None:
            spec = ISA.get(opcode)
            self.trace.append(TraceEntry(
                pc=self.pc,
                instr=instr,
                mnemonic=spec.mnemonic if spec else "?",
                flags_before=flags_before,
                flags_after=dict(self.flags),
                cycle=self.cycles,
            ))

    # ─── Substrate-native arithmetic helpers ──────────────────────────────────
    #
    # When substrate_mode=True these helpers route through SubstrateALU so that
    # all ADD/SUB/MUL/DIV operate digit-by-digit on the base-12 cell arrays
    # (LAW_SUBSTRATE_ALU_001/002/003/004).  In plain mode they fall back to
    # Python operators, which is correct and fast for non-substrate workloads.
    #
    # Every method returns the signed integer result for flag computation.
    # The ALU writes the magnitude directly into the destination register;
    # the sign is stored separately in self._signs[rd].

    def _sau_add(self, rd: int, rs1: int, rs2: int) -> tuple:
        """
        Substrate-native signed ADD.
        Returns (signed_result: int, carry_out: bool).
        """
        if self.substrate_mode:
            ra, rb, rdst = self.registers[rs1], self.registers[rs2], self.registers[rd]
            sa, sb = self._signs[rs1], self._signs[rs2]
            result_neg, carry_out, _ = SubstrateALU.add(ra, sa, rb, sb, rdst)
            self._signs[rd] = result_neg
            # Latch S flag
            if rdst.shadow_active:
                self.flags["S"] = 1
            signed_result = self._read_reg(rd)
            return signed_result, carry_out
        # Plain mode
        a, b = self._read_reg(rs1), self._read_reg(rs2)
        r = a + b
        self._write_reg(rd, r)
        return r, abs(a) + abs(b) > self._word_max

    def _sau_sub(self, rd: int, rs1: int, rs2: int) -> tuple:
        """
        Substrate-native signed SUB.
        Returns (signed_result: int, borrow_out: bool).
        """
        if self.substrate_mode:
            ra, rb, rdst = self.registers[rs1], self.registers[rs2], self.registers[rd]
            sa, sb = self._signs[rs1], self._signs[rs2]
            result_neg, borrow_out, _ = SubstrateALU.sub(ra, sa, rb, sb, rdst)
            self._signs[rd] = result_neg
            if rdst.shadow_active:
                self.flags["S"] = 1
            signed_result = self._read_reg(rd)
            return signed_result, borrow_out
        a, b = self._read_reg(rs1), self._read_reg(rs2)
        r = a - b
        self._write_reg(rd, r)
        return r, a < b

    def _sau_add_imm(self, rd: int, rs: int, imm: int) -> tuple:
        """
        Substrate-native signed ADDI (register + immediate).
        Loads the immediate into a temporary ShadowRegister, then delegates to add().
        Returns (signed_result: int, carry_out: bool).
        """
        if self.substrate_mode:
            ra = self.registers[rs]
            sa = self._signs[rs]
            # Immediate has its own sign
            si = imm < 0
            tmp = ShadowRegister(mode=ra.mode)
            tmp.write(abs(imm))
            rdst = self.registers[rd]
            result_neg, carry_out, _ = SubstrateALU.add(ra, sa, tmp, si, rdst)
            self._signs[rd] = result_neg
            if rdst.shadow_active:
                self.flags["S"] = 1
            return self._read_reg(rd), carry_out
        a = self._read_reg(rs)
        r = a + imm
        self._write_reg(rd, r)
        return r, abs(a) + abs(imm) > self._word_max

    def _sau_sub_imm(self, rd: int, rs: int, imm: int) -> tuple:
        """Substrate-native signed SUBI. Returns (signed_result, borrow_out)."""
        if self.substrate_mode:
            ra = self.registers[rs]
            sa = self._signs[rs]
            si = imm < 0
            tmp = ShadowRegister(mode=ra.mode)
            tmp.write(abs(imm))
            rdst = self.registers[rd]
            result_neg, borrow_out, _ = SubstrateALU.sub(ra, sa, tmp, si, rdst)
            self._signs[rd] = result_neg
            if rdst.shadow_active:
                self.flags["S"] = 1
            return self._read_reg(rd), borrow_out
        a = self._read_reg(rs)
        r = a - imm
        self._write_reg(rd, r)
        return r, a < imm

    # ── INSTRUCTION IMPLEMENTATIONS ───────────────────────────────────

    def _op_load(self, rd, imm):
        self._write_reg(rd, imm)
        self._update_flags(imm)

    def _op_mov(self, rd, rs):
        v = self._read_reg(rs)
        self._write_reg(rd, v)
        self._update_flags(v)

    def _op_add(self, rd, rs1, rs2):
        a, b = self._read_reg(rs1), self._read_reg(rs2)
        r, carry_out = self._sau_add(rd, rs1, rs2)
        self._add_flags(a, b, r, carry_out=carry_out)

    def _op_sub(self, rd, rs1, rs2):
        a, b = self._read_reg(rs1), self._read_reg(rs2)
        r, borrow_out = self._sau_sub(rd, rs1, rs2)
        self._sub_flags(a, b, r, borrow_out=borrow_out)

    def _op_mul(self, rd, rs1, rs2):
        if self.substrate_mode:
            sa, sb = self._signs[rs1], self._signs[rs2]
            result_neg = SubstrateALU.mul(
                self.registers[rs1], sa,
                self.registers[rs2], sb,
                self.registers[rd],
            )
            self._signs[rd] = result_neg
            if self.registers[rd].shadow_active:
                self.flags["S"] = 1
            r = self._read_reg(rd)
        else:
            a, b = self._read_reg(rs1), self._read_reg(rs2)
            r = a * b
            self._write_reg(rd, r)
        self._update_flags(r)

    def _op_div(self, rd, rs1, rs2):
        if self.registers[rs2].read() == 0 and not self._signs[rs2]:
            # Fast zero-check without reading full int
            b_zero = all(c.read() == 0 for c in self.registers[rs2].cells) \
                if self.substrate_mode else (self._read_reg(rs2) == 0)
        else:
            b_zero = False
        if self.substrate_mode:
            b_zero = all(c.read() == 0 for c in self.registers[rs2].cells)
        else:
            b_zero = self._read_reg(rs2) == 0
        if b_zero:
            raise ZeroDivisionError(f"DIV: R{rs2} is zero")
        if self.substrate_mode:
            sa, sb = self._signs[rs1], self._signs[rs2]
            q_neg, _ = SubstrateALU.divmod(
                self.registers[rs1], sa,
                self.registers[rs2], sb,
                self.registers[rd], None,
            )
            self._signs[rd] = q_neg
            if self.registers[rd].shadow_active:
                self.flags["S"] = 1
            r = self._read_reg(rd)
        else:
            a, b = self._read_reg(rs1), self._read_reg(rs2)
            sign = (a < 0) ^ (b < 0)
            q = abs(a) // abs(b)
            r = -q if sign and q != 0 else q
            self._write_reg(rd, r)
        self._update_flags(r)

    def _op_mod(self, rd, rs1, rs2):
        if self.substrate_mode:
            b_zero = all(c.read() == 0 for c in self.registers[rs2].cells)
        else:
            b_zero = self._read_reg(rs2) == 0
        if b_zero:
            raise ZeroDivisionError(f"MOD: R{rs2} is zero")
        if self.substrate_mode:
            sa, sb = self._signs[rs1], self._signs[rs2]
            # Need a temporary register for the quotient
            tmp_q = ShadowRegister(mode=self.registers[rd].mode)
            _, r_neg = SubstrateALU.divmod(
                self.registers[rs1], sa,
                self.registers[rs2], sb,
                tmp_q, self.registers[rd],
            )
            self._signs[rd] = r_neg
            if self.registers[rd].shadow_active:
                self.flags["S"] = 1
            r = self._read_reg(rd)
        else:
            a, b = self._read_reg(rs1), self._read_reg(rs2)
            r = abs(a) % abs(b)
            result = -r if a < 0 and r != 0 else r
            self._write_reg(rd, result)
            r = result
        self._update_flags(r)

    def _op_and(self, rd, rs1, rs2):
        if self.substrate_mode:
            SubstrateALU.bitwise_and(self.registers[rs1], self.registers[rs2], self.registers[rd])
            self._signs[rd] = False
            if self.registers[rd].shadow_active:
                self.flags["S"] = 1
            r = self._read_reg(rd)
        else:
            r = self.registers[rs1].read() & self.registers[rs2].read()
            self._write_reg(rd, r)
        self._update_flags(r)

    def _op_or(self, rd, rs1, rs2):
        if self.substrate_mode:
            SubstrateALU.bitwise_or(self.registers[rs1], self.registers[rs2], self.registers[rd])
            self._signs[rd] = False
            if self.registers[rd].shadow_active:
                self.flags["S"] = 1
            r = self._read_reg(rd)
        else:
            r = self.registers[rs1].read() | self.registers[rs2].read()
            self._write_reg(rd, r)
        self._update_flags(r)

    def _op_xor(self, rd, rs1, rs2):
        if self.substrate_mode:
            SubstrateALU.bitwise_xor(self.registers[rs1], self.registers[rs2], self.registers[rd])
            self._signs[rd] = False
            if self.registers[rd].shadow_active:
                self.flags["S"] = 1
            r = self._read_reg(rd)
        else:
            r = self.registers[rs1].read() ^ self.registers[rs2].read()
            self._write_reg(rd, r)
        self._update_flags(r)

    def _op_not(self, rd, rs):
        if self.substrate_mode:
            SubstrateALU.bitwise_not(self.registers[rs], self.registers[rd], self.word_bits)
            self._signs[rd] = False
            if self.registers[rd].shadow_active:
                self.flags["S"] = 1
            r = self._read_reg(rd)
        else:
            mask = (1 << self.word_bits) - 1
            r = (~self.registers[rs].read()) & mask
            self._write_reg(rd, r)
        self._update_flags(r)

    def _op_lsl(self, rd, rs, amt):
        if self.substrate_mode:
            SubstrateALU.shift_left(self.registers[rs], amt, self.registers[rd])
            self._signs[rd] = self._signs[rs]
            if self.registers[rd].shadow_active:
                self.flags["S"] = 1
            r = self._read_reg(rd)
        else:
            r = self.registers[rs].read() << amt
            self._write_reg(rd, r)
        self._update_flags(r)

    def _op_lsr(self, rd, rs, amt):
        if self.substrate_mode:
            SubstrateALU.shift_right(self.registers[rs], amt, self.registers[rd])
            self._signs[rd] = False   # LSR always positive
            if self.registers[rd].shadow_active:
                self.flags["S"] = 1
            r = self._read_reg(rd)
        else:
            r = self.registers[rs].read() >> amt
            self._write_reg(rd, r)
        self._update_flags(r)

    def _op_cmp(self, rs1, rs2):
        """CMP: set flags from Rs1 − Rs2 without storing the result."""
        if self.substrate_mode:
            cmp_val = SubstrateALU.compare(
                self.registers[rs1], self._signs[rs1],
                self.registers[rs2], self._signs[rs2],
            )
            a, b = self._read_reg(rs1), self._read_reg(rs2)
            self._sub_flags(a, b, a - b, borrow_out=(cmp_val < 0))
        else:
            a, b = self._read_reg(rs1), self._read_reg(rs2)
            self._sub_flags(a, b, a - b)

    def _op_addi(self, rd, rs, imm):
        a = self._read_reg(rs)
        r, carry_out = self._sau_add_imm(rd, rs, imm)
        self._add_flags(a, imm, r, carry_out=carry_out)

    def _op_subi(self, rd, rs, imm):
        a = self._read_reg(rs)
        r, borrow_out = self._sau_sub_imm(rd, rs, imm)
        self._sub_flags(a, imm, r, borrow_out=borrow_out)

    def _op_muli(self, rd, rs, imm):
        if self.substrate_mode:
            sa = self._signs[rs]
            si = imm < 0
            tmp = ShadowRegister(mode=self.registers[rd].mode)
            tmp.write(abs(imm))
            result_neg = SubstrateALU.mul(self.registers[rs], sa, tmp, si, self.registers[rd])
            self._signs[rd] = result_neg
            if self.registers[rd].shadow_active:
                self.flags["S"] = 1
            r = self._read_reg(rd)
        else:
            a = self._read_reg(rs)
            r = a * imm
            self._write_reg(rd, r)
        self._update_flags(r)

    def _op_andi(self, rd, rs, imm):
        if self.substrate_mode:
            tmp = ShadowRegister(mode=self.registers[rd].mode)
            tmp.write(abs(imm))
            SubstrateALU.bitwise_and(self.registers[rs], tmp, self.registers[rd])
            self._signs[rd] = False
            if self.registers[rd].shadow_active:
                self.flags["S"] = 1
            r = self._read_reg(rd)
        else:
            r = self.registers[rs].read() & imm
            self._write_reg(rd, r)
        self._update_flags(r)

    def _op_ori(self, rd, rs, imm):
        if self.substrate_mode:
            tmp = ShadowRegister(mode=self.registers[rd].mode)
            tmp.write(abs(imm))
            SubstrateALU.bitwise_or(self.registers[rs], tmp, self.registers[rd])
            self._signs[rd] = False
            if self.registers[rd].shadow_active:
                self.flags["S"] = 1
            r = self._read_reg(rd)
        else:
            r = self.registers[rs].read() | imm
            self._write_reg(rd, r)
        self._update_flags(r)

    def _op_cmpi(self, rs, imm):
        if self.substrate_mode:
            si = imm < 0
            tmp = ShadowRegister(mode=self.registers[rs].mode)
            tmp.write(abs(imm))
            a, b = self._read_reg(rs), imm
            cmp_val = SubstrateALU.compare(self.registers[rs], self._signs[rs], tmp, si)
            self._sub_flags(a, b, a - b, borrow_out=(cmp_val < 0))
        else:
            a = self._read_reg(rs)
            self._sub_flags(a, imm, a - imm)

    def _op_store(self, rs, addr):
        self._write_mem(addr, self._read_reg(rs))

    def _op_load_mem(self, rd, addr):
        v = self._read_mem(addr)
        self._write_reg(rd, v)
        self._update_flags(v)

    def _op_storei(self, rs, raddr):
        addr = self._read_reg(raddr)
        self._write_mem(addr, self._read_reg(rs))

    def _op_loadi(self, rd, raddr):
        addr = self._read_reg(raddr)
        v = self._read_mem(addr)
        self._write_reg(rd, v)
        self._update_flags(v)

    def _op_storex(self, rs, rbase, off):
        addr = self._read_reg(rbase) + off
        self._write_mem(addr, self._read_reg(rs))

    def _op_loadx(self, rd, rbase, off):
        addr = self._read_reg(rbase) + off
        v = self._read_mem(addr)
        self._write_reg(rd, v)
        self._update_flags(v)

    def _op_push(self, rs):
        sp = self._read_reg(self.SP_REGISTER)
        if sp < 0:
            raise OverflowError("Stack overflow on PUSH (SP < 0)")
        self._write_mem(sp, self._read_reg(rs))
        self._write_reg(self.SP_REGISTER, sp - 1)

    def _op_pop(self, rd):
        sp = self._read_reg(self.SP_REGISTER) + 1
        if sp >= self.memory_size:
            raise OverflowError("Stack underflow on POP (SP overran memory)")
        v = self._read_mem(sp)
        self._write_reg(rd, v)
        self._write_reg(self.SP_REGISTER, sp)
        self._update_flags(v)

    def _op_call(self, addr):
        self.call_stack.append(self.pc + 1)   # save return address
        self.pc = addr - 1

    def _op_ret(self):
        if not self.call_stack:
            raise RuntimeError("RET with empty call stack")
        self.pc = self.call_stack.pop() - 1

    def _op_syscall(self, num):
        # First device that handles it wins
        for dev in self.devices:
            try:
                dev.on_syscall(self, num)
                return
            except NotImplementedError:
                continue
        raise ValueError(f"Unhandled syscall: {num}")

    # ── PROGRAM RUNNER ─────────────────────────────────────────────────

    def run(
        self,
        program: List[Tuple],
        verbose: bool = False,
        max_cycles: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Execute `program` until HALT or max_cycles.
        Returns a result dict {cycles, halted, exit_code, output, ...}.
        """
        if max_cycles is None:
            max_cycles = self.max_cycles

        self.pc = 0
        self.halted = False
        self.cycles = 0
        t0 = time.perf_counter()

        while self.pc < len(program) and not self.halted and self.cycles < max_cycles:
            instr = program[self.pc]
            if verbose:
                spec = ISA.get(instr[0])
                mn = spec.mnemonic if spec else "?"
                print(f"  PC={self.pc:04d}  {mn:<8} {instr[1:]}  flags={self.flags}")
            self.execute(instr)
            self.pc += 1
            self.cycles += 1

        if self.cycles >= max_cycles and not self.halted:
            raise RuntimeError(
                f"CPU exceeded max_cycles={max_cycles} without HALT "
                f"(infinite loop?)"
            )

        elapsed = time.perf_counter() - t0
        total_carry_work = sum(
            r.carry_work for r in self.registers
            if hasattr(r, "carry_work")
        )
        return {
            "cycles": self.cycles,
            "halted": self.halted,
            "exit_code": self.exit_code,
            "output": self.console.output(),
            "flags": dict(self.flags),
            "registers": [self._read_reg(i) for i in range(self.num_registers)],
            "elapsed_s": elapsed,
            "ips": int(self.cycles / elapsed) if elapsed > 0 else 0,
            "trace_hash": self._trace_hash() if self.do_trace else None,
            "shadow_flag": self.flags["S"],
            "total_carry_work": total_carry_work,
        }

    # ── DIAGNOSTICS ────────────────────────────────────────────────────

    def format_state(self) -> str:
        lines = [f"== CPU state @ cycle {self.cycles}, PC={self.pc} =="]
        for i in range(self.num_registers):
            v = self._read_reg(i)
            tag = " (SP)" if i == self.SP_REGISTER else ""
            lines.append(f"  R{i}{tag}: {v}")
        f = self.flags
        shadow_note = "  [SHADOW REGIME — LAW_SHADOW_PROCESSOR_001]" if f["S"] else ""
        lines.append(
            f"  Flags: Z={f['Z']} N={f['N']} C={f['C']} V={f['V']} S={f['S']}"
            f"  Halted={self.halted}{shadow_note}"
        )
        return "\n".join(lines)

    def reset(self) -> None:
        """Hard reset of CPU state."""
        for r in self.registers: r.write(0)
        for m in self.memory: m.write(0)
        self._signs = [False] * self.num_registers
        self._mem_signs = [False] * self.memory_size
        self.flags = {"Z": 0, "C": 0, "V": 0, "N": 0, "S": 0}
        self.pc = 0
        self.halted = False
        self.exit_code = 0
        self.cycles = 0
        self.call_stack.clear()
        self.registers[self.SP_REGISTER].write(self.memory_size - 1)
        for d in self.devices: d.reset()
        self.trace.clear()

    def _trace_hash(self) -> str:
        """SHA-256 over the full trace — for reproducibility checks."""
        h = hashlib.sha256()
        for entry in self.trace:
            h.update(repr(entry).encode())
        return h.hexdigest()

    def substrate_fingerprint(self) -> Dict[str, Any]:
        """
        Aggregate substrate fingerprint over all register cells.

        Returns:
            nrci_mean: Mean NRCI across all register cells.
                NOTE — NRCI is a property of the *substrate geometry*,
                not of the stored values. For a CPU built entirely on
                PERFECT_V1 substrates (the default), nrci_mean is always
                0.7692 regardless of what has been computed. It would
                differ only if different substrate types were mixed across
                registers. Use magnitude_sha to detect computation state.

            magnitude_sha: SHA-256 (first 16 hex chars) of the magnitude
                pattern across all registers + first 32 memory cells.
                This IS computation-dependent — it changes as registers
                and memory are written, giving a deterministic geometric
                signature of the CPU's current numeric state.

            shadow_flag: Current value of the S (Shadow) flag.
                1 = at least one register has entered the Shadow Regime
                (LAW_SHADOW_PROCESSOR_001) at some point since last reset.

            shadow_registers: List of register indices currently in the
                Shadow Regime (their ShadowRegister.shadow_active is True).

            total_carry_work: Sum of carry_work across all ShadowRegisters.
                Implements LAW_CARRY_WORK_001 — the accumulated base-4
                carry events measure the geometric binding work performed
                by this CPU since last reset.
        """
        if not self.substrate_mode:
            return {
                "mode": "plain",
                "nrci_mean": None,
                "magnitude_sha": None,
                "shadow_flag": 0,
                "shadow_registers": [],
                "total_carry_work": 0,
            }
        nrcis: List[float] = []
        mag_signature: List[int] = []
        shadow_reg_indices: List[int] = []
        total_carry_work: int = 0
        for i, r in enumerate(self.registers):
            mag_signature.append(r.read())
            if r.cells:
                nrcis.append(r.cells[0].fingerprint()["nrci"])
            if hasattr(r, "shadow_active") and r.shadow_active:
                shadow_reg_indices.append(i)
            if hasattr(r, "carry_work"):
                total_carry_work += r.carry_work
        for m in self.memory[:32]:           # first 32 mem cells only (cheap)
            mag_signature.append(m.read())
        sha = hashlib.sha256(repr(mag_signature).encode()).hexdigest()[:16]
        return {
            "mode": "substrate",
            "nrci_mean": round(sum(nrcis) / len(nrcis), 4) if nrcis else None,
            "magnitude_sha": sha,
            "shadow_flag": self.flags["S"],
            "shadow_registers": shadow_reg_indices,
            "total_carry_work": total_carry_work,
        }


# ── PLAIN-INT REGISTER (used when substrate_mode=False) ──────────────────────

class _PlainReg:
    """
    Drop-in for NoiseRegisterV3 when speed matters and substrate isn't needed.

    CPU._write_reg() always calls write(abs(value)), so this register only ever
    receives non-negative magnitudes — matching the contract of NoiseRegisterV3.
    The assert below makes that invariant explicit; it will surface immediately
    if any future code path accidentally bypasses _write_reg.
    """
    def __init__(self):
        self._v = 0
        self.cells: list = []

    def write(self, v: int, *_, **__):
        v = int(v)
        assert v >= 0, (
            f"_PlainReg.write() received {v} — only non-negative magnitudes "
            "are valid. The caller must pass abs(value) and store the sign separately."
        )
        self._v = v

    def read(self) -> int:
        return self._v
