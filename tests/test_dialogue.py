import sqlite3

from ragger.dialogue import DialogueNode, DialoguePage, DialogueTag


def _seed_dialogue(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT INTO dialogue_pages (id, title, page_type) VALUES (1, 'Hans', 'npc')")
    conn.execute("INSERT INTO dialogue_pages (id, title, page_type) VALUES (2, 'Cook''s Assistant', 'quest')")

    # Hans dialogue tree:
    # (1) Hans: Hello. What are you doing here?          depth=1, no parent
    #   (2) option: I'm looking for whoever is in charge  depth=2, parent=1
    #     (3) Player: I'm looking for whoever is in charge depth=3, parent=2
    #     (4) Hans: Who, the Duke? First floor.           depth=3, parent=2
    #     (5) action: end                                 depth=3, parent=2
    #   (6) option: I have come to kill everyone!         depth=2, parent=1
    #     (7) Player: I have come to kill everyone!       depth=3, parent=6
    #     (8) action: end                                 depth=3, parent=6
    conn.executemany(
        """INSERT INTO dialogue_nodes
           (id, page_id, parent_id, sort_order, depth, node_type, speaker, text, section)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (1, 1, None, 0, 1, "line", "Hans", "Hello. What are you doing here?", "Standard dialogue"),
            (2, 1, 1, 1, 2, "option", None, "I'm looking for whoever is in charge of this place.", "Standard dialogue"),
            (3, 1, 2, 2, 3, "line", "Player", "I'm looking for whoever is in charge of this place.", "Standard dialogue"),
            (4, 1, 2, 3, 3, "line", "Hans", "Who, the Duke? He's in his study, on the first floor.", "Standard dialogue"),
            (5, 1, 2, 4, 3, "action", None, "end", "Standard dialogue"),
            (6, 1, 1, 5, 2, "option", None, "I have come to kill everyone in this castle!", "Standard dialogue"),
            (7, 1, 6, 6, 3, "line", "Player", "I have come to kill everyone in this castle!", "Standard dialogue"),
            (8, 1, 6, 7, 3, "action", None, "end", "Standard dialogue"),
            # Cook's Assistant - single node for cross-page tests
            (9, 2, None, 0, 1, "line", "Cook", "What am I to do?", "Starting off"),
        ],
    )

    conn.executemany(
        "INSERT INTO dialogue_tags (id, node_id, entity_type, entity_name, entity_id) VALUES (?, ?, ?, ?, ?)",
        [
            (1, 4, "npc", "Duke Horacio", 42),
            (2, 9, "quest", "Cook's Assistant", 10),
        ],
    )
    conn.commit()


def test_page_by_title(conn: sqlite3.Connection) -> None:
    _seed_dialogue(conn)
    page = DialoguePage.by_title(conn, "Hans")
    assert page is not None
    assert page.page_type == "npc"


def test_page_by_title_missing(conn: sqlite3.Connection) -> None:
    _seed_dialogue(conn)
    assert DialoguePage.by_title(conn, "Nonexistent") is None


def test_page_all(conn: sqlite3.Connection) -> None:
    _seed_dialogue(conn)
    pages = DialoguePage.all(conn)
    assert len(pages) == 2


def test_page_all_filter_type(conn: sqlite3.Connection) -> None:
    _seed_dialogue(conn)
    pages = DialoguePage.all(conn, page_type="quest")
    assert len(pages) == 1
    assert pages[0].title == "Cook's Assistant"


def test_page_search(conn: sqlite3.Connection) -> None:
    _seed_dialogue(conn)
    pages = DialoguePage.search(conn, "Han")
    assert len(pages) == 1
    assert pages[0].title == "Hans"


def test_page_nodes(conn: sqlite3.Connection) -> None:
    _seed_dialogue(conn)
    page = DialoguePage.by_title(conn, "Hans")
    nodes = page.nodes(conn)
    assert len(nodes) == 8


def test_page_roots(conn: sqlite3.Connection) -> None:
    _seed_dialogue(conn)
    page = DialoguePage.by_title(conn, "Hans")
    roots = page.roots(conn)
    assert len(roots) == 1
    assert roots[0].speaker == "Hans"


def test_page_sections(conn: sqlite3.Connection) -> None:
    _seed_dialogue(conn)
    page = DialoguePage.by_title(conn, "Hans")
    sections = page.sections(conn)
    assert sections == ["Standard dialogue"]


def test_node_by_id(conn: sqlite3.Connection) -> None:
    _seed_dialogue(conn)
    node = DialogueNode.by_id(conn, 1)
    assert node is not None
    assert node.speaker == "Hans"
    assert node.text == "Hello. What are you doing here?"


def test_node_children(conn: sqlite3.Connection) -> None:
    _seed_dialogue(conn)
    root = DialogueNode.by_id(conn, 1)
    children = root.children(conn)
    assert len(children) == 2
    assert all(c.node_type == "option" for c in children)


def test_node_subtree(conn: sqlite3.Connection) -> None:
    _seed_dialogue(conn)
    option = DialogueNode.by_id(conn, 2)
    subtree = option.subtree(conn)
    assert len(subtree) == 4  # option + 3 children
    assert subtree[0].id == 2


def test_node_parent(conn: sqlite3.Connection) -> None:
    _seed_dialogue(conn)
    child = DialogueNode.by_id(conn, 3)
    parent = child.parent(conn)
    assert parent is not None
    assert parent.id == 2
    assert parent.node_type == "option"


def test_node_ancestors(conn: sqlite3.Connection) -> None:
    _seed_dialogue(conn)
    leaf = DialogueNode.by_id(conn, 4)
    ancestors = leaf.ancestors(conn)
    assert len(ancestors) == 2
    assert ancestors[0].id == 1  # root
    assert ancestors[1].id == 2  # option


def test_node_parent_of_root(conn: sqlite3.Connection) -> None:
    _seed_dialogue(conn)
    root = DialogueNode.by_id(conn, 1)
    assert root.parent(conn) is None


def test_node_by_speaker(conn: sqlite3.Connection) -> None:
    _seed_dialogue(conn)
    nodes = DialogueNode.by_speaker(conn, "Hans")
    assert len(nodes) == 2  # greeting + duke response


def test_node_by_speaker_scoped(conn: sqlite3.Connection) -> None:
    _seed_dialogue(conn)
    nodes = DialogueNode.by_speaker(conn, "Hans", page_id=1)
    assert len(nodes) == 2


def test_node_search(conn: sqlite3.Connection) -> None:
    _seed_dialogue(conn)
    nodes = DialogueNode.search(conn, "Duke")
    assert len(nodes) == 1
    assert nodes[0].speaker == "Hans"


def test_node_search_scoped(conn: sqlite3.Connection) -> None:
    _seed_dialogue(conn)
    nodes = DialogueNode.search(conn, "kill", page_id=1)
    assert len(nodes) == 2  # option + player line


def test_node_by_section(conn: sqlite3.Connection) -> None:
    _seed_dialogue(conn)
    nodes = DialogueNode.by_section(conn, 1, "Standard dialogue")
    assert len(nodes) == 8


def test_node_page(conn: sqlite3.Connection) -> None:
    _seed_dialogue(conn)
    node = DialogueNode.by_id(conn, 1)
    page = node.page(conn)
    assert page is not None
    assert page.title == "Hans"


def test_node_tags(conn: sqlite3.Connection) -> None:
    _seed_dialogue(conn)
    node = DialogueNode.by_id(conn, 4)
    tags = node.tags(conn)
    assert len(tags) == 1
    assert tags[0].entity_type == "npc"
    assert tags[0].entity_name == "Duke Horacio"


def test_tag_by_entity(conn: sqlite3.Connection) -> None:
    _seed_dialogue(conn)
    tags = DialogueTag.by_entity(conn, "npc", "Duke Horacio")
    assert len(tags) == 1
    assert tags[0].node_id == 4


def test_tag_by_entity_type(conn: sqlite3.Connection) -> None:
    _seed_dialogue(conn)
    tags = DialogueTag.by_entity_type(conn, "quest")
    assert len(tags) == 1
    assert tags[0].entity_name == "Cook's Assistant"


def test_tag_search(conn: sqlite3.Connection) -> None:
    _seed_dialogue(conn)
    tags = DialogueTag.search(conn, "Duke")
    assert len(tags) == 1


def test_tag_node(conn: sqlite3.Connection) -> None:
    _seed_dialogue(conn)
    tag = DialogueTag.by_entity(conn, "npc", "Duke Horacio")[0]
    node = tag.node(conn)
    assert node is not None
    assert node.speaker == "Hans"
    assert "Duke" in node.text


def test_node_render_line(conn: sqlite3.Connection) -> None:
    _seed_dialogue(conn)
    node = DialogueNode.by_id(conn, 1)
    assert node.render() == "000001: Hans: Hello. What are you doing here?"


def test_node_render_option(conn: sqlite3.Connection) -> None:
    _seed_dialogue(conn)
    node = DialogueNode.by_id(conn, 2)
    assert node.render() == "000002:   [I'm looking for whoever is in charge of this place.]"


def test_node_render_action(conn: sqlite3.Connection) -> None:
    _seed_dialogue(conn)
    node = DialogueNode.by_id(conn, 5)
    assert node.render() == "000005:     -> end"


def test_page_render(conn: sqlite3.Connection) -> None:
    _seed_dialogue(conn)
    page = DialoguePage.by_title(conn, "Hans")
    tree = page.render(conn)
    lines = tree.split("\n")
    assert lines[0] == "== Standard dialogue =="
    assert "Hans: Hello. What are you doing here?" in lines[1]
    assert any("[I'm looking for whoever is in charge of this place.]" in l for l in lines)
    assert any("-> end" in l for l in lines)


def test_page_render_section_filter(conn: sqlite3.Connection) -> None:
    _seed_dialogue(conn)
    page = DialoguePage.by_title(conn, "Hans")
    tree = page.render(conn, section="Standard dialogue")
    assert "Hans: Hello" in tree
    # Section header not shown when filtering to a single section
    assert "== Standard dialogue ==" not in tree
