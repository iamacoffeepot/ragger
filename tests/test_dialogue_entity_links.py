"""Unit tests for refine_entity_links."""
from __future__ import annotations

from ragger.dialogue.dialogue_entity_links import refine_entity_links


# Lookup keys are lowercased, un-slugged names. Tests use a small fixture.
FIXTURE_LOOKUP: dict[str, tuple[str, int]] = {
    "cook": ("npc", 1),
    "hard hat": ("item", 2),
    "cook's assistant": ("quest", 3),
    "lumbridge": ("location", 4),
    "general store": ("shop", 5),
    "wintertodt": ("activity", 6),
    "goblin": ("monster", 7),
    "rune scimitar": ("equipment", 8),
}


def test_refine_known_npc() -> None:
    src = "[Cook](wiki:Cook) is here."
    assert refine_entity_links(src, FIXTURE_LOOKUP) == "[Cook](npc:Cook) is here."


def test_refine_known_item_with_underscored_slug() -> None:
    src = "Get a [hat](wiki:Hard_hat)."
    assert refine_entity_links(src, FIXTURE_LOOKUP) == "Get a [hat](item:Hard_hat)."


def test_refine_known_quest() -> None:
    src = "[the quest](wiki:Cook's_Assistant)"
    assert refine_entity_links(src, FIXTURE_LOOKUP) == "[the quest](quest:Cook's_Assistant)"


def test_refine_anchor_preserved() -> None:
    # Anchor stays on the URL but isn't part of the lookup key.
    src = "See [riddles](wiki:Lumbridge#Riddles)."
    assert refine_entity_links(src, FIXTURE_LOOKUP) == "See [riddles](location:Lumbridge#Riddles)."


def test_refine_unknown_passes_through() -> None:
    src = "[Mystery](wiki:Some_Page)"
    assert refine_entity_links(src, FIXTURE_LOOKUP) == "[Mystery](wiki:Some_Page)"


def test_refine_multiple_links_in_one_line() -> None:
    src = "[Cook](wiki:Cook) said hi to [Lumbridge](wiki:Lumbridge)."
    assert refine_entity_links(src, FIXTURE_LOOKUP) == \
        "[Cook](npc:Cook) said hi to [Lumbridge](location:Lumbridge)."


def test_refine_idempotent_on_typed_links() -> None:
    # Already-typed links don't match the wiki: pattern.
    src = "[Cook](npc:Cook)"
    assert refine_entity_links(src, FIXTURE_LOOKUP) == "[Cook](npc:Cook)"


def test_refine_each_entity_type() -> None:
    cases = [
        ("[Hard hat](wiki:Hard_hat)", "[Hard hat](item:Hard_hat)"),
        ("[Cook](wiki:Cook)", "[Cook](npc:Cook)"),
        ("[Goblin](wiki:Goblin)", "[Goblin](monster:Goblin)"),
        ("[Cook's Assistant](wiki:Cook's_Assistant)", "[Cook's Assistant](quest:Cook's_Assistant)"),
        ("[Lumbridge](wiki:Lumbridge)", "[Lumbridge](location:Lumbridge)"),
        ("[General Store](wiki:General_Store)", "[General Store](shop:General_Store)"),
        ("[Wintertodt](wiki:Wintertodt)", "[Wintertodt](activity:Wintertodt)"),
        ("[Rune Scimitar](wiki:Rune_Scimitar)", "[Rune Scimitar](equipment:Rune_Scimitar)"),
    ]
    for src, expected in cases:
        assert refine_entity_links(src, FIXTURE_LOOKUP) == expected


def test_refine_empty_string() -> None:
    assert refine_entity_links("", FIXTURE_LOOKUP) == ""


def test_refine_no_links_passes_through() -> None:
    src = "Just plain text with no links at all."
    assert refine_entity_links(src, FIXTURE_LOOKUP) == src


def test_refine_case_insensitive_lookup() -> None:
    # Slug "COOK" lowercases to "cook" which is in the lookup.
    src = "[Cook](wiki:COOK)"
    assert refine_entity_links(src, FIXTURE_LOOKUP) == "[Cook](npc:COOK)"
