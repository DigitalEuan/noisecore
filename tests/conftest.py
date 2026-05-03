"""Pytest configuration. Adds project root to sys.path."""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest
from noisecore_vm import CPU, assemble


@pytest.fixture
def cpu():
    """Fast CPU (plain-int registers, substrate disabled — used for ISA tests)."""
    return CPU(substrate_mode=False)


@pytest.fixture
def cpu_substrate():
    """Substrate-backed CPU (Golay-mediated registers — used for substrate tests)."""
    return CPU(substrate_mode=True)


@pytest.fixture
def asm():
    """Convenience: source → list of instruction tuples."""
    def _asm(source: str):
        return assemble(source).instructions
    return _asm
