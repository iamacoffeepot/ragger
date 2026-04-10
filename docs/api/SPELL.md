### Spells (`src/ragger/spell.py`)

Three separate dataclasses by spell type. All share `runes(conn) -> list[SpellRune]`.

```python
from ragger.spell import CombatSpell, UtilitySpell, TeleportSpell
from ragger.enums import Element, Spellbook

# Combat spells (element, max_damage)
CombatSpell.all(conn, spellbook?) -> list[CombatSpell]
CombatSpell.by_name(conn, name) -> CombatSpell | None
CombatSpell.by_element(conn, element) -> list[CombatSpell]
CombatSpell.at_level(conn, level) -> list[CombatSpell]    # all spells <= level
spell.runes(conn) -> list[SpellRune]
spell.element -> Element | None
spell.max_damage -> int | None

# Utility spells
UtilitySpell.all(conn, spellbook?) -> list[UtilitySpell]
UtilitySpell.by_name(conn, name) -> UtilitySpell | None
UtilitySpell.at_level(conn, level) -> list[UtilitySpell]
spell.runes(conn) -> list[SpellRune]

# Teleport spells (destination, coordinates, lectern)
TeleportSpell.all(conn, spellbook?) -> list[TeleportSpell]
TeleportSpell.by_name(conn, name) -> TeleportSpell | None
TeleportSpell.at_level(conn, level) -> list[TeleportSpell]
spell.runes(conn) -> list[SpellRune]
spell.destination -> str | None
spell.dst_x -> int | None
spell.dst_y -> int | None
spell.lectern -> str | None

# Shared fields (all types)
spell.name -> str
spell.members -> bool
spell.level -> int
spell.spellbook -> Spellbook                               # normal, ancient, lunar, arceuus
spell.experience -> float
spell.speed -> int | None                                  # ticks
spell.cooldown -> int | None                               # ticks (combat/utility only)
spell.description -> str | None

# SpellRune
rune.item_id -> int                                        # FK to items
rune.item_name -> str
rune.quantity -> int
```
