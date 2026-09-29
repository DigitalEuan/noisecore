# THEORY.md — the NoiseCore substrate, captured for builders

*What the NoiseCore VM (github.com/DigitalEuan/noisecore) is, how it works, why it works, and exactly where
the GLM (github.com/DigitalEuan/GLM) (or anything else) plugs in.*

---

## 1. The idea in one paragraph

NoiseCore VM is a register machine whose registers and memory are not
abstract integers but **base-12 positional stacks of 24-bit Golay
manifolds** ("cells"). Each cell stores its digit as a *geometric
frustration* against the Golay [24,12,8] code — the same code the GLM's
24-coordinate carriers live in. The claim "not a simulation of a CPU" is
literal at this level: there is a real ISA, a real two-pass assembler, a
real dispatcher, and every storage element is mediated by an actual
(error-correcting) code with a measured displacement curve. The point of
all this geometry is *verification*: because the storage has physics, a
computation can carry evidence about the state that produced it (NRCI
fingerprints, trace hashes), which plain integer storage cannot.

## 2. The layers, bottom up

### 2.1 The Golay substrate (`core/golay_engine.py`)

- The extended binary Golay code **[24,12,8]**: 24-bit words, 4096
  codewords, minimum distance 8, 759 octads (weight-8 codewords), self-dual
  and doubly even. Engine methods: `encode(message)` (systematic
  G = [I₁₂ | B]), `decode`, `snap_to_codeword` (nearest-codeword snap with
  syndrome weight), `get_all_codewords`, `get_octads`.
- **Verified identity (exp01):** NoiseCore's engine and GLM's
  `glm_universal.substrate.mog.GOLAY_MASKS` are the *same* code under the
  *same* labelling — 4096/4096 codewords equal with bit *i* at position *i*,
  759/759 octads shared, and the systematic encodings agree 4096/4096.
  Any mask is portable between the two systems as-is.

### 2.2 The cell (`core/substrate.py`, `NoiseCellV3`)

A 24-bit manifold storing one **base-12 digit** (0..11) as geometric
frustration:

- `baseline_sw` — syndrome weight of the substrate word itself;
- `displacement_curve[k]` for k = 0..12 — the measured drop in syndrome
  weight caused by a k-bit perturbation (calibrated at construction);
- `elastic_limit` — the largest k whose displacement stays non-negative;
- `substrate_read()` — the physical reading: logical digit, displacement,
  syndrome weight, and `sm_consistent` (is displacement == digit? the
  "linear regime" check);
- `fingerprint()` — UBP fingerprint: substrate hamming weight, baseline,
  digit, displacement, NRCI = 10/(10 + |hw − 12|).

Two operating modes: **SM** (substrate-mediated: the displacement IS the
answer) and **SV** (substrate-verified: the digit is the answer, the
substrate vouches for it). The CPU uses SV semantics with SM checks.

**Engineering note (this is where the speed went, and where "generate,
don't store" fixes it):** the curve is a pure function of (substrate,
base) — every cell computes the same 13 points — yet the shipped
constructor recalibrates per cell (27,459 `snap_to_codeword` calls to
build one default CPU). `accelerate.py` computes it once and copies it.
Additionally, `substrate_read` shipped with
`curve.get(k, self.probe_displacement(k))` — Python evaluates that fallback
*eagerly*, so the expensive probe ran even when the answer was already in
the curve. Both fixes are proven bit-identical by `fidelity_test.py`.

### 2.3 The register (`NoiseRegisterV3`)

- Arbitrary-precision **base-12 positional** register: digit i is cell i,
  value = Σ digitᵢ · 12ⁱ. `auto_expand` grows the cell stack for big
  magnitudes (effectively unbounded).
- Sign lives **above** the substrate: `CPU._write_reg` stores the magnitude
  in the register and the sign in a parallel `_signs` array — geometric
  displacement stays non-negative, exactly as the UBP "v2 fix" demands.
  This is why GLM's negative Leech coordinates round-trip exactly.
- Writes sync digits to cells and record a per-write trace
  (`_record` → `substrate_verify`); reads reconstruct the value from digits.
  (Tier-2 acceleration elides the recording; the reconstruction is provably
  equal to the cached value over random 31-bit writes.)

### 2.4 The CPU (`vm/cpu.py`)

- 8 registers (R7 = stack pointer), N-cell main memory (default 256 —
  the coprocessor raises this to 4096), flags {Z, N, C, V}, call stack,
  cycle counter, console device, optional trace recorder.
- **Sign-magnitude arithmetic at the ALU layer**: `ADD/SUB/MUL/DIV/MOD`
  operate on signed values and update flags with correct signed/unsigned
  semantics; the substrate only ever sees magnitudes.
- `word_bits` configures flag/overflow bookkeeping and `NOT` masking —
  but note (exp05, verified) it does **not** clamp stored values; a
  24-bit mask round-trips even at `word_bits=8`. Treat the VM's integers
  as unbounded in practice and the width as advisory.
- Two execution modes: `substrate_mode=True` (every register/memory cell
  is a real `NoiseRegisterV3` — the physically valid route) and
  `substrate_mode=False` (plain ints — fast, for unit tests).
- **Certification:** with `trace=True` every instruction appends a
  `TraceEntry` (pc, instr, flags before/after, cycle) and the run returns
  `trace_hash` — SHA-256 over the trace. `substrate_fingerprint()` returns
  `{mode, nrci_mean, magnitude_sha}`. Verified (exp06): hashes are
  reproducible across runs and sensitive to a 1-bit input change.

### 2.5 The ISA (`vm/isa.py`)

| family | ops | notes |
|---|---|---|
| arithmetic/logic | LOAD MOV ADD SUB AND OR XOR NOT LSL LSR MUL DIV MOD CMP HALT | LSL/LSR take **immediate** shift counts |
| control flow | JMP JZ JNZ JN JNN JC JE JNE JG JL JGE JLE | flags from CMP/CMPI/arithmetic |
| immediate | ADDI SUBI MULI ANDI ORI CMPI | CMPI = compare reg with imm |
| memory | STORE LOAD_MEM STOREI LOADI STOREX LOADX | LOADI/STOREI indirect; LOADX/STOREX base+offset |
| stack | PUSH POP CALL RET | R7 = SP, grows down from memory_size−1 |
| syscalls | SYSCALL NOP | 1 PRINT_INT 2 PRINT_CHAR 3 PRINT_STR 4 READ_INT 5 EXIT 6 PRINT_NL 7 DUMP_REGS |
| delta-sigma | DSSTATE DSBIT DSAVG DSONES DYORBIT ODORBIT | exact `Fraction` math, results as scaled ints |
| zero-storage | SYN ISGOLAY DECODE LEDGER MDSBIT MDSRT NRCI2 COST | the substrate-native family |

The **zero-storage family** is the crown jewel for GLM work:

- `SYN Rs` — 12-bit syndrome of the 24-bit word in Rs
- `ISGOLAY Rs` — 1 iff Rs is a Golay codeword — **computed, no table**
- `DECODE (R, Rs)` — nearest Leech point to the 24-int target at
  mem[Rs..+23]; writes the point back to those cells, Rd = decode cost
- `NRCI2` — the UBP noise-to-signal metric between two 16-cell streams

### 2.6 The assembler (`vm/assembler.py`)

Two-pass, symbolic: labels (`loop:`), constants (`.equ N 30`), data
(`.data name v v v...` — placed sequentially from address 0), char
literals, hex/binary/negative immediates. Round-trip disassembly is
bit-identical. Programs are assembled to opcode tuples and executed
directly — instructions do **not** occupy the 256-cell data memory.

### 2.7 The Leech decoder (`decoder.py`)

Nearest-point decoding for the Leech lattice Λ₂₄ by exhaustion over the
8192 Construction-C cosets (with early-abort pruning; the exhaustive
reference route exists for testing; the per-coset optimality facts are
Lean-proved in the project). **Units contract (discoverable only by
probing — now fixed here):**

- the *target* enters as 24 integers in **1/256 units**;
- the returned *point* is in **whole units** — which are exactly GLM's
  integer-model units;
- so: `decode(glm_point × 256)["point"] == glm_point` for any GLM lattice
  point (verified 40/40 and 30/30 in exp03/03b), and decode costs compare
  against `(256·z − y)²` sums.

### 2.8 Delta-sigma rationals (`delta_sigma.py`, `vm/delta_sigma_ops.py`)

Rationals enter as exact `Fraction(num, den)` and leave as integers:
`DSONES R,#n,#num,#den` = ⌊n·num/den⌋ exactly (count of 1-bits of the
modulator); `DSAVG` = first-n-bit average × 10⁶; `DSBIT` = bit n;
`DYORBIT`/`ODORBIT` = orbit steps. **Contract:** exact rational *equality*
(GLM's D7) cannot be represented in a register — only scaled integers.
Checks that need exact equality belong on the Python/GLM side.

### 2.9 NRCI and the ledger (`nrci.py`, `ledger.py`)

NRCI = the framework's noise-to-correlation metric; `NRCI2` computes a
scaled (×10⁶) version between 16-cell streams, and the ledger counts
substrate operations (syndromes, decodes, int-squares...) for cost
accounting (`LEDGER`, `COST` opcodes). Fingerprints expose `nrci_mean`
over register cells.

## 3. Conventions and seams (read before integrating!)

1. **Bit order.** The engine and GLM put bit *i* at position *i*. The
   `core/syndrome` module used by the `SYN`/`ISGOLAY` opcodes puts bit *i*
   at position 23−*i*. Proof: GLM codewords pass `is_golay` at 4/4096 raw
   and 4096/4096 bit-reversed. **The coprocessor absorbs this** (`rev24`
   at the API boundary) — always go through `CertifiedSubstrate.is_golay`
   / `.syndrome` or reverse masks yourself.
2. **Syndrome values.** Only the *zero test* is portable (0 ⇔ codeword).
   The 12-bit syndrome value itself uses a private convention and does not
   equal GLM's `syndrome_int` even after reversal.
3. **Leech units.** §2.7 — targets ×256, points in whole units.
4. **Trace accumulation.** `cpu.trace` accumulates across `run()` calls on
   a reused CPU and `trace_hash` covers all of it — clear `cpu.trace`
   between runs (the coprocessor does).
5. **Syscall routing.** Dispatch goes through `cpu.devices[0]`, not
   `cpu.console` — replacing the console attribute alone detaches output.
6. **`.data` origin** is address 0 and sequential within the source.

## 4. What maps onto this from the GLM

| GLM object | NoiseCore form | status |
|---|---|---|
| 24-bit letter word (token mask) | one register / `.nca` loop | **bit-exact** (exp02) |
| Golay word overlap (jaccard) | AND/OR + popcount loop, exact (inter, union) pair | **bit-exact** |
| leech2 signed 24-dim inner product | LOADX/MUL/ADD loop | **bit-exact** incl. negatives |
| `GOLAY.encode_mask` systematic encode | generated G=[I\|B] on the VM | **bit-exact** (4096/4096) |
| `golay_decode.decode_complete` nearest codewords | `SYN`+`ISGOLAY` (zero route) | works via reversal; candidate sets need the Python decoder |
| leech2 lattice membership / nearest point | `DECODE` opcode | **exact**, units contract applied |
| exact `Fraction` arithmetic | delta-sigma scaled ints | approximation only — keep on GLM side |
| the semantics graph, retrieval stack, Lean-checked evaluation | — | stay in Python/Lean |

## 5. Generate, don't store — the shared doctrine

GLM derives its figures and structures by *execution* rather than
quoting tables (`glm_universal.figures`, `derived.memo`). NoiseCore's
zero-storage family is the same doctrine at the ISA level: `ISGOLAY`
answers codeword membership *without the 4096-word table existing
anywhere*. The coprocessor follows suit:

- `golay_codewords()` / `octads()` **stream** the code; nothing is kept;
- `golay_encode` builds its generator rows by *generating* them from
  `encode(unit vectors)` at first use;
- `verify_stream(4096)` checks the entire code on the VM in one program
  with **zero table cells** (measured: 0.3 s, 12,293 cycles);
- the cell calibration is computed once and *copied* (a generated
  constant, not a per-cell measurement).

This is why the expanded substrate matters less than it seemed: you do
not need to *store* GLM-scale tables in VM memory when the substrate can
*generate* the answers. Memory expansion (256 → 4096 by default, 16384
measured) is there for streaming workloads and target buffers.

## 6. The acceleration tiers (measured, proven)

| tier | what | fidelity claim | measured effect |
|---|---|---|---|
| 0 raw | shipped code | — | 256-cell CPU build 1.3 s; 4096-cell 21.6 s |
| 1 exact | shared calibration + lazy curve lookup + O(1) register read | **byte-identical** values, cycles, trace hashes, fingerprints (82/82 records) | build 2 ms / 55 ms (**548× / 393×**); kernels **5.6–18.9×** |
| 2 turbo | + elide per-write register traces | identical outputs & certificates; internal write-traces not recorded | kernels up to **11–19×** vs raw |

## 7. Where the time still goes (honest residuals)

- `leech_decode` is ~228 ms per call at every tier: the cost is the
  decoder's 8192-coset search, not the register file. If GLM needs bulk
  nearest-point decoding, batch targets per program (the decode loop is
  Python-side) or profile `decoder.decode`'s pruning — that is the next
  big win, and it is decoder work, not substrate work.
- Even tier 2 is slower than GLM's Python for pure arithmetic
  (e.g. `is_golay` ≈ 0.10 ms on the VM vs ≈ 1 µs in Python). **Use the
  VM for what it certifies, not for what it computes fast**: compute in
  Python/Lean, and run the final state through the substrate to obtain
  the certificate — or accept VM speed where auditability is the point.
- Substrate register ops still cost tens of µs; the remaining hot spots
  are the base-12 digit sync on writes and the per-op dispatch.

## 8. The reverse direction: what the GLM gives NoiseCore

Everything above is NoiseCore serving the GLM. This section is the other
way round — including asking the GLM *outright* (`GLM.py -q ...`) and
implementing what came back.

### 8.1 Asked outright — what the machine said

**`report zero storage`** is an audit of the generate-don't-store doctrine
itself, and three of its findings land directly on NoiseCore:

1. *"Generating is right in principle — but a generator has to be checked
   against what it replaces."* It measured stored tables at 9,449,445
   bytes vs 24,648 for their generators, every regenerated object compared
   identical before the row was emitted. **Adopted here:**
   `CertifiedSubstrate._codewords()` generates the 4096 words from the 12
   rows, audits them (count, distinctness, distance, closure), and caches
   the derivation with a SHA-256 digest (`generator_audit`).
2. *A wrong Leech sieve, caught and repaired.* A proposed "all coordinates
   agree mod 4" membership test is sound but keeps only 1,152 of the
   196,560 minimal vectors; the right Construction-C condition is that **the
   coordinates which disagree form a Golay codeword**. The repaired sieve
   agreed with the package's membership test on all 196,565 vectors tested.
   This is the exact condition NoiseCore's coset decoder is built on — the
   GLM independently re-derived and stress-tested it.
3. *Snapping is where silent wrong answers live.* A snap-style lattice
   decoder "returned a non-lattice point on 4 of 4 targets in general
   position", while the exact coset decoder was inside the lattice and
   within the covering radius every time. **Adopted here:** the coprocessor
   offers `decode_complete` (exact, all nearest codewords) and deliberately
   no lattice snap. NoiseCore's `decoder.decode` is already exact coset
   decoding — good — and its word-level `snap_to_codeword` should not be
   promoted to lattice work.
4. *"A process is a number only when the error is a function of the work."*
   The report's exactness doctrine applies to NoiseCore's delta-sigma
   scaled integers: the ×10⁶ outputs are fine as long as their error is
   stated (≤ 1 unit at 10⁶), and `DSONES` is exact; float-like claims
   without an error bound are where this report refused 3 of 3 constants.

**`report admission`** supplied the refusal doctrine now used in every
`Certified.status` and `extra["refused"]` field: a refusal is *conditional
and names its condition* ("refused as portable — condition: private
syndrome convention"), never a bare no — and asking twice gives the same
answer.

### 8.2 Methods ported into this package (this round)

| GLM method | where it now lives here |
|---|---|
| complete syndrome decoding, ties never broken (`golay_decode.Decoding`) | `CertifiedSubstrate.decode_complete` → `Decoding` dataclass (status: codeword / corrected / ambiguous; six sextet candidates at weight 4, verified against GLM's decoder in `fidelity_test.py`) |
| re-derived figures, never quoted (directive D6) | `CertifiedSubstrate.figures()` — every published count recomputed by execution, mismatch names the figure |
| checked generators + caches-with-digest | `_codewords()` audit + `generator_audit` |
| conditional named refusals (admission) | `Certified.status` + `extra["refused"]` / `refusal_condition` |
| probes that locate boundaries | `fidelity_test.py` GLM-parity block |

### 8.3 The Lean corpus is NoiseCore's missing verification half

NoiseCore's README says "Lean-proved contract" for subsystems — the proofs
(or their siblings) live in GLM's `RequestProject/GLM/` (122+ Lean files,
`lake build`, no `sorry`). The mapping by subject:

| NoiseCore module | GLM Lean files |
|---|---|
| `delta_sigma.py`, `vm/delta_sigma_ops.py` | `DeltaSigma.lean`, `Mantissa.lean`, `ScaleConversion.lean` |
| `vm/zero_storage_ops.py`, `core/zs.py` | `ZeroStorage.lean`, `ZeroStorageV5.lean` |
| `deep_hole.py` | `DeepHoleClassifier.lean`, `DeepHoleEscalation.lean`, `DeepHoleFailure.lean` |
| the `core/syndrome` bit-order seam (§3) | `Endianness.lean`, `CoordinateOrder.lean` |
| `decoder.py` (coset decoding, ties) | `Steiner.lean`, `Packing.lean`, `GolayBoundary.lean`, `TieBreak.lean` |
| memory/capacity questions (exp05) | `FitCapacity.lean` |
| test methodology | `ProbeOracle.lean`, `Calibration.lean` |
| shared substrate theory | `GolayMOG.lean`, `GolayWeightEnum.lean`, `ZeroStorageV5.lean` |

(Honesty: `lake build` was not re-run here; the mapping is by name and
subject. The next verification step is to point NoiseCore's contracts at
these files: e.g. state the displacement-curve and sign-magnitude lemmas as
Lean obligations next to `DeltaSigma.lean`'s existing contract.)

### 8.4 What NoiseCore should borrow next (not done here)

1. **A corpus-consistency gate** in GLM's style (`glm_universal.corpus
   --check`): every documented figure recomputed, every link resolved. It
   would have caught the drift found in exp baselines — `SubstrateALU` /
   `ShadowRegister` imports pointing at nothing, the `S`-flag test, and
   the README's "5–10× slower" against the measured 57–63×.
2. **Declared-expectation probes** (`capabilities/` style): before a test
   runs, state what it is expected to do; a changed verdict is then either
   a regression or a newly won capability, named as such.
3. **Refusal by name in the VM**: `DECODE`/`SYN` could return status codes
   alongside values (unique / ambiguous / out-of-contract) instead of
   silently choosing — the ISA already has room (flags).

## 9. File map

| file | role |
|---|---|
| `coprocessor.py` | the certified GLM-facing API (kernels + certificates + conventions), `decode_complete`, `figures` | 
| `accelerate.py` | opt-in runtime acceleration, tier 1/2, `reset()` for A/B |
| `run_all.py` | fidelity + bench + a demo certificate, one command |
| `README.md` | quick start |
