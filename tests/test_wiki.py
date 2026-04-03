from ragger.wiki import (
    extract_coords,
    extract_section,
    extract_template,
    parse_skill_requirements,
    parse_template_param,
    resolve_region,
    strip_markup,
    strip_wiki_links,
)


def test_extract_coords_xy_param() -> None:
    text = "{{Map|x=3210|y=3448|zoom=2}}"
    assert extract_coords(text) == [(3210, 3448)]


def test_extract_coords_xy_param_spaces() -> None:
    text = "{{Map|x = 2414|y = 9680}}"
    assert extract_coords(text) == [(2414, 9680)]


def test_extract_coords_xy_colon() -> None:
    text = "{{Map|x:2454,y:3231|type=maplink}}"
    assert extract_coords(text) == [(2454, 3231)]


def test_extract_coords_xy_colon_multiple() -> None:
    text = "|x:2475,y:3398,icon:greenPin|x:2487,y:3401,icon:bluePin"
    assert extract_coords(text) == [(2475, 3398), (2487, 3401)]


def test_extract_coords_positional() -> None:
    text = "{{Map|2884,3398|caption=Entrance}}"
    assert extract_coords(text) == [(2884, 3398)]


def test_extract_coords_positional_multiple() -> None:
    text = "{{Map|2744,3155|2760,3063|mtype=pin}}"
    assert extract_coords(text) == [(2744, 3155), (2760, 3063)]


def test_extract_coords_empty() -> None:
    assert extract_coords("no coords here") == []


def test_extract_coords_prefers_xy_param() -> None:
    text = "{{Map|x=100|y=200|300,400}}"
    assert extract_coords(text) == [(100, 200)]


def test_resolve_region_simple() -> None:
    assert resolve_region("Varlamore") == 10


def test_resolve_region_none() -> None:
    assert resolve_region(None) is None
    assert resolve_region("") is None


def test_resolve_region_no() -> None:
    assert resolve_region("No") is None
    assert resolve_region("no") is None
    assert resolve_region("N/A") is None
    assert resolve_region("none") is None


def test_resolve_region_complex() -> None:
    # First region of first group
    assert resolve_region("Misthalin&Morytania&Asgarnia, Misthalin&Fremennik") == 7  # Misthalin


def test_resolve_region_with_comment() -> None:
    assert resolve_region("No <!-- This shop is disabled -->") is None


def test_resolve_region_unknown() -> None:
    assert resolve_region("Varlarmore") is None  # typo


def test_strip_markup() -> None:
    assert strip_markup("[[Dragon Slayer I|Dragon Slayer]]") == "Dragon Slayer"
    assert strip_markup("'''Bold text'''") == "Bold text"
    assert strip_markup("{{SomeTemplate}}") == ""


def test_strip_wiki_links() -> None:
    assert strip_wiki_links("[[Aldarin]]") == "Aldarin"
    assert strip_wiki_links("[[Shilo Village (location)|Shilo Village]]") == "Shilo Village (location)"
    assert strip_wiki_links("Near [[Varrock]] and [[Lumbridge]]") == "Near Varrock and Lumbridge"


def test_extract_template() -> None:
    wikitext = "before {{Infobox Shop|name=Test|location=Here}} after"
    result = extract_template(wikitext, "Infobox Shop")
    assert result == "|name=Test|location=Here"


def test_extract_template_nested() -> None:
    wikitext = "{{Infobox|map={{Map|x=1|y=2}}|name=Test}}"
    result = extract_template(wikitext, "Infobox")
    assert "Map" in result
    assert "name=Test" in result


def test_extract_template_not_found() -> None:
    assert extract_template("no template here", "Missing") is None


def test_extract_section() -> None:
    wikitext = "|rewards = Some rewards here|next_field = value"
    result = extract_section(wikitext, "rewards")
    assert result.strip() == "Some rewards here"


def test_parse_template_param() -> None:
    text = "|name = Test Shop\n|location = Aldarin\n|members = Yes"
    assert parse_template_param(text, "name") == "Test Shop"
    assert parse_template_param(text, "location") == "Aldarin"
    assert parse_template_param(text, "missing") is None


def test_parse_skill_requirements() -> None:
    text = "{{SCP|Mining|40}} and {{SCP|Smithing|50}}"
    reqs = parse_skill_requirements(text)
    assert len(reqs) == 2
    assert (16, 40) in reqs  # Mining = 16
    assert (17, 50) in reqs  # Smithing = 17


def test_parse_skill_requirements_invalid() -> None:
    text = "{{SCP|FakeSkill|50}}"
    assert parse_skill_requirements(text) == []


def test_parse_skill_requirements_out_of_range() -> None:
    text = "{{SCP|Mining|0}} and {{SCP|Mining|100}}"
    assert parse_skill_requirements(text) == []
