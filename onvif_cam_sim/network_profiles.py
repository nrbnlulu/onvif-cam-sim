"""Named network-quality presets and their mapping to gstreamer `netsim` properties."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NetworkProfile:
    drop_probability: float = 0.0
    delay_probability: float = 0.0
    min_delay_ms: int = 0
    max_delay_ms: int = 0
    duplicate_probability: float = 0.0
    max_kbps: int = -1

    @property
    def is_perfect(self) -> bool:
        return self == NetworkProfile()

    def to_netsim_properties(self) -> dict[str, float | int]:
        return {
            "drop-probability": self.drop_probability,
            "delay-probability": self.delay_probability,
            "min-delay": self.min_delay_ms,
            "max-delay": self.max_delay_ms,
            "duplicate-probability": self.duplicate_probability,
            "max-kbps": self.max_kbps,
        }


NETWORK_PRESETS: dict[str, NetworkProfile] = {
    "perfect": NetworkProfile(),
    "good": NetworkProfile(
        drop_probability=0.001,
        delay_probability=0.05,
        min_delay_ms=5,
        max_delay_ms=30,
        duplicate_probability=0.0,
        max_kbps=-1,
    ),
    "poor": NetworkProfile(
        drop_probability=0.03,
        delay_probability=0.2,
        min_delay_ms=20,
        max_delay_ms=150,
        duplicate_probability=0.005,
        max_kbps=800,
    ),
    "very_poor": NetworkProfile(
        drop_probability=0.1,
        delay_probability=0.4,
        min_delay_ms=50,
        max_delay_ms=400,
        duplicate_probability=0.02,
        max_kbps=250,
    ),
}
