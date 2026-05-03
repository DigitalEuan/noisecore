"""VM subpackage — CPU, assembler, disassembler, ISA."""
from .cpu import CPU, ConsoleDevice, Device, TraceEntry
from .assembler import Assembler, AssembledProgram, AssemblerError, assemble
from .disassembler import disassemble
from .isa import ISA, MNEMONIC_TO_OPCODE, SYSCALL_NAMES, OpSpec, describe

__all__ = [
    "CPU", "ConsoleDevice", "Device", "TraceEntry",
    "Assembler", "AssembledProgram", "AssemblerError", "assemble",
    "disassemble",
    "ISA", "MNEMONIC_TO_OPCODE", "SYSCALL_NAMES", "OpSpec", "describe",
]
