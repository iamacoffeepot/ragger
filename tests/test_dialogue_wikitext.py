"""Unit tests for normalize_dialogue_wikitext."""
from __future__ import annotations

from ragger.dialogue.dialogue_wikitext import normalize_dialogue_wikitext


def test_passes_plain_text() -> None:
    assert normalize_dialogue_wikitext("Hello there.") == "Hello there."


def test_empty_string_passthrough() -> None:
    assert normalize_dialogue_wikitext("") == ""


def test_wiki_link_simple() -> None:
    assert normalize_dialogue_wikitext("[[Cook]] is here.") == "[Cook](wiki:Cook) is here."


def test_wiki_link_with_alias() -> None:
    assert normalize_dialogue_wikitext("[[Cook's Assistant|the quest]] is hard.") == \
        "[the quest](wiki:Cook's_Assistant) is hard."


def test_wiki_link_multiple_in_one_line() -> None:
    assert normalize_dialogue_wikitext("[[Hans]] told [[Cook]] something.") == \
        "[Hans](wiki:Hans) told [Cook](wiki:Cook) something."


def test_plink_simple() -> None:
    assert normalize_dialogue_wikitext("Get a {{plink|cabbage}}.") == \
        "Get a [cabbage](item:cabbage)."


def test_plink_capitalized() -> None:
    assert normalize_dialogue_wikitext("Get a {{Plink|cabbage}}.") == \
        "Get a [cabbage](item:cabbage)."


def test_plink_with_alias() -> None:
    assert normalize_dialogue_wikitext("{{plink|cabbage|txt=veggie}}") == \
        "[veggie](item:cabbage)"


def test_bold() -> None:
    assert normalize_dialogue_wikitext("'''important'''") == "**important**"


def test_italic() -> None:
    assert normalize_dialogue_wikitext("''emphasized''") == "*emphasized*"


def test_bold_with_italic_inside() -> None:
    assert normalize_dialogue_wikitext("'''bold with ''italic'' inside'''") == \
        "**bold with *italic* inside**"


def test_player_slot_lowercase() -> None:
    assert normalize_dialogue_wikitext("Hello, <player>!") == "Hello, <player/>!"


def test_player_slot_capitalized() -> None:
    assert normalize_dialogue_wikitext("Hello, <Player>!") == "Hello, <player/>!"


def test_gender() -> None:
    assert normalize_dialogue_wikitext("{{Gender|young man|young woman}}") == \
        '<gender male="young man" female="young woman"/>'


def test_gender_lowercase_template_name() -> None:
    assert normalize_dialogue_wikitext("{{gender|he|she}}") == \
        '<gender male="he" female="she"/>'


def test_nowiki_template_strips_outer() -> None:
    assert normalize_dialogue_wikitext("{{nowiki}}raw text{{/nowiki}}") == "raw text"


def test_nowiki_tag_strips_outer() -> None:
    assert normalize_dialogue_wikitext("<nowiki>raw text</nowiki>") == "raw text"


def test_nowiki_then_bold_runs() -> None:
    # nowiki strip is currently order-dependent: outer markers go first,
    # then bold runs on the inner content. We accept this — the
    # rendered text is functionally identical, just markdown bold
    # instead of wiki bold.
    assert normalize_dialogue_wikitext("{{nowiki}}'''X'''{{/nowiki}}") == "**X**"


def test_tmissing() -> None:
    assert normalize_dialogue_wikitext("{{tmissing}}") == "<missing/>"


def test_tmissing_with_note() -> None:
    assert normalize_dialogue_wikitext("{{tmissing|todo: write this dialogue}}") == "<missing/>"


def test_overhead() -> None:
    assert normalize_dialogue_wikitext("{{overhead|Hello world!}}") == \
        "<overhead>Hello world!</overhead>"


def test_idempotent_on_normalized_text() -> None:
    once = normalize_dialogue_wikitext("[[Cook]] said '''hi''' to <player>.")
    twice = normalize_dialogue_wikitext(once)
    assert once == twice
    assert once == "[Cook](wiki:Cook) said **hi** to <player/>."


def test_unrecognized_template_passes_through() -> None:
    # We deliberately leave unknown templates alone — preserves content
    # rather than damaging it.
    assert normalize_dialogue_wikitext("{{unknown|foo}}") == "{{unknown|foo}}"


def test_plinkp_picture_variant() -> None:
    assert normalize_dialogue_wikitext("{{plinkp|saw}}") == "[saw](item:saw)"


def test_player_name_variant() -> None:
    assert normalize_dialogue_wikitext("Hello, <player name>!") == "Hello, <player/>!"
    assert normalize_dialogue_wikitext("Hello, <Player name>!") == "Hello, <player/>!"


def test_mes_strips_wrapper() -> None:
    assert normalize_dialogue_wikitext("{{mes|You place the shards in the cage.}}") == \
        "You place the shards in the cage."


def test_colour_drops_color_keeps_text() -> None:
    assert normalize_dialogue_wikitext("{{colour|red|Danger!}}") == "Danger!"
    assert normalize_dialogue_wikitext("{{color|blue|Cold}}") == "Cold"


def test_sic_dropped() -> None:
    assert normalize_dialogue_wikitext("somefing{{sic}} cool") == "somefing cool"


def test_sic_with_note_dropped() -> None:
    assert normalize_dialogue_wikitext("happens{{sic|Missing period}}") == "happens"


def test_trandom_dropped() -> None:
    assert normalize_dialogue_wikitext("{{trandom}}") == ""
    assert normalize_dialogue_wikitext("Hello{{trandom}}") == "Hello"


def test_combined_realistic_line() -> None:
    src = "'''Hans:''' Welcome, <player>. Have you visited [[Lumbridge]]?"
    expected = "**Hans:** Welcome, <player/>. Have you visited [Lumbridge](wiki:Lumbridge)?"
    assert normalize_dialogue_wikitext(src) == expected
