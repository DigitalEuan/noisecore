# NoiseCore VM v1.2.0 — Zero-Storage Validation Report

| Metric | Value |
|---|---|
| Opcodes | **59** |
| Self-dual syndrome route | verified at import (True) |
| Decode cost of [1/256]^24 target | 1048576 (coset m=1, word=0x000000) |
| Decode ledger | coset_trial=8192, pruned=8190, coord_pass=130960, pm4_repair=1, table_lookup=0 |
| NRCI(ΔΣ avg, t=2/7, N=512) | 0.914890970 (bound_ok=True) |
| NRCI(dyadic tower, depth 16) | 0.642262466 |
| Storage audit | stored 9447168 B      generator 36 B      ratio 262421 : 1 |
