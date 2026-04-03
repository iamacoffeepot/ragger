"""OSRS experience and level conversion utilities."""

import math

# Build XP table using the OSRS formula
# Level L requires sum from n=1 to L-1 of floor(n + 300 * 2^(n/7)) / 4
XP_TABLE: list[int] = [0, 0]  # index 0 unused, level 1 = 0 XP

_points = 0
for n in range(1, 99):
    _points += math.floor(n + 300 * (2 ** (n / 7.0)))
    XP_TABLE.append(_points // 4)


def xp_for_level(level: int) -> int:
    """Return the minimum XP required to reach a given level."""
    if level < 1 or level > 99:
        raise ValueError(f"Level must be between 1 and 99, got {level}")
    return XP_TABLE[level]


def level_for_xp(xp: int) -> int:
    """Return the level for a given amount of XP."""
    for level in range(99, 0, -1):
        if xp >= XP_TABLE[level]:
            return level
    return 1
