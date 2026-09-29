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

from ..core.substrate import NoiseRegisterV3
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
    registers      : list[NoiseRegisterV3]   — R0..R(N-1)
    memory         : list[NoiseRegisterV3]   — main memory cells
    flags          : dict[str,int]           — {'Z','N','C','V'}
    pc             : int                     — program counter
    halted         : bool
    cycles         : int                     — instructions executed
    word_bits      : int                     — 8, 16, 32, 64
    sp_register    : int                     — index of register used as SP (default 7)
    devices        : list[Device]
    trace          : list[TraceEntry]        — populated when trace=True

    Conventions
    -----------
    • R7 is the stack pointer (SP) by convention — initialised to MEMORY_SIZE-1
      and grows downward (PUSH decrements, POP increments).
    • The dedicated `call_stack` list holds return addresses for CALL/RET
      (kept separate from data stack to keep the demo clear; can be migrated to
      memory-stack form later without ISA change).
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
            self.registers: List[NoiseRegisterV3] = [
                NoiseRegisterV3(mode=mode) for _ in range(num_registers)
            ]
        else:
            self.registers = [_PlainReg() for _ in range(num_registers)]
        self._signs: List[bool] = [False] * num_registers

        # Memory
        if substrate_mode:
            self.memory: List[NoiseRegisterV3] = [
                NoiseRegisterV3(mode=mode) for _ in range(memory_size)
            ]
        else:
            self.memory = [_PlainReg() for _ in range(memory_size)]
        self._mem_signs: List[bool] = [False] * memory_size

        # CPU state
        self.flags: Dict[str, int] = {"Z": 0, "C": 0, "V": 0, "N": 0}
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

        # Zero-storage v5: cost ledger + moving delta-sigma state
        from ..ledger import Ledger
        self.ledger = Ledger()
        self._mds = None   # MovingDeltaSigma, created by MDSRT

    # ── REGISTER / MEMORY ACCESSORS ─────────────────────────────────────

    def _write_reg(self, idx: int, value: int) -> None:
        self._signs[idx] = value < 0
        self.registers[idx].write(abs(value))

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

    def _add_flags(self, a: int, b: int, result: int) -> None:
        carry = 1 if (abs(a) + abs(b)) > self._word_max else 0
        overflow = (
            (a >= 0 and b >= 0 and result < 0) or
            (a < 0 and b < 0 and result >= 0) or
            result > self._word_signed_max or result < self._word_signed_min
        )
        self._update_flags(result, carry=carry, overflow=overflow)

    def _sub_flags(self, a: int, b: int, result: int) -> None:
        borrow = 1 if a < b else 0
        overflow = (
            (a >= 0 and b < 0 and result < 0) or
            (a < 0 and b >= 0 and result >= 0) or
            result > self._word_signed_max or result < self._word_signed_min
        )
        self._update_flags(result, carry=borrow, overflow=overflow)

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

        # ── delta-sigma & mantissa wall (exact arithmetic) ──
        elif opcode in (0x60, 0x61, 0x62, 0x63, 0x64, 0x65):
            from .delta_sigma_ops import DELTA_SIGMA_OPS
            DELTA_SIGMA_OPS[opcode](self, *args)

        # ── zero-storage substrate (v5) ──
        elif opcode in (0x66, 0x67, 0x68, 0x69, 0x6A, 0x6B, 0x6C, 0x6D):
            from .zero_storage_ops import ZERO_STORAGE_OPS
            ZERO_STORAGE_OPS[opcode](self, *args)

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
        r = a + b
        self._write_reg(rd, r)
        self._add_flags(a, b, r)

    def _op_sub(self, rd, rs1, rs2):
        a, b = self._read_reg(rs1), self._read_reg(rs2)
        r = a - b
        self._write_reg(rd, r)
        self._sub_flags(a, b, r)

    def _op_mul(self, rd, rs1, rs2):
        a, b = self._read_reg(rs1), self._read_reg(rs2)
        r = a * b
        self._write_reg(rd, r)
        self._update_flags(r)

    def _op_div(self, rd, rs1, rs2):
        a, b = self._read_reg(rs1), self._read_reg(rs2)
        if b == 0:
            raise ZeroDivisionError(f"DIV: R{rs2} is zero")
        sign = (a < 0) ^ (b < 0)
        q = abs(a) // abs(b)
        r = -q if sign and q != 0 else q
        self._write_reg(rd, r)
        self._update_flags(r)

    def _op_mod(self, rd, rs1, rs2):
        a, b = self._read_reg(rs1), self._read_reg(rs2)
        if b == 0:
            raise ZeroDivisionError(f"MOD: R{rs2} is zero")
        r = abs(a) % abs(b)
        result = -r if a < 0 and r != 0 else r
        self._write_reg(rd, result)
        self._update_flags(result)

    def _op_and(self, rd, rs1, rs2):
        a = self.registers[rs1].read()
        b = self.registers[rs2].read()
        r = a & b
        self._write_reg(rd, r)
        self._update_flags(r)

    def _op_or(self, rd, rs1, rs2):
        a = self.registers[rs1].read()
        b = self.registers[rs2].read()
        r = a | b
        self._write_reg(rd, r)
        self._update_flags(r)

    def _op_xor(self, rd, rs1, rs2):
        a = self.registers[rs1].read()
        b = self.registers[rs2].read()
        r = a ^ b
        self._write_reg(rd, r)
        self._update_flags(r)

    def _op_not(self, rd, rs):
        a = self.registers[rs].read()
        mask = (1 << self.word_bits) - 1
        r = (~a) & mask
        self._write_reg(rd, r)
        self._update_flags(r)

    def _op_lsl(self, rd, rs, amt):
        v = self.registers[rs].read() << amt
        self._write_reg(rd, v)
        self._update_flags(v)

    def _op_lsr(self, rd, rs, amt):
        v = self.registers[rs].read() >> amt
        self._write_reg(rd, v)
        self._update_flags(v)

    def _op_cmp(self, rs1, rs2):
        """CMP: set flags from Rs1 - Rs2 without storing the result."""
        a, b = self._read_reg(rs1), self._read_reg(rs2)
        self._sub_flags(a, b, a - b)

    def _op_addi(self, rd, rs, imm):
        a = self._read_reg(rs)
        r = a + imm
        self._write_reg(rd, r)
        self._add_flags(a, imm, r)

    def _op_subi(self, rd, rs, imm):
        a = self._read_reg(rs)
        r = a - imm
        self._write_reg(rd, r)
        self._sub_flags(a, imm, r)

    def _op_muli(self, rd, rs, imm):
        a = self._read_reg(rs)
        r = a * imm
        self._write_reg(rd, r)
        self._update_flags(r)

    def _op_andi(self, rd, rs, imm):
        a = self.registers[rs].read()
        r = a & imm
        self._write_reg(rd, r)
        self._update_flags(r)

    def _op_ori(self, rd, rs, imm):
        a = self.registers[rs].read()
        r = a | imm
        self._write_reg(rd, r)
        self._update_flags(r)

    def _op_cmpi(self, rs, imm):
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
        }

    # ── DIAGNOSTICS ────────────────────────────────────────────────────

    def format_state(self) -> str:
        lines = [f"== CPU state @ cycle {self.cycles}, PC={self.pc} =="]
        for i in range(self.num_registers):
            v = self._read_reg(i)
            tag = " (SP)" if i == self.SP_REGISTER else ""
            lines.append(f"  R{i}{tag}: {v}")
        f = self.flags
        lines.append(f"  Flags: Z={f['Z']} N={f['N']} C={f['C']} V={f['V']}  Halted={self.halted}")
        return "\n".join(lines)

    def reset(self) -> None:
        """Hard reset of CPU state."""
        for r in self.registers: r.write(0)
        for m in self.memory: m.write(0)
        self._signs = [False] * self.num_registers
        self._mem_signs = [False] * self.memory_size
        self.flags = {"Z": 0, "C": 0, "V": 0, "N": 0}
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
        Aggregate substrate fingerprint over all cells with non-zero magnitude.
        Returns mean NRCI and a SHA-256 of the magnitude pattern.
        """
        if not self.substrate_mode:
            return {"mode": "plain", "nrci_mean": None, "magnitude_sha": None}
        nrcis: List[float] = []
        mag_signature: List[int] = []
        for r in self.registers:
            mag_signature.append(r.read())
            if r.cells:
                nrcis.append(r.cells[0].fingerprint()["nrci"])
        for m in self.memory[:32]:           # first 32 mem cells only (cheap)
            mag_signature.append(m.read())
        sha = hashlib.sha256(repr(mag_signature).encode()).hexdigest()[:16]
        return {
            "mode": "substrate",
            "nrci_mean": round(sum(nrcis) / len(nrcis), 4) if nrcis else None,
            "magnitude_sha": sha,
        }


# ── PLAIN-INT REGISTER (used when substrate_mode=False) ──────────────────────

class _PlainReg:
    """Drop-in for NoiseRegisterV3 when speed matters and substrate isn't needed."""
    def __init__(self):
        self._v = 0
        self.cells: list = []
    def write(self, v: int, *_, **__): self._v = max(0, int(v))
    def read(self) -> int: return self._v
