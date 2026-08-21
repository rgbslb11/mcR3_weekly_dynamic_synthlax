from __future__ import annotations

import hashlib
import math


def _uniform01(base_seed: int, *parts: object, slot: int) -> float:
    payload = "|".join([str(base_seed), *(str(p) for p in parts), str(slot)]).encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    integer = int.from_bytes(digest[:8], "big")
    return (integer + 0.5) / (2**64)


def deterministic_standard_normal(base_seed: int, *parts: object) -> float:
    """Stateless Box-Muller draw keyed by semantic coordinates.

    This makes a game's draw invariant to path iteration order and process scheduling.
    """
    u1 = max(_uniform01(base_seed, *parts, slot=0), 1e-15)
    u2 = _uniform01(base_seed, *parts, slot=1)
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def deterministic_normal(base_seed: int, mean: float, sd: float, *parts: object) -> float:
    return mean + sd * deterministic_standard_normal(base_seed, *parts)
