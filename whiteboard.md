# NoiseCore UI Enhancement Whiteboard

## Current Status
- Analyzed existing `index.html` (v1.2.0).
- Analyzed canonical Python implementation (`cpu.py`, `substrate.py`, `assembler.py`).
- Identified core requirements: Terminal input, transparency (Substrate mode details), full documentation, better UI.

## Architectural Decisions
1. **Terminal UI**: Replace the static console with an interactive terminal that supports `READ_INT` (SYSCALL 4) and provides a CLI-like experience.
2. **Substrate Transparency**:
   - Add a visual representation of the Golay substrate (24-bit manifold).
   - Display `carry_work` and `shadow_regime` transitions clearly.
   - Show base-12 digit decomposition for all registers.
3. **Documentation**:
   - Embed an "Architectural Theory" section based on `ARCHITECTURE.md`.
   - Explain the "Phenomenal" vs "Shadow" regimes.
   - Document the ISA and Syscalls.
4. **Substrate Mode Integrity**:
   - Ensure the JavaScript implementation matches the Python `SubstrateALU` and `ShadowRegister` logic exactly.
   - No "toy" versions: all arithmetic must be digit-by-digit base-12 with carry/borrow events.

## To-Do
- [ ] Implement interactive terminal with input handling.
- [ ] Create visual Substrate Manifold display.
- [ ] Add detailed documentation tabs (Theory, ISA, Guide).
- [ ] Refine the CSS for a "real computer" feel (CRT effects, layout).
- [ ] Update the `index.html` with the new implementation.
- [ ] Update repository README.
