### Monster (`src/ragger/monster.py`)

```python
from ragger.monster import Monster, MonsterLocation, MonsterDrop

Monster.all(conn, region?) -> list[Monster]
Monster.by_name(conn, name, version?) -> Monster | None
Monster.by_slayer_category(conn, category) -> list[Monster]
Monster.search(conn, name) -> list[Monster]            # partial name match
monster.locations(conn) -> list[MonsterLocation]
monster.drops(conn) -> list[MonsterDrop]
monster.drops_by_name(conn, item_name) -> list[MonsterDrop]
monster.has_immunity(immunity) -> bool
monster.immunity_list() -> list[Immunity]
monster.requirement_groups(conn) -> list[RequirementGroup]
monster.skill_requirements(conn) -> list[GroupSkillRequirement]
monster.quest_requirements(conn) -> list[GroupQuestRequirement]
monster.game_vars(conn) -> list[GameVariable]           # associated game variables
monster.combat_level -> int | None
monster.hitpoints -> int | None
monster.immunities -> int                              # bitmask
monster.slayer_category -> str | None
monster.elemental_weakness_type -> str | None
monster.elemental_weakness_percent -> int | None
monster.attack_level -> int | None
monster.strength_level -> int | None
monster.defence_level -> int | None
monster.magic_level -> int | None
monster.ranged_level -> int | None
monster.attack_bonus -> int | None
monster.strength_bonus -> int | None
monster.magic_attack -> int | None
monster.magic_strength -> int | None
monster.ranged_attack -> int | None
monster.ranged_strength -> int | None
monster.defensive_stab -> int | None
monster.defensive_slash -> int | None
monster.defensive_crush -> int | None
monster.defensive_magic -> int | None
monster.defensive_light_ranged -> int | None
monster.defensive_standard_ranged -> int | None
monster.defensive_heavy_ranged -> int | None
monster.attack_speed -> int | None
monster.max_hit -> str | None
monster.attack_style -> str | None
monster.aggressive -> bool | None
monster.size -> int | None
monster.respawn -> int | None
monster.slayer_xp -> float | None
monster.slayer_assigned_by -> str | None
monster.attributes -> str | None
monster.examine -> str | None
monster.members -> bool | None
```
