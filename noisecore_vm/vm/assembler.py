"""
================================================================================
NoiseCore VM — Assembler
================================================================================
Two-pass symbolic assembler for NoiseCore Assembly (.nca) files.

Source format (whitespace + line-oriented):

    ; comment starting with ';' or '#'
    .equ NAME value           ; named constant (decimal/hex/binary)
    .data buf 0 0 0 0         ; reserve memory & set initial values
    label:                    ; label (column-anchored)
        LOAD  R0, #5
        ADD   R1, R0, R0
        JMP   label

Operand forms
-------------
    R0..R7          register
    #imm            immediate (int literal or .equ name)
    addr            absolute program address (label) or .equ name or int
    string forms accepted: hex 0x.., binary 0b.., decimal, char 'A'

Output
------
A list of instruction tuples that the CPU.execute() can consume directly.

Memory init layout
------------------
.data labels are placed sequentially in main memory starting at address 0
(unless `.org` is used). The data label resolves to the start address.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any

from .isa import MNEMONIC_TO_OPCODE, ISA, OpSpec


class AssemblerError(Exception):
    """Raised on assembly errors. Carries line number when available."""
    def __init__(self, message: str, line_no: Optional[int] = None,
                 line_text: str = ""):
        super().__init__(message)
        self.line_no = line_no
        self.line_text = line_text

    def __str__(self):
        if self.line_no is not None:
            return f"line {self.line_no}: {super().__str__()}\n  > {self.line_text}"
        return super().__str__()


@dataclass
class AssembledProgram:
    """Result of assembling a source file."""
    instructions: List[Tuple]                # the program
    labels:       Dict[str, int]             # label → instr index
    constants:    Dict[str, int]             # .equ name → value
    data_layout:  Dict[str, Tuple[int, List[int]]]  # name → (start_addr, values)
    source:       str = ""                   # original source

    def memory_init(self) -> Dict[int, int]:
        """Flatten .data into {addr: value}."""
        out: Dict[int, int] = {}
        for name, (start, values) in self.data_layout.items():
            for i, v in enumerate(values):
                out[start + i] = v
        return out


# ── PARSER HELPERS ──────────────────────────────────────────────────────────

def _smart_split(s: str) -> List[str]:
    """Whitespace-split that preserves single-quoted char literals."""
    out: List[str] = []
    i = 0
    n = len(s)
    while i < n:
        if s[i].isspace():
            i += 1
            continue
        if s[i] == "'" and i + 2 < n and s[i + 2] == "'":
            out.append(s[i:i+3])
            i += 3
            continue
        # take token until next whitespace
        j = i
        while j < n and not s[j].isspace():
            j += 1
        out.append(s[i:j])
        i = j
    return out


_RE_LABEL  = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$")
_RE_REG    = re.compile(r"^[Rr](\d+)$")
_RE_HEX    = re.compile(r"^0x[0-9A-Fa-f]+$")
_RE_BIN    = re.compile(r"^0b[01]+$")
_RE_DEC    = re.compile(r"^-?\d+$")
_RE_CHAR   = re.compile(r"^'(.)'$")


def _parse_int(token: str, constants: Dict[str, int]) -> int:
    """Parse a literal or named constant into an integer."""
    t = token.strip()
    if t.startswith("#"):
        t = t[1:]
    if _RE_HEX.match(t):  return int(t, 16)
    if _RE_BIN.match(t):  return int(t, 2)
    if _RE_DEC.match(t):  return int(t, 10)
    m = _RE_CHAR.match(t)
    if m: return ord(m.group(1))
    if t in constants: return constants[t]
    raise AssemblerError(f"Cannot parse integer: '{token}'")


def _parse_register(token: str) -> int:
    m = _RE_REG.match(token.strip())
    if not m:
        raise AssemblerError(f"Expected register, got '{token}'")
    n = int(m.group(1))
    if not (0 <= n <= 31):
        raise AssemblerError(f"Register index out of range: R{n}")
    return n


def _split_operands(operand_text: str) -> List[str]:
    if not operand_text.strip():
        return []
    return [o.strip() for o in operand_text.split(",")]


# ── ASSEMBLER ───────────────────────────────────────────────────────────────

class Assembler:
    """
    Two-pass assembler.

    Pass 1: scan lines, collect labels, .equ constants, .data blocks.
    Pass 2: encode each instruction, resolving label/constant references.
    """

    def __init__(self, data_origin: int = 0):
        self.data_origin = data_origin

    def assemble(self, source: str) -> AssembledProgram:
        constants: Dict[str, int] = {}
        labels: Dict[str, int] = {}
        data_layout: Dict[str, Tuple[int, List[int]]] = {}

        # Pass 0: tokenise lines, strip comments
        raw_lines = source.splitlines()
        tokens: List[Tuple[int, str, str]] = []   # (line_no, label_or_none, body)

        for line_no, raw in enumerate(raw_lines, start=1):
            # Strip comments (; or # to end of line, but not inside char literals)
            stripped = self._strip_comment(raw)
            if not stripped.strip():
                continue
            # split label and rest
            m = _RE_LABEL.match(stripped.strip())
            if m:
                lbl = m.group(1)
                body = m.group(2).strip()
                tokens.append((line_no, lbl, body))
            else:
                tokens.append((line_no, "", stripped.strip()))

        # Pass 1: walk tokens, assign instruction indices, register labels/.equ/.data
        # We need to know data_origin — set free pointer
        data_ptr = self.data_origin
        instr_index = 0
        instr_tokens: List[Tuple[int, Tuple[str, ...]]] = []  # (line_no, parts)

        for line_no, label, body in tokens:
            # When a label is on the same line as an instruction (e.g. "start: LOAD R0, #5"),
            # _RE_LABEL has already split them into (label="start", body="LOAD R0, #5").
            # We cannot record the label→index binding yet because instr_index hasn't
            # been incremented for this line. The binding is recorded further below,
            # immediately before the instruction token is appended to instr_tokens.
            # Labels on bare lines (no body) are handled in the `if not body:` block.

            if not body:
                # bare label line — record as instruction-position label
                if label:
                    labels[label] = instr_index
                continue

            # Tokenise body into directive/mnemonic + operands
            head_match = re.match(r"^([\.\w]+)\s*(.*)$", body)
            if not head_match:
                raise AssemblerError(f"Cannot parse line", line_no, body)
            head = head_match.group(1)
            tail = head_match.group(2)

            if head.startswith("."):
                # directive
                if head == ".equ":
                    parts = tail.split(None, 1)
                    if len(parts) != 2:
                        raise AssemblerError(".equ requires NAME VALUE", line_no, body)
                    name, val = parts[0], parts[1].strip()
                    constants[name] = _parse_int(val, constants)
                    if label:
                        labels[label] = instr_index
                elif head == ".data":
                    # .data NAME val val val...
                    parts = _smart_split(tail)
                    if not parts:
                        raise AssemblerError(".data requires NAME", line_no, body)
                    name = parts[0]
                    values = [_parse_int(v, constants) for v in parts[1:]] if len(parts) > 1 else [0]
                    data_layout[name] = (data_ptr, values)
                    constants[name] = data_ptr   # so label name resolves to address
                    data_ptr += len(values)
                    if label:
                        labels[label] = instr_index
                elif head == ".org":
                    parts = tail.split()
                    if not parts:
                        raise AssemblerError(".org requires VALUE", line_no, body)
                    data_ptr = _parse_int(parts[0], constants)
                    if label:
                        labels[label] = instr_index
                else:
                    raise AssemblerError(f"Unknown directive: {head}", line_no, body)
            else:
                # instruction
                if label:
                    labels[label] = instr_index
                instr_tokens.append((line_no, (head, tail)))
                instr_index += 1

        # Pass 2: encode
        instructions: List[Tuple] = []
        for line_no, (mn, tail) in instr_tokens:
            mn_u = mn.upper()
            spec = MNEMONIC_TO_OPCODE.get(mn_u)
            if spec is None:
                raise AssemblerError(f"Unknown mnemonic: {mn}", line_no, mn + " " + tail)

            operands = _split_operands(tail)
            if len(operands) != len(spec.operands):
                raise AssemblerError(
                    f"{mn_u} expects {len(spec.operands)} operand(s), got {len(operands)}",
                    line_no, mn + " " + tail
                )

            encoded: List[int] = [spec.opcode]
            for kind, tok in zip(spec.operands, operands):
                try:
                    if kind == "R":
                        encoded.append(_parse_register(tok))
                    elif kind == "#":
                        # immediate: may reference constant or literal
                        if tok in labels:
                            encoded.append(labels[tok])
                        else:
                            encoded.append(_parse_int(tok, constants))
                    elif kind == "A":
                        # address: label or literal
                        if tok in labels:
                            encoded.append(labels[tok])
                        elif tok in constants:
                            encoded.append(constants[tok])
                        else:
                            encoded.append(_parse_int(tok, constants))
                    elif kind == "S":
                        encoded.append(_parse_int(tok, constants))
                    else:
                        raise AssemblerError(f"Unknown operand kind: {kind}",
                                             line_no, mn + " " + tail)
                except AssemblerError as e:
                    if e.line_no is None:
                        e.line_no = line_no
                        e.line_text = mn + " " + tail
                    raise

            instructions.append(tuple(encoded))

        return AssembledProgram(
            instructions=instructions,
            labels=labels,
            constants=constants,
            data_layout=data_layout,
            source=source,
        )

    @staticmethod
    def _strip_comment(line: str) -> str:
        """Strip `;` comments while preserving `#` (used as immediate prefix)
        and char literals like 'X'."""
        out = []
        i = 0
        while i < len(line):
            c = line[i]
            if c == "'" and (i + 2 < len(line)) and line[i + 2] == "'":
                out.append(line[i:i+3])
                i += 3
                continue
            if c == ";":
                break
            out.append(c)
            i += 1
        return "".join(out)


# ── CONVENIENCE ─────────────────────────────────────────────────────────────

def assemble(source: str, data_origin: int = 0) -> AssembledProgram:
    return Assembler(data_origin=data_origin).assemble(source)
