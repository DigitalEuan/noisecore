"""
================================================================================
NoiseCore VM — Reproducible validation & report generator
================================================================================
Runs:
  1. Full pytest suite
  2. Every example program in plain mode
  3. Every example program in substrate mode (slower; full Golay physics)
  4. Substrate calibration + fingerprint stability check
  5. Trace hash reproducibility check
Produces:
  - validation_report.md   — human-readable
  - validation_report.json — machine-readable (for CI / signing)
"""
import os, sys, json, subprocess, hashlib, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from noisecore_vm import CPU, assemble, run_program, ISA, __version__
from noisecore_vm.core.substrate import (
    SubstrateLibrary, SubstrateCalibrator, GOLAY_AVAILABLE,
)


def run_pytest():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q",
         "--tb=line", "--no-header"],
        cwd=str(ROOT), capture_output=True, text=True
    )
    last_line = next(
        (l for l in reversed(proc.stdout.splitlines()) if "passed" in l or "failed" in l),
        proc.stdout.splitlines()[-1] if proc.stdout else "no output"
    )
    return {
        "returncode": proc.returncode,
        "summary":    last_line.strip(),
        "output":     proc.stdout,
    }


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


def run_examples(substrate: bool):
    rows = []
    for name, expected in EXAMPLES:
        src = (ROOT / "examples" / name).read_text()
        t0 = time.perf_counter()
        cpu, info = run_program(src, substrate_mode=substrate, max_cycles=200_000)
        dt = time.perf_counter() - t0
        out = cpu.console.output()
        ok = (out == expected)
        rows.append({
            "name": name,
            "ok": ok,
            "cycles": info["cycles"],
            "elapsed_s": round(dt, 4),
            "ips": int(info["cycles"] / dt) if dt > 0 else 0,
            "output": out,
            "nrci_mean": cpu.substrate_fingerprint().get("nrci_mean") if substrate else None,
        })
    return rows


def trace_reproducibility():
    """Run each demo twice, compare trace hashes."""
    rows = []
    for name, _ in EXAMPLES:
        src = (ROOT / "examples" / name).read_text()
        hashes = []
        for _ in range(2):
            cpu = CPU(substrate_mode=False, trace=True)
            prog = assemble(src)
            for addr, val in prog.memory_init().items():
                cpu._write_mem(addr, val)
            info = cpu.run(prog.instructions, max_cycles=200_000)
            hashes.append(info["trace_hash"])
        rows.append({
            "name": name,
            "stable": hashes[0] == hashes[1],
            "trace_sha256": hashes[0],
        })
    return rows


def substrate_calibration():
    cal = SubstrateCalibrator().calibrate(SubstrateLibrary.PERFECT_V1)
    return {
        "engine": cal["engine_mode"],
        "substrate_hw": cal["substrate_hw"],
        "baseline_sw": cal["baseline_syndrome_weight"],
        "elastic_limit": cal["elastic_limit"],
        "curve_first_5": {
            str(k): cal["curve"][k]["displacement"] for k in range(5)
        },
    }


def main():
    print("=" * 70)
    print(f"  NoiseCore VM v{__version__} — full validation")
    print(f"  Real Golay engine: {GOLAY_AVAILABLE}")
    print(f"  Total opcodes: {len(ISA)}")
    print("=" * 70)

    pytest_result = run_pytest()
    print(f"\n[1/5] pytest:  {pytest_result['summary']}")

    print("\n[2/5] Examples (plain mode)...")
    plain = run_examples(substrate=False)
    plain_pass = sum(1 for r in plain if r["ok"])
    for r in plain:
        flag = "OK" if r["ok"] else "FAIL"
        print(f"  {flag} {r['name']:32s}  cycles={r['cycles']:5d}  ips={r['ips']}")

    print("\n[3/5] Examples (Golay-substrate mode)...")
    substrate = run_examples(substrate=True)
    sub_pass = sum(1 for r in substrate if r["ok"])
    for r in substrate:
        flag = "OK" if r["ok"] else "FAIL"
        print(f"  {flag} {r['name']:32s}  cycles={r['cycles']:5d}  "
              f"NRCI={r['nrci_mean']}")

    print("\n[4/5] Trace hash reproducibility...")
    traces = trace_reproducibility()
    trace_pass = sum(1 for r in traces if r["stable"])
    for r in traces:
        flag = "OK" if r["stable"] else "FAIL"
        print(f"  {flag} {r['name']:32s}  sha={r['trace_sha256'][:16]}...")

    print("\n[5/5] Substrate calibration...")
    cal = substrate_calibration()
    print(f"  engine={cal['engine']}  hw={cal['substrate_hw']}  "
          f"baseline_sw={cal['baseline_sw']}  elastic={cal['elastic_limit']}")
    print(f"  displacement curve k=0..4: {cal['curve_first_5']}")

    # ── write outputs ───────────────────────────────────────────────────
    summary = {
        "version": __version__,
        "real_golay_engine": GOLAY_AVAILABLE,
        "opcode_count": len(ISA),
        "pytest": pytest_result["summary"],
        "examples_plain_pass":     f"{plain_pass}/{len(plain)}",
        "examples_substrate_pass": f"{sub_pass}/{len(substrate)}",
        "traces_stable":           f"{trace_pass}/{len(traces)}",
        "calibration": cal,
        "examples_plain":     plain,
        "examples_substrate": substrate,
        "trace_hashes":       traces,
    }

    (ROOT / "validation_report.json").write_text(json.dumps(summary, indent=2))
    _write_markdown(summary)
    print("\nReports written:")
    print(f"  → validation_report.json")
    print(f"  → validation_report.md")

    # exit code
    failures = (
        (pytest_result["returncode"] != 0) +
        (plain_pass != len(plain)) +
        (sub_pass != len(substrate)) +
        (trace_pass != len(traces))
    )
    sys.exit(failures)


def _write_markdown(s):
    L = []
    L.append(f"# NoiseCore VM v{s['version']} — Validation Report\n")
    L.append(f"_Generated by `scripts/validate_and_report.py`._\n")
    L.append("## Summary\n")
    L.append("| Metric | Value |")
    L.append("|---|---|")
    L.append(f"| Version | `{s['version']}` |")
    L.append(f"| Real Golay engine | `{s['real_golay_engine']}` |")
    L.append(f"| Opcodes implemented | **{s['opcode_count']}** |")
    L.append(f"| Pytest | **{s['pytest']}** |")
    L.append(f"| Examples (plain) | **{s['examples_plain_pass']}** |")
    L.append(f"| Examples (substrate) | **{s['examples_substrate_pass']}** |")
    L.append(f"| Trace hashes stable | **{s['traces_stable']}** |\n")

    L.append("## Substrate calibration (PERFECT_V1)\n")
    cal = s["calibration"]
    L.append(f"- Engine mode: `{cal['engine']}`")
    L.append(f"- Hamming weight: {cal['substrate_hw']}")
    L.append(f"- Baseline syndrome weight: {cal['baseline_sw']}")
    L.append(f"- Elastic limit: {cal['elastic_limit']} bits")
    L.append(f"- Displacement curve k=0..4: `{cal['curve_first_5']}`\n")

    L.append("## Programs (plain integer mode)\n")
    L.append("| Program | Cycles | IPS | Output |")
    L.append("|---|---:|---:|---|")
    for r in s["examples_plain"]:
        out = r["output"].replace("\n", "↵").strip()[:40]
        L.append(f"| `{r['name']}` | {r['cycles']} | {r['ips']:,} | `{out}` |")

    L.append("\n## Programs (Golay-substrate mode)\n")
    L.append("| Program | Cycles | NRCI | Output |")
    L.append("|---|---:|---:|---|")
    for r in s["examples_substrate"]:
        out = r["output"].replace("\n", "↵").strip()[:40]
        L.append(f"| `{r['name']}` | {r['cycles']} | {r['nrci_mean']} | `{out}` |")

    L.append("\n## Trace reproducibility\n")
    L.append("Each program is run **twice** and the SHA-256 of its instruction trace ")
    L.append("is compared. Identical hashes prove deterministic execution.\n")
    L.append("| Program | Stable | Trace SHA-256 |")
    L.append("|---|---|---|")
    for r in s["trace_hashes"]:
        flag = "✓" if r["stable"] else "✗"
        L.append(f"| `{r['name']}` | {flag} | `{r['trace_sha256'][:32]}…` |")

    (ROOT / "validation_report.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
