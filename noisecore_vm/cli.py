"""
================================================================================
NoiseCore VM — Command-line Interface
================================================================================

Subcommands
-----------
    noisecore run FILE.nca          Assemble & execute
    noisecore asm FILE.nca [-o OUT] Show / save instruction listing
    noisecore disasm FILE.nca       Round-trip disassembly
    noisecore repl                  Interactive REPL
    noisecore info                  Print ISA reference

Run with --help on any subcommand for details.
"""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

from . import CPU, assemble, disassemble, ISA, SYSCALL_NAMES, __version__


def _load_program(path: str):
    src = Path(path).read_text()
    return src, assemble(src)


def cmd_run(args):
    src, prog = _load_program(args.file)
    cpu = CPU(
        substrate_mode=args.substrate,
        word_bits=args.word_bits,
        memory_size=args.memory,
        trace=args.trace,
        max_cycles=args.max_cycles,
    )
    # Apply data initialisation
    for addr, val in prog.memory_init().items():
        cpu._write_mem(addr, val)
    info = cpu.run(prog.instructions, verbose=args.verbose)
    sys.stdout.write(cpu.console.output())
    if args.stats:
        sys.stderr.write(
            f"\n[stats] cycles={info['cycles']}  "
            f"halted={info['halted']}  exit={info['exit_code']}  "
            f"elapsed={info['elapsed_s']:.4f}s  ips={info['ips']}\n"
        )
        if args.substrate:
            fp = cpu.substrate_fingerprint()
            sys.stderr.write(f"[stats] substrate NRCI mean = {fp['nrci_mean']}\n")
            sys.stderr.write(f"[stats] magnitude SHA-16   = {fp['magnitude_sha']}\n")
    return 0 if info["halted"] else 1


def cmd_asm(args):
    src, prog = _load_program(args.file)
    listing = disassemble(prog.instructions, labels=prog.labels)
    if args.output:
        Path(args.output).write_text(listing + "\n")
    else:
        print(listing)
    return 0


def cmd_disasm(args):
    """Round-trip: assemble → disassemble → print without labels resolved."""
    src, prog = _load_program(args.file)
    print(disassemble(prog.instructions, labels=prog.labels))
    return 0


def cmd_info(args):
    print(f"NoiseCore VM v{__version__}")
    print("─" * 60)
    print(f"{'OPCODE':<8} {'MNEMONIC':<10} {'OPERANDS':<20}")
    print("─" * 60)
    for op in sorted(ISA.keys()):
        spec = ISA[op]
        operands = ", ".join(spec.operands) or "(none)"
        print(f"  0x{op:02X}    {spec.mnemonic:<10} {operands}")
    print("\nSYSCALLS:")
    for n, name in sorted(SYSCALL_NAMES.items()):
        print(f"  {n}: {name}")
    return 0


def cmd_repl(args):
    """Tiny interactive REPL. Each line is one assembly instruction."""
    cpu = CPU(substrate_mode=args.substrate)
    print(f"NoiseCore VM v{__version__} REPL — type 'help' for commands, 'quit' to exit")
    while True:
        try:
            line = input("nc> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line: continue
        if line in ("quit", "exit", ":q"): break
        if line == "help":
            print("  Commands: regs, flags, reset, quit")
            print("  Or any single assembly line, e.g. 'LOAD R0, #5'")
            continue
        if line == "regs":
            print(cpu.format_state()); continue
        if line == "flags":
            print(cpu.flags); continue
        if line == "reset":
            cpu.reset(); print("(reset)"); continue
        try:
            prog = assemble(line)
            for instr in prog.instructions:
                opcode = instr[0]
                if opcode == 0x0F:          # HALT — skip in REPL context
                    continue
                if 0x10 <= opcode <= 0x1B:  # branch opcodes modify pc
                    print("  warning: branch instructions (JMP, JZ, etc.) have no "
                          "effect in the REPL — run a full program file instead.")
                    continue
                cpu.execute(instr)
                cpu.pc = 0  # reset pc after each instruction so branches don't linger
            print(cpu.format_state())
        except Exception as e:
            print(f"  error: {e}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="noisecore", description="NoiseCore Virtual Machine"
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Assemble & run a .nca file")
    p_run.add_argument("file")
    p_run.add_argument("--substrate", action="store_true",
                       help="Use Golay-mediated registers (slower, full physics)")
    p_run.add_argument("--word-bits", type=int, default=16, choices=[8,16,32,64])
    p_run.add_argument("--memory", type=int, default=256)
    p_run.add_argument("--max-cycles", type=int, default=1_000_000)
    p_run.add_argument("--trace", action="store_true")
    p_run.add_argument("--verbose", "-v", action="store_true")
    p_run.add_argument("--stats", action="store_true",
                       help="Print runtime statistics to stderr")
    p_run.set_defaults(func=cmd_run)

    p_asm = sub.add_parser("asm", help="Assemble & show instruction listing")
    p_asm.add_argument("file")
    p_asm.add_argument("-o", "--output")
    p_asm.set_defaults(func=cmd_asm)

    p_dis = sub.add_parser("disasm", help="Disassemble (round-trip)")
    p_dis.add_argument("file")
    p_dis.set_defaults(func=cmd_disasm)

    p_info = sub.add_parser("info", help="Print ISA reference")
    p_info.set_defaults(func=cmd_info)

    p_repl = sub.add_parser("repl", help="Interactive REPL")
    p_repl.add_argument("--substrate", action="store_true")
    p_repl.set_defaults(func=cmd_repl)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
