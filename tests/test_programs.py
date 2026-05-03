"""End-to-end tests: real, non-trivial programs run on the VM."""
import os
from noisecore_vm import CPU, assemble, run_program

EX_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples"
)

def _run_example(name: str) -> str:
    with open(os.path.join(EX_DIR, name)) as f:
        src = f.read()
    cpu, info = run_program(src, substrate_mode=False, max_cycles=200_000)
    return cpu.console.output()


def test_hello():
    assert _run_example("01_hello.nca") == "HELLO\n"


def test_factorial_iterative():
    assert _run_example("02_factorial_iter.nca") == "720\n"


def test_factorial_recursive():
    assert _run_example("03_factorial_recursive.nca") == "720\n"


def test_bubble_sort():
    assert _run_example("04_bubble_sort.nca") == "1 2 3 4 5 6 7 8 \n"


def test_prime_sieve():
    assert _run_example("05_prime_sieve.nca") == "2 3 5 7 11 13 17 19 23 29 \n"


def test_fibonacci_iter():
    assert _run_example("06_fibonacci.nca") == "0 1 1 2 3 5 8 13 21 34 \n"


def test_gcd():
    assert _run_example("07_gcd.nca") == "18\n"


def test_string_reverse():
    assert _run_example("08_string_reverse.nca") == "DLROW OLLEH\n"


def test_sum_of_squares():
    """Sum of squares 1²+2²+...+10² = 385."""
    src = """
        LOAD R0, #0           ; acc
        LOAD R1, #1           ; i
    loop:
        CMPI R1, 10
        JG   done
        MUL  R2, R1, R1
        ADD  R0, R0, R2
        ADDI R1, R1, #1
        JMP  loop
    done:
        SYSCALL 1
        HALT
    """
    cpu, _ = run_program(src, substrate_mode=False)
    assert cpu.console.output() == "385"


def test_signed_integer_arithmetic_program():
    """End-to-end signed arithmetic test."""
    src = """
        LOAD R0, #-100
        LOAD R1, #50
        ADD  R2, R0, R1       ; -50
        LOAD R3, #-7
        MUL  R4, R2, R3       ; -50 * -7 = 350
        MOV  R0, R4
        SYSCALL 1
        HALT
    """
    cpu, _ = run_program(src, substrate_mode=False)
    assert cpu.console.output() == "350"
