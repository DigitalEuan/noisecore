# Zero Storage in NoiseCore VM

## The claim, operationalised

Membership in the extended binary Golay code is **twelve parity checks against
36 bytes of generator** — not a 4096-entry table. Leech membership is parity
off coordinate 0, those same twelve checks, and one mod-8 sum. Every answer
carries an exact-integer **ledger** of what generating it cost, and the
`table_lookup` counter is the permanent trip-wire: it must be zero.

## Where each piece lives

| Piece | Module | ISA |
|---|---|---|
| Syndrome membership (`syndromeZero_iff_isGolay`) | `core/syndrome.py` | `SYN` 0x66, `ISGOLAY` 0x67 |
| Leech sieve (`refinedSieve_iff_isLeech`) | `core/syndrome.py::is_leech` | — |
| Coset decoder (`lattice_dist_ge` etc.) | `decoder.py` | `DECODE` 0x68 |
| Cost ledger (13 items, v5-compatible) | `ledger.py` | `LEDGER` 0x69, `COST` 0x6D |
| Moving-target modulator (`ds_track_bound`) | `moving_ds.py` | `MDSBIT` 0x6A, `MDSRT` 0x6B |
| NRCI, one definition, dyadic enclosure | `nrci.py` | `NRCI2` 0x6C |
| Cell/register verification all the way down | `core/zs.py` + `substrate.py` hooks | — |
| Cesàro dynamics (rate 24/N) | `cesaro.py` | — |
| Deep-hole classifier machinery | `deep_hole.py` | — |

## Verifying

    python3 -m pytest tests/test_zero_storage_v5.py tests/test_zero_storage_all_down.py \
                      tests/test_cesaro.py tests/test_deep_hole.py -q
    noisecore run examples/11_zero_storage_decode.nca   # prints: 1 0 0 24 0

The final `0` is the table_lookup counter read back from inside the VM.
