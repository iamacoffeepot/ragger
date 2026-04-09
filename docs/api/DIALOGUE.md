### DialoguePage (`src/ragger/dialogue/dialogue_page.py`)

```python
from ragger.dialogue import DialoguePage

DialoguePage.all(conn, page_type?) -> list[DialoguePage]
DialoguePage.by_title(conn, title) -> DialoguePage | None
DialoguePage.search(conn, title) -> list[DialoguePage]     # partial title match
page.nodes(conn) -> list[DialogueNode]                     # all nodes in order
page.roots(conn) -> list[DialogueNode]                     # top-level nodes only
page.sections(conn) -> list[str]                           # distinct section headings
page.render(conn, section?) -> str                         # indented text with node IDs and resolved continue targets
page.instructions(conn) -> list[Instruction]               # flattened instruction stream
```

### DialogueNode (`src/ragger/dialogue/dialogue_node.py`)

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
node.continue_target(conn) -> DialogueNode | None          # resolved ACTION target ({{tact|above}} etc.)
node.tags(conn) -> list[DialogueTag]                       # entity tags on this node
node.requirement_groups(conn) -> list[RequirementGroup]    # extracted requirements
node.page(conn) -> DialoguePage | None
node.render() -> str                                       # single indented line with node ID prefix
```

Node types: `line`, `option`, `condition`, `action`, `box`, `select`, `quest_action`.

Action nodes whose text is `end` have `continue_target_id = None`. Action
nodes whose text is a reference (`above`, `below`, `other`, `continues`,
`initial`, `previous`, etc.) have the resolved target node in
`continue_target_id`, populated by `fetch_dialogues.py` at parse time.

### DialogueTag (`src/ragger/dialogue/dialogue_tag.py`)

```python
from ragger.dialogue import DialogueTag

DialogueTag.by_node(conn, node_id) -> list[DialogueTag]
DialogueTag.by_entity(conn, entity_type, entity_name) -> list[DialogueTag]
DialogueTag.by_entity_type(conn, entity_type) -> list[DialogueTag]
DialogueTag.search(conn, entity_name) -> list[DialogueTag]  # partial name match
tag.node(conn) -> DialogueNode | None
```

Entity types: `item`, `npc`, `monster`, `quest`, `location`, `shop`, `equipment`, `activity`.

### Instruction (`src/ragger/dialogue/dialogue_instruction.py`)

```python
from ragger.dialogue import Instruction

Instruction.for_page(conn, page_id) -> list[Instruction]            # whole page, ordered by addr
Instruction.by_section(conn, page_id, section) -> list[Instruction] # one section, ordered by addr
Instruction.delete_for_page(conn, page_id) -> None
Instruction.save_all_for_page(conn, page_id, instructions) -> None  # replaces existing rows
```

An `Instruction` is one line of a per-page flattened instruction stream.
Addresses (`addr`) are global within a page. Sections are a column, not
a partition — cross-section references are regular local addresses.

Fields: `page_id`, `addr`, `section`, `op`, `text`, `speaker`,
`fallthrough`, `targets`, `target_labels`, `target_predicates`.

Ops emitted after the pipeline runs:

| op | meaning |
|---|---|
| `SPEAK` | dialogue line with a speaker |
| `BOX` | narration / game message (no speaker) |
| `QUEST` | quest cutscene / scripted action |
| `MENU` | player-visible choice menu; labels in `target_labels`, visibility gates in `target_predicates`, optional title in `text` |
| `SELECT` | in-game selection prompt not adjacent to a MENU (residual after folding) |
| `SWITCH` | engine-side branch over conditions; labels in `target_labels` |
| `JUMP_IF` | single condition check that skips forward to `targets[0]` on false |
| `JUMP` | unconditional resolved branch; target in `targets[0]` |
| `GOTO` | unresolved branch (the parser couldn't resolve the reference); no targets |
| `COND` | inline NOTE-style annotation (rare) |
| `END` | terminal; end of a branch |

### Pipeline (`src/ragger/dialogue/dialogue_flatten.py`, `dialogue_passes.py`)

```python
from ragger.dialogue.dialogue_flatten import flatten
from ragger.dialogue.dialogue_passes import PASSES

page = DialoguePage.by_title(conn, "Cook's Assistant")
instructions = flatten(conn, page)
for p in PASSES:
    instructions = p(instructions)
```

`flatten(conn, page)` produces the raw per-page instruction stream from
the node tree. Option groups become `MENU`s, condition groups become
`SWITCH`/`JUMP_IF`, predicate CONDs are folded onto MENU options. Action
nodes with a resolved `continue_target_id` become `GOTO` with resolved
targets.

`PASSES` is the canonical cleanup pipeline:

1. `lower_gotos` — resolved GOTOs become JUMPs
2. `thread_jumps` — follow JUMP trampolines and labeled MENU chains
3. `collapse_trivial_branches` — drop branches whose arms converge: SWITCHes with all-equal targets, JUMP_IFs with empty or no-op predicates, and JUMPs to the next live addr
4. `inline_player_echoes` — kill `SPEAK Player + JUMP -> MENU` echo trampolines
5. `fold_select_menu` — lift SELECT text onto the immediately-following MENU as a title
6. `sweep_unreachable` — BFS from each section's first live addr; drop unreachable control flow (`JUMP`, `GOTO`, `END`, `COND`, `PRED`); raise `UnreachableContentError` if any unreachable content op (`SPEAK`, `BOX`, `QUEST`, `MENU`, `SELECT`, `SWITCH`, `JUMP_IF`) is found, since those signal a flatten bug or duplicated wiki transcript
7. `compact` — remove dead instructions, remap addresses

Each pass is a pure `list[Instruction] -> list[Instruction]` function.
The `compute_dialogue_instructions.py` pipeline script persists the
output to `dialogue_instructions`.
