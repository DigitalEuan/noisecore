"""
NoiseCore VM — A Substrate-Mediated Virtual Computation Environment
====================================================================

Public API
----------
    from noisecore_vm import CPU, assemble, disassemble, run_program

    cpu = CPU()
    prog = assemble('''
        LOAD R0, #5
        LOAD R1, #7
        ADD  R2, R0, R1
        MOV  R0, R2
        SYSCALL 1     ; PRINT_INT
        SYSCALL 6     ; PRINT_NL
        HALT
    ''')
    cpu.run(prog.instructions)
    print(cpu.console.output())   # → "12\n"
"""

from .vm.cpu import CPU, ConsoleDevice, Device, TraceEntry
from .vm.assembler import Assembler, AssembledProgram, AssemblerError, assemble
from .vm.disassembler import disassemble
from .core.zs import verify_cell_zero_storage, golay_weight_census, zero_storage_audit
from .cesaro import delta_law, step as cesaro_step, cesaro, cesaro_error, bound_holds as cesaro_bound_holds
from .deep_hole import l1 as profile_l1, DeepHoleClassifier
from .ledger import Ledger, LEDGER_ITEMS
from .moving_ds import MovingDeltaSigma
from .nrci import nrci, nrci_enclosure
from .decoder import decode as leech_decode
from .vm.isa import ISA, MNEMONIC_TO_OPCODE, SYSCALL_NAMES, OpSpec, describe

__version__ = "1.4.0"

__all__ = [
    "CPU", "ConsoleDevice", "Device", "TraceEntry",
    "Assembler", "AssembledProgram", "AssemblerError", "assemble",
    "disassemble",
    "ISA", "MNEMONIC_TO_OPCODE", "SYSCALL_NAMES", "OpSpec", "describe",
    "run_program",
    "__version__",
]


def run_program(source: str, **cpu_kwargs):
    """Convenience: assemble + run a program in one call."""
    cpu = CPU(**cpu_kwargs)
    prog = assemble(source)
    # Apply .data initialisation
    for addr, value in prog.memory_init().items():
        cpu._write_mem(addr, value)
    result = cpu.run(prog.instructions)
    return cpu, result
