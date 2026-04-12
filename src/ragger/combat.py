"""OSRS combat-level calculation utilities."""


def combat_level(
    *,
    attack: int = 1,
    strength: int = 1,
    defence: int = 1,
    hitpoints: int = 10,
    ranged: int = 1,
    magic: int = 1,
    prayer: int = 1,
) -> int:
    """Return the OSRS combat level for a given set of combat skill levels.

    Formula (from the OSRS combat level calculation):

        base  = (defence + hitpoints + floor(prayer / 2)) / 4
        melee = 13/40 * (attack + strength)
        range = 13/40 * floor(3 * ranged / 2)
        magic = 13/40 * floor(3 * magic / 2)
        combat = floor(base + max(melee, range, magic))

    All seven skills default to the fresh-account starting levels
    (all 1 except Hitpoints, which starts at 10).

    Ranged and Magic use floor(3 * level / 2) so an odd level contributes
    the same "attack score" as the even level below it — this matches the
    in-game rounding and is not a Python integer-division artifact.
    """
    base = (defence + hitpoints + prayer // 2) / 4
    melee_score = 13 / 40 * (attack + strength)
    ranged_score = 13 / 40 * (3 * ranged // 2)
    magic_score = 13 / 40 * (3 * magic // 2)
    return int(base + max(melee_score, ranged_score, magic_score))
