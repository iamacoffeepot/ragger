from ragger.combat import combat_level


def test_fresh_account() -> None:
    assert combat_level() == 3


def test_maxed_account() -> None:
    assert combat_level(
        attack=99, strength=99, defence=99, hitpoints=99,
        ranged=99, magic=99, prayer=99,
    ) == 126


def test_pure_melee_takes_max_style() -> None:
    # Melee beats range/magic when only melee stats are trained
    assert combat_level(attack=60, strength=60, defence=1) > combat_level(magic=60)


def test_odd_magic_level_floors() -> None:
    # floor(3 * 41 / 2) == floor(3 * 40 / 2) == 60
    assert combat_level(magic=41) == combat_level(magic=40)


def test_prayer_half_floors() -> None:
    # floor(43/2) == floor(42/2) == 21
    assert combat_level(prayer=43) == combat_level(prayer=42)


def test_pure_mage_cb_50() -> None:
    # Pure mage with Prayer 43, HP 40: Magic 72 is the threshold for CB 50
    assert combat_level(magic=71, prayer=43, hitpoints=40) == 49
    assert combat_level(magic=72, prayer=43, hitpoints=40) == 50
