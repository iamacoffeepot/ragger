### Quest (`src/ragger/quest.py`)

```python
from ragger.quest import Quest

Quest.all(conn) -> list[Quest]
Quest.by_name(conn, name) -> Quest | None
Quest.search(conn, name) -> list[Quest]           # partial name match
quest.xp_rewards(conn) -> list[ExperienceReward]
quest.item_rewards(conn) -> list[ItemReward]
quest.requirement_groups(conn) -> list[RequirementGroup]
quest.skill_requirements(conn) -> list[GroupSkillRequirement]
quest.quest_requirements(conn) -> list[GroupQuestRequirement]
quest.quest_point_requirement(conn) -> GroupQuestPointRequirement | None
quest.region_requirements(conn) -> list[GroupRegionRequirement]
quest.requirement_chain(conn) -> list[Quest]       # flat list, bottom-up order
quest.requirement_tree(conn) -> str                 # indented tree string
quest.game_vars(conn) -> list[GameVariable]             # associated game variables
```
