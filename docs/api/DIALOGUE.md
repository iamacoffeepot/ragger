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
6. `sweep_unreachable` — BFS from every entry point in the stream. Entries are the first live instruction, every section change, and every instruction following a terminator (`fallthrough=False`). The post-terminator rule accepts the wiki convention of placing multiple independent top-level branches in the same section (default arms after a SWITCH, alternate "search the X" responses, trailing scripted actions). Marks unreachable control flow dead and raises `UnreachableContentError` defensively if any content op is still unreachable — in practice the rule is permissive enough that this never fires on the live corpus
7. `compact` — remove dead instructions, remap addresses

Each pass is a pure `list[Instruction] -> list[Instruction]` function.
The `compute_dialogue_instructions.py` pipeline script persists the
output to `dialogue_instructions`.

### Condition Parser (`src/ragger/dialogue/condition_parser.py`)

```python
from ragger.dialogue.condition_normalize import (
    build_entity_automaton, build_currency_pattern, normalize,
)
from ragger.dialogue.condition_parser import parse_condition
from ragger.dialogue.condition_types import Atom

auto, type_map = build_entity_automaton(conn)
currency_pat = build_currency_pattern(conn)

text = normalize(raw_condition_text, auto, type_map, currency_pat)
atoms = parse_condition(text)                        # list[Atom]
atoms = parse_condition(text, allow_unknown=True)    # never returns []
```

Parses normalized dialogue condition text into structured `Atom`
predicates. Covers ~66% of the 16.6k condition instances across 56
frame types. Unmatched conditions return `unknown(text=...)` when
`allow_unknown=True`.

An `Atom` has a `frame` name and sorted `args` tuple:

```python
Atom(frame="has_item", args=(("count", 1), ("neg", False), ("qual", "any")))
Atom(frame="quest_state", args=(("neg", False), ("state", "completed")))
Atom(frame="unknown", args=(("text", "if bob is the wizard"),))
```

### Normalization (`src/ragger/dialogue/condition_normalize.py`)

```python
build_entity_automaton(conn) -> (Automaton, dict)  # AC automaton + type_map
build_currency_pattern(conn) -> Pattern | None     # currency regex
normalize(text, auto, type_map, currency_pat?) -> str
strip_subject(text) -> str                         # remove "if the player ..."
strip_fillers(text) -> str                         # remove "still", "already", etc.
split_compound(text) -> list[str]                  # split on "and"/"or"/"but"
```

Normalization order: typed entity links → wiki links → lowercase →
contractions → second-person ("your" → "the player's") → currency
names → Aho-Corasick entity matching → skill names → whitespace cleanup.

### Frame Modules (`src/ragger/dialogue/condition_frames/`)

Each `frames_*.py` exports a `RULES: list[FrameRule]` of plain data.
`condition_frames/__init__.py` assembles them into `ALL_RULES` in
explicit match order — specific frames first, catch-alls last.

| Module | Frames |
|--------|--------|
| `frames_quests.py` | quest_state, quest_decision, diary_completed |
| `frames_skills.py` | skill_ge, combat_level, monster_skill_check |
| `frames_equipment.py` | wearing, wearing_either |
| `frames_items.py` | has_item, has_coins, has_currency, has_all_items, showing_item, has_read, received_reward, reward_is, currency_cap |
| `frames_inventory.py` | inventory_space |
| `frames_farming.py` | patch_state, patch_planted, patch_grown |
| `frames_tasks.py` | has_assignment, port_task, task_progress, has_rumour, all_completed |
| `frames_dialogue.py` | answered, puzzle_answer, puzzle_solved, dialogue_state, has_talked_to, talking_to, npc_role, npc_thought, non_predicate, meta_predicate, time_out |
| `frames_world.py` | location_at, proximity_check, npc_at_location, member_only, account_state, world_type, in_combat, world_state |
| `frames_misc.py` | gender, owns, has_follower, has_chosen, needs_to_build, cast_count |
| `frames_events.py` | event, event_past_tense, outcome, has_event_action (catch-all) |
