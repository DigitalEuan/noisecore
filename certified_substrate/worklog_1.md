# 2026-09-29

## GLM × NoiseCore experiment lab (user's request)

User asked (webchat) whether their **GLM** (Geometric Language Machine,
github.com/DigitalEuan/GLM) can use their **noisecore** VM
(github.com/DigitalEuan/noisecore) as its "native" computer — with real
scripts/measurements, not hand-waving.

Built `glm-noisecore-lab/` with 8 experiment scripts + `REPORT.md`.
Both repos cloned inside. Everything ran; key results:

- **Exp01**: the two Golay [24,12,8] substrates are *identical* — 4096/4096
  codewords (identity bit order), 759/759 octads, systematic encodes agree
  4096/4096.
- **Exp02**: GLM kernels (letter_word, popcount, jaccard, leech2.inner incl.
  signed coords) as `.nca` programs: **0 mismatches** vs GLM Python.
- **Exp03**: Leech lattices coincide coordinate-for-coordinate (30/30 cost-0);
  DECODE opcode == Python decoder; decoder outputs pass GLM in_leech 40/40.
  Seam found: `core.syndrome` (used by SYN/ISGOLAY opcodes) uses bit-reversed
  masks vs engine/GLM (proven 4096/4096 under reversal); syndrome VALUES also
  private convention. Leech units contract: target in 1/256 units, point in
  whole units (= GLM integer model).
- **Exp04/04b**: perf — substrate CPU cold start 1.4 s (5 ms/cell calibration
  in NoiseCellV3), 21 s for 4096 cells; steady substrate tax 57–63× vs fast
  (README claims 5–10×); ~10³–10⁴× slower than Python GLM per kernel.
- **Exp05**: `word_bits` not enforced on values (cosmetic); default 256-cell
  memory < GLM's 4096-word tables (configurable); rationals only via
  delta-sigma scaled ints (DSONES exact floor, DSAVG first-n-bit avg ×1e⁶).
- **Exp06**: certification advantage — reproducible input-sensitive SHA-256
  trace hashes + substrate_fingerprint (nrci_mean, magnitude_sha).

**Verdict given**: yes at substrate level (same code, same lattice, kernels
bit-exact) → adopt as *certified substrate coprocessor* (Golay words, Leech
decode, certified results); not yet as the whole GLM's CPU (speed, cold
start, memory, Fraction gap, bit-order seam). Fix list in REPORT.md.

Notes: noisecore test drift (test_shadow/test_substrate_alu import errors —
ShadowRegister/SubstrateALU missing; test_cpu_state expects 'S' flag;
test_delta_sigma: 111 tests, does not finish in 30 min, ≥1 failure).
Workspace had no pytest — installed via pip3 (pytest 9.1.1).

## Certified Substrate Coprocessor (follow-up request, same day)

User asked to construct + test a "certified substrate coprocessor" capturing
noisecore's methods/theory for the GLM to build on; expand the too-small
substrate; improve speed without losing fidelity (accuracy > speed);
suggested GLM's "Generate don't Store" doctrine.

Delivered `certified_substrate/` (workspace root): THEORY.md (full capture
of noisecore layers + conventions/seams), coprocessor.py (CertifiedSubstrate
API: letter_word/popcount/jaccard_parts/inner/golay_encode/is_golay/syndrome/
leech_decode/verify_stream, each with cycles+trace_hash+substrate_fingerprint
certificate; canonical GLM bit order + Leech units absorbed),
accelerate.py (tier1 "exact": shared cell-calibration cache + lazy
displacement-curve lookup (shipped code evaluates fallback eagerly!) + O(1)
register read; tier2 "turbo": + elide per-write register traces),
fidelity_test.py (subprocess A/B: 82 records/tier, tier1 & tier2 IDENTICAL to
raw in values/cycles/trace_hash/fingerprint; GLM parity OK incl. all 4096
encodes), bench.py, run_all.py, README.md.

Measured: CPU construction 548x (256 cells 1.3s→2ms), 393x (4096 cells
21.6s→55ms), 16384 cells 0.31s; kernels 5.6–18.9x; 4096-codeword stream
verified on VM in 0.3s with ZERO table cells (generate-don't-store).
leech_decode ~228ms/call unchanged (decoder coset search, not registers —
next optimization target). Gotchas absorbed: SYN/ISGOLAY bit-reversal seam,
Leech units x256 targets / whole-unit points, cpu.trace accumulates on CPU
reuse (must clear for stable trace_hash), syscalls dispatch via
cpu.devices[0] not cpu.console.
