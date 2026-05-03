"""Core subpackage — Golay engine + noise substrate."""
from .substrate import (
    NoiseCellV3, NoiseRegisterV3, SubstrateLibrary,
    NoiseALU, MathNetNoiseRunner, SubstrateCalibrator,
    GOLAY_AVAILABLE,
)

__all__ = [
    "NoiseCellV3", "NoiseRegisterV3", "SubstrateLibrary",
    "NoiseALU", "MathNetNoiseRunner", "SubstrateCalibrator",
    "GOLAY_AVAILABLE",
]
