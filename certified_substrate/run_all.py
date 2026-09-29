"""run_all.py — fidelity proof + benchmarks + a demo certificate."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
env = {**os.environ,
       "NOISECORE_PATH": os.environ.get(
           "NOISECORE_PATH",
           os.path.join(HERE, "..", "glm-noisecore-lab", "noisecore"))}


def run(script):
    print(f"\n{'=' * 66}\n  {script}\n{'=' * 66}")
    return subprocess.run([sys.executable, os.path.join(HERE, script)],
                          cwd=HERE, env=env).returncode


def demo():
    print(f"\n{'=' * 66}\n  demo certificate\n{'=' * 66}")
    sys.path.insert(0, HERE)
    from coprocessor import CertifiedSubstrate
    cs = CertifiedSubstrate()
    for res in (cs.letter_word("codeword"),
                cs.golay_encode(42),
                cs.leech_decode([3, -1, 0, 2] * 6)):
        print(f"\nvalue: {res.value if not isinstance(res.value, list) else res.value[:6]}"
              f"{' ...' if isinstance(res.value, list) else ''}")
        for k, v in res.certificate().items():
            if k != "value":
                print(f"  {k}: {v}")


if __name__ == "__main__":
    rc = run("fidelity_test.py")
    rc |= run("bench.py")
    demo()
    sys.exit(rc)
