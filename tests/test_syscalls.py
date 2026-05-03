"""Unit tests for system calls / I/O (opcode 0x50)."""
from noisecore_vm import CPU, assemble


def test_print_int():
    cpu = CPU(substrate_mode=False)
    src = """
        LOAD    R0, #1234
        SYSCALL 1
        HALT
    """
    cpu.run(assemble(src).instructions)
    assert cpu.console.output() == "1234"


def test_print_negative_int():
    cpu = CPU(substrate_mode=False)
    src = """
        LOAD    R0, #-99
        SYSCALL 1
        HALT
    """
    cpu.run(assemble(src).instructions)
    assert cpu.console.output() == "-99"


def test_print_char():
    cpu = CPU(substrate_mode=False)
    src = """
        LOAD    R0, 'A'
        SYSCALL 2
        LOAD    R0, 'Z'
        SYSCALL 2
        HALT
    """
    cpu.run(assemble(src).instructions)
    assert cpu.console.output() == "AZ"


def test_print_str():
    cpu = CPU(substrate_mode=False)
    src = """
.data msg 'H' 'I' '!' 0
        LOAD    R0, msg
        SYSCALL 3
        HALT
    """
    prog = assemble(src)
    for addr, val in prog.memory_init().items():
        cpu._write_mem(addr, val)
    cpu.run(prog.instructions)
    assert cpu.console.output() == "HI!"


def test_print_newline():
    cpu = CPU(substrate_mode=False)
    src = """
        LOAD    R0, #5
        SYSCALL 1
        SYSCALL 6
        HALT
    """
    cpu.run(assemble(src).instructions)
    assert cpu.console.output() == "5\n"


def test_read_int():
    cpu = CPU(substrate_mode=False)
    cpu.console.input_queue.append(99)
    src = """
        SYSCALL 4
        SYSCALL 1
        HALT
    """
    cpu.run(assemble(src).instructions)
    assert cpu.console.output() == "99"


def test_exit_syscall_sets_halt():
    cpu = CPU(substrate_mode=False)
    src = """
        LOAD    R0, #7
        SYSCALL 5
        LOAD    R0, #999     ; should not execute
        HALT
    """
    info = cpu.run(assemble(src).instructions)
    assert cpu._read_reg(0) == 7
    assert cpu.exit_code == 7
    assert info["halted"] is True
