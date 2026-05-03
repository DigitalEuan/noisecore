"""Run every example .nca and verify expected output."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from noisecore_vm import CPU, assemble, run_program

EXAMPLES = [
    ("01_hello.nca",              "HELLO\n"),
    ("02_factorial_iter.nca",     "720\n"),
    ("03_factorial_recursive.nca","720\n"),
    ("04_bubble_sort.nca",        "1 2 3 4 5 6 7 8 \n"),
    ("05_prime_sieve.nca",        "2 3 5 7 11 13 17 19 23 29 \n"),
    ("06_fibonacci.nca",          "0 1 1 2 3 5 8 13 21 34 \n"),
    ("07_gcd.nca",                "18\n"),
    ("08_string_reverse.nca",     "DLROW OLLEH\n"),
]

EX_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")

passed = failed = 0
results = []
for name, expected in EXAMPLES:
    path = os.path.join(EX_DIR, name)
    with open(path) as f:
        src = f.read()
    try:
        cpu, info = run_program(src, substrate_mode=False, max_cycles=100_000)
        out = cpu.console.output()
        ok = (out == expected)
        if ok:
            passed += 1
            results.append((name, "PASS", info["cycles"], out))
            print(f"  PASS  {name:32s}  cycles={info['cycles']:5d}  out={out!r}")
        else:
            failed += 1
            results.append((name, "FAIL", info["cycles"], out))
            print(f"  FAIL  {name:32s}  expected={expected!r}  got={out!r}")
    except Exception as e:
        failed += 1
        results.append((name, "ERROR", 0, str(e)))
        print(f"  ERROR {name:32s}  {type(e).__name__}: {e}")

print(f"\n  Passed: {passed}/{passed+failed}")
sys.exit(0 if failed == 0 else 1)
