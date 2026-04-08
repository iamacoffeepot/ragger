"""Tests for dialogue tree parser."""

from scripts.pipeline.fetch_dialogues import parse_dialogue_tree, parse_line_content


SAMPLE_WIKITEXT = """{{Transcript|Quest}}
{{Transcript list|Cook (Lumbridge)}}

==Starting off==
* '''Cook:''' What am I to do?
* {{topt|What's wrong?}}
** '''Player:''' What's wrong?
** '''Cook:''' Oh dear, oh dear, I'm in a terrible mess!
** {{tselect|Start the Cook's Assistant quest?}}
** {{topt|Yes.}}
*** '''Player:''' Yes, I'll help you.
*** '''Cook:''' Oh thank you. I need milk, an egg and flour.
*** {{tcond|If the player already has the necessary items:}}
**** '''Player:''' I have all of those ingredients on me already!
**** {{tbox|pic=Pot of flour detail.png|pic2=Bucket of milk detail.png|You hand the cook all of the ingredients.}}
**** {{tact|end}}
** {{topt|No.}}
*** '''Player:''' No way.
*** {{tact|end}}

==Treasure Trails==
===Beginner===
* '''Cook:''' Well done.
* {{tact|receives=a casket}}
"""


def test_parse_transcript_type():
    page_type, _ = parse_dialogue_tree(SAMPLE_WIKITEXT)
    assert page_type == "quest"


def test_node_count():
    _, nodes = parse_dialogue_tree(SAMPLE_WIKITEXT)
    assert len(nodes) == 17


def test_root_nodes_have_no_parent():
    _, nodes = parse_dialogue_tree(SAMPLE_WIKITEXT)
    roots = [n for n in nodes if n["parent_idx"] is None]
    # depth-1 nodes under sections have no parent
    assert len(roots) > 0
    for r in roots:
        assert r["depth"] == 1


def test_tree_structure():
    _, nodes = parse_dialogue_tree(SAMPLE_WIKITEXT)
    # "What's wrong?" option at depth 1
    opt = nodes[1]
    assert opt["node_type"] == "option"
    assert opt["text"] == "What's wrong?"
    assert opt["parent_idx"] is None  # depth 1, no parent

    # Player response at depth 2 should be child of the option
    player = nodes[2]
    assert player["speaker"] == "Player"
    assert player["parent_idx"] == 1  # index of the option


def test_section_tracking():
    _, nodes = parse_dialogue_tree(SAMPLE_WIKITEXT)
    # First section
    assert nodes[0]["section"] == "Starting off"
    # Subsection
    last_two = nodes[-2:]
    for n in last_two:
        assert n["section"] == "Treasure Trails/Beginner"


def test_node_types():
    _, nodes = parse_dialogue_tree(SAMPLE_WIKITEXT)
    types = {n["node_type"] for n in nodes}
    assert "line" in types
    assert "option" in types
    assert "condition" in types
    assert "action" in types
    assert "box" in types
    assert "select" in types


def test_tbox_text_extraction():
    _, nodes = parse_dialogue_tree(SAMPLE_WIKITEXT)
    boxes = [n for n in nodes if n["node_type"] == "box"]
    assert len(boxes) == 1
    assert "hand the cook" in boxes[0]["text"]


def test_parse_line_content_speaker():
    result = parse_line_content("'''Hans:''' Hello there!")
    assert result["node_type"] == "line"
    assert result["speaker"] == "Hans"
    assert result["text"] == "Hello there!"


def test_parse_line_content_option():
    result = parse_line_content("{{topt|Tell me more.|quest=no}}")
    assert result["node_type"] == "skip_quest"
    assert result["text"] == "Tell me more."


def test_parse_line_content_action():
    result = parse_line_content("{{tact|end}}")
    assert result["node_type"] == "action"
    assert result["text"] == "end"
