### RequirementGroup (`src/ragger/requirements.py`)

Shared requirement system used by Quest, Equipment, DiaryTask, LeagueTask, Monster, and DialogueNode. Groups linked to an entity are AND'd (all must be satisfied). Requirements within a group are OR'd (any one satisfies the group).

```python
from ragger.requirements import RequirementGroup

group.skill_requirements(conn) -> list[GroupSkillRequirement]
group.quest_requirements(conn) -> list[GroupQuestRequirement]
group.quest_point_requirements(conn) -> list[GroupQuestPointRequirement]
group.item_requirements(conn) -> list[GroupItemRequirement]
group.diary_requirements(conn) -> list[GroupDiaryRequirement]
group.region_requirements(conn) -> list[GroupRegionRequirement]
group.equipment_requirements(conn) -> list[GroupEquipmentRequirement]

RequirementGroup.for_quest(conn, quest_id) -> list[RequirementGroup]
RequirementGroup.for_equipment(conn, equipment_id) -> list[RequirementGroup]
RequirementGroup.for_monster(conn, monster_id) -> list[RequirementGroup]
RequirementGroup.for_action(conn, action_id) -> list[RequirementGroup]
RequirementGroup.for_diary_task(conn, diary_task_id) -> list[RequirementGroup]
RequirementGroup.for_league_task(conn, league_task_id) -> list[RequirementGroup]
RequirementGroup.for_dialogue_node(conn, node_id) -> list[RequirementGroup]
```
