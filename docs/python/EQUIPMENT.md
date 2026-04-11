### Equipment (`src/ragger/equipment.py`)

```python
from ragger.equipment import Equipment

Equipment.all(conn, slot?) -> list[Equipment]
Equipment.by_name(conn, name, version?) -> Equipment | None
Equipment.by_slot(conn, slot) -> list[Equipment]
Equipment.search(conn, name) -> list[Equipment]
Equipment.for_item(conn, item_id) -> list[Equipment]
equipment.requirement_groups(conn) -> list[RequirementGroup]
equipment.skill_requirements(conn) -> list[GroupSkillRequirement]
equipment.quest_requirements(conn) -> list[GroupQuestRequirement]
equipment.slot -> EquipmentSlot | None
equipment.two_handed -> bool                           # True for 2h weapons
equipment.combat_style -> CombatStyle | None
equipment.item_id -> int | None                        # FK to items table
equipment.attack_stab -> int | None
equipment.attack_slash -> int | None
equipment.attack_crush -> int | None
equipment.attack_magic -> int | None
equipment.attack_ranged -> int | None
equipment.defence_stab -> int | None
equipment.defence_slash -> int | None
equipment.defence_crush -> int | None
equipment.defence_magic -> int | None
equipment.defence_ranged -> int | None
equipment.melee_strength -> int | None
equipment.ranged_strength -> int | None
equipment.magic_damage -> int | None
equipment.prayer -> int | None
equipment.speed -> int | None                          # weapon-only
equipment.attack_range -> int | None                   # weapon-only
```
