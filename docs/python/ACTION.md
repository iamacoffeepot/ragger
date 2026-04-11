### Action (`src/ragger/action.py`)

```python
from ragger.action import Action, ActionTrigger, ActionOutputExperience, ActionInputItem, ActionInputObject, ActionInputCurrency, ActionOutputItem, ActionOutputObject

# Core queries
Action.all(conn) -> list[Action]
Action.by_name(conn, name) -> Action | None            # exact match, first result
Action.all_by_name(conn, name) -> list[Action]         # multiple methods for same output
Action.search(conn, name) -> list[Action]              # partial name match
Action.by_trigger_type(conn, trigger_type) -> list[Action]  # actions with triggers of a given type
Action.by_trigger(conn, trigger_type, target_id, op=None) -> list[Action]  # match a game interaction event

# Producing queries
Action.producing_item(conn, item_name) -> list[Action]
Action.producing_object(conn, object_name) -> list[Action]
Action.producing_experience(conn, skill) -> list[Action]

# Consuming queries
Action.consuming_item(conn, item_name) -> list[Action]
Action.consuming_object(conn, object_name) -> list[Action]
Action.consuming_currency(conn, currency) -> list[Action]

# Output methods
action.output_experience(conn) -> list[ActionOutputExperience]
action.output_items(conn) -> list[ActionOutputItem]
action.output_objects(conn) -> list[ActionOutputObject]

# Input methods
action.input_items(conn) -> list[ActionInputItem]      # consumed items
action.input_objects(conn) -> list[ActionInputObject]   # consumed objects
action.input_currencies(conn) -> list[ActionInputCurrency]  # consumed currencies

# Trigger methods
action.triggers(conn) -> list[ActionTrigger]           # (trigger_type, source_id, target_id, op)

# Requirements (skill levels and tools are stored as requirement groups)
action.requirement_groups(conn) -> list[RequirementGroup]
action.skill_requirements(conn) -> list[GroupSkillRequirement]
action.quest_requirements(conn) -> list[GroupQuestRequirement]

Action.delete_by_source(conn, source) -> list[int]     # delete all actions for a source and dependents

action.name -> str                                     # what the action creates
action.members -> bool
action.ticks -> int | None                             # game ticks per action (NULL for gathering)
action.notes -> str | None                             # quest/other requirements
```

#### ActionTrigger

Each trigger represents a game interaction that activates the action:

- `trigger_type: ActionTriggerType` — the interaction type
- `source_id: int | None` — what the player acts WITH (item ID for USE_ITEM_ON_*, None for CLICK_*)
- `target_id: int` — what they act ON (entity game ID or item ID)
- `op: str` — the menu option (e.g. "Use", "Build", "Mine", "Cast")
