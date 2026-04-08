### DialoguePage (`src/ragger/dialogue.py`)

```python
from ragger.dialogue import DialoguePage

DialoguePage.all(conn, page_type?) -> list[DialoguePage]
DialoguePage.by_title(conn, title) -> DialoguePage | None
DialoguePage.search(conn, title) -> list[DialoguePage]     # partial title match
page.nodes(conn) -> list[DialogueNode]                     # all nodes in order
page.roots(conn) -> list[DialogueNode]                     # top-level nodes only
page.sections(conn) -> list[str]                           # distinct section headings
page.render_tree(conn, section?, node_ids=False) -> str    # indented text rendering
```

### DialogueNode (`src/ragger/dialogue.py`)

```python
from ragger.dialogue import DialogueNode

DialogueNode.by_page(conn, page_id) -> list[DialogueNode]
DialogueNode.by_id(conn, node_id) -> DialogueNode | None
DialogueNode.by_speaker(conn, speaker, page_id?) -> list[DialogueNode]
DialogueNode.search(conn, text, page_id?) -> list[DialogueNode]  # text LIKE search
DialogueNode.by_section(conn, page_id, section) -> list[DialogueNode]
node.children(conn) -> list[DialogueNode]                  # direct children
node.subtree(conn) -> list[DialogueNode]                   # recursive CTE descendants
node.parent(conn) -> DialogueNode | None
node.ancestors(conn) -> list[DialogueNode]                 # root-to-node path
node.tags(conn) -> list[DialogueTag]                       # entity tags on this node
node.requirement_groups(conn) -> list[RequirementGroup]    # extracted requirements
node.page(conn) -> DialoguePage | None
node.render(node_ids=False) -> str                         # single indented line
```

Node types: `line`, `option`, `condition`, `action`, `box`, `select`, `quest_action`

### DialogueTag (`src/ragger/dialogue.py`)

```python
from ragger.dialogue import DialogueTag

DialogueTag.by_node(conn, node_id) -> list[DialogueTag]
DialogueTag.by_entity(conn, entity_type, entity_name) -> list[DialogueTag]
DialogueTag.by_entity_type(conn, entity_type) -> list[DialogueTag]
DialogueTag.search(conn, entity_name) -> list[DialogueTag]  # partial name match
tag.node(conn) -> DialogueNode | None
```

Entity types: `item`, `npc`, `monster`, `quest`, `location`, `shop`, `equipment`, `activity`
