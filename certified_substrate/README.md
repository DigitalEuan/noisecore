# Certified Substrate Coprocessor

A certified Golay [24,12,8] / Leech Λ₂₄ coprocessor for the **GLM** (and
any other consumer), built on the **NoiseCore VM**
(`github.com/DigitalEuan/noisecore`) without modifying it.

Three guarantees:

1. **Canonical conventions** — speaks GLM's bit order and GLM's Leech
   units; the NoiseCore-internal seams (bit-reversed `SYN`/`ISGOLAY`
   masks, 1/256 decoder units, syndrome-value convention) are absorbed
   and documented.
2. **Certificates** — every answer carries the VM cycle count, the
   SHA-256 execution trace hash (reproducible, input-sensitive) and the
   substrate fingerprint (NRCI mean + magnitude hash).
3. **Generate, don't store** — no lookup tables in VM memory; codewords,
   generators and lattice points are generated from the code's own
   structure (measured: the full 4096-codeword corpus verified on the VM
   in 0.3 s using **zero** table cells).

## Quick start

```python
import sys; sys.path.insert(0, "certified_substrate")
from coprocessor import CertifiedSubstrate

cs = CertifiedSubstrate()                  # 4096-cell substrate memory
r = cs.letter_word("codeword")             # GLM-native kernel
r.value        # 4341788  (bit-exact with GLM)
r.certificate  # cycles, trace_hash, substrate_fingerprint, wall_s, mode

cs.jaccard_parts(0x555, 0xAAA)             # exact (inter, union)
cs.inner(x24, y24)                         # signed 24-dim Leech inner product
cs.golay_encode(42)                        # systematic encode, generator generated
cs.is_golay(mask)                          # table-free membership
cs.decode_complete(mask)                   # ALL nearest codewords; ties never
                                           #   broken (weight 4 -> 6 sextet mates)
cs.leech_decode(point24)                   # nearest Leech point (GLM units)
cs.figures()                               # every published count re-derived
                                           #   by execution (GLM directive D6)
cs.verify_stream(4096)                     # whole code verified, no table
```

## Both directions

NoiseCore serves the GLM (certified Golay/Leech coprocessing — see
`THEORY.md` §1–7), and the GLM serves NoiseCore (`THEORY.md` §8): complete
decoding with no silent ties, conditional named refusals, re-derived
figures, and **checked generators** ("a generator has to be checked against
what it replaces" — GLM `report zero storage`) — the code is generated
from 12 rows, audited, and cached with a digest. Asked outright, the GLM
also stress-tested the Leech membership condition, showed that snap-style
decoders return non-lattice points, and its Lean corpus maps 1:1 onto
NoiseCore's subsystems as a ready-made verification half.

## Files

| file | role |
|---|---|
| `THEORY.md` | the NoiseCore methods/systems/theory, captured and explained for builders |
| `coprocessor.py` | the certified API |
| `accelerate.py` | tier 1 ("exact") / tier 2 ("turbo") runtime acceleration |
| `run_all.py` | one command for everything |

Set `NOISECORE_PATH` if the noisecore tree is not at
`../glm-noisecore-lab/noisecore`.
