### GameVariable (`src/ragger/game_variable.py`)

```python
from ragger.game_variable import GameVariable, ContentTag
from ragger.enums import ContentCategory, FunctionalTag

GameVariable.all(conn, var_type?) -> list[GameVariable]       # var_type: VariableType enum
GameVariable.by_name(conn, name) -> GameVariable | None       # exact name match, first result
GameVariable.all_by_name(conn, name) -> list[GameVariable]    # all vars with exact name
GameVariable.search(conn, name) -> list[GameVariable]         # partial name match (LIKE %name%)
GameVariable.by_var_id(conn, var_id, var_type) -> GameVariable | None
GameVariable.by_content_tag(conn, ContentCategory.QUEST, "dragon_slayer_i") -> list[GameVariable]  # enum + name
GameVariable.by_content_tag(conn, "quest:dragon_slayer_i") -> list[GameVariable]                  # legacy string form
GameVariable.by_content_tag(conn, ContentCategory.QUEST) -> list[GameVariable]                    # all vars in category
GameVariable.by_functional_tag(conn, tag, var_type?) -> list[GameVariable]    # FunctionalTag.TIMER or "timer"
var.name -> str                                     # client name hash (e.g. "COM_STANCE")
var.var_id -> int                                   # numeric ID to pass to varp:get/varc:int
var.var_type -> VariableType                         # VARP, VARBIT, VARC_INT, VARC_STR
var.description -> str | None                       # human-readable description (if annotated)
var.content_tags -> list[ContentTag]                # e.g. [ContentTag(QUEST, "troll_stronghold")]
var.functional_tags -> list[FunctionalTag]          # e.g. [FunctionalTag.PROGRESS]
var.wiki_name -> str | None                         # wiki-documented name (e.g. "DRAGON_SLAYER_I_PROGRESS")
var.wiki_content -> str | None                      # wiki-linked content (e.g. "Dragon Slayer I")
var.var_class -> str | None                         # Enum, Switch, Counter, Bitmap, Other
var.values(conn) -> list[VariableValue]                  # annotated values (e.g. quest stages)

# VariableValue fields
vv.var_type -> str
vv.var_id -> int
vv.value -> int                                     # e.g. 0, 1, 2
vv.label -> str                                     # e.g. "Not started", "Started", "Completed"

# ContentTag fields
tag.category -> ContentCategory                     # QUEST, SKILL, NPC, LOCATION, ITEM, MINIGAME, ACTIVITY
tag.name -> str                                     # e.g. "troll_stronghold"
str(tag) -> "quest:troll_stronghold"
```
