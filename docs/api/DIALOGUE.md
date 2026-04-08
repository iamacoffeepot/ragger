### DialoguePage (`src/ragger/dialogue.py`)

```python
from ragger.dialogue import DialoguePage

DialoguePage.all(conn, page_type?) -> list[DialoguePage]
DialoguePage.by_title(conn, title) -> DialoguePage | None
DialoguePage.search(conn, title) -> list[DialoguePage]     # partial title match
page.nodes(conn) -> list[DialogueNode]                     # all nodes in order
page.roots(conn) -> list[DialogueNode]                     # top-level nodes only
page.sections(conn) -> list[str]                           # distinct section headings
page.render(conn, section?) -> str                    # indented text with node IDs and resolved edges
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
node.edges_out(conn, edge_type?) -> list[DialogueEdge]     # outgoing edges
node.edges_in(conn, edge_type?) -> list[DialogueEdge]      # incoming edges
node.requirement_groups(conn) -> list[RequirementGroup]    # extracted requirements
node.page(conn) -> DialoguePage | None
node.render() -> str                                       # single indented line with node ID prefix
```

Node types: `line`, `option`, `condition`, `action`, `box`, `select`, `quest_action`

### DialogueEdge (`src/ragger/dialogue.py`)

```python
from ragger.dialogue import DialogueEdge

DialogueEdge.from_node(conn, node_id, edge_type?) -> list[DialogueEdge]   # outgoing
DialogueEdge.to_node(conn, node_id, edge_type?) -> list[DialogueEdge]     # incoming
DialogueEdge.by_page(conn, page_id, edge_type?) -> list[DialogueEdge]     # all edges on page
edge.source(conn) -> DialogueNode | None
edge.target(conn) -> DialogueNode | None
```

Edge types: `child`, `next`, `continues`, `same_as`, `cross_page`, `branch`

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
