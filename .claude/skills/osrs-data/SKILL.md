---
name: osrs-data
description: Query the OSRS knowledge base for items, quests, monsters, equipment, locations, shops, spells, skills, and navigation. Use when answering questions about Old School RuneScape game data.
user-invocable: false
allowed-tools: Bash
---

# OSRS Data Query

Query the ragger SQLite database via the Python API. Run queries with:

```bash
uv run python -c "
import sqlite3
conn = sqlite3.connect('data/ragger.db')
from ragger.<module> import <Class>
result = Class.method(conn, ...)
print(result)
"
```

All classmethods take `conn` as the first argument. Instance methods take `self, conn`.

## Modules

### Items (`ragger.item`)
```
Item.by_name(conn, name) -> Item | None
Item.search(conn, name) -> list[Item]          # LIKE %name%
Item.by_game_id(conn, game_id) -> Item | None
item.game_ids(conn) -> list[int]
```
Fields: id, name, members, tradeable, weight, examine

### Quests (`ragger.quest`)
```
Quest.by_name(conn, name) -> Quest | None
Quest.search(conn, name) -> list[Quest]
quest.skill_requirements(conn) -> list[GroupSkillRequirement]  # skill, level, boostable
quest.quest_requirements(conn) -> list[GroupQuestRequirement]  # required_quest_id
quest.xp_rewards(conn) -> list[ExperienceReward]               # eligible_skills (bitmask), amount
quest.item_rewards(conn) -> list[ItemReward]                    # item_id, quantity
quest.requirement_chain(conn) -> list[Quest]                    # all prereqs recursively
quest.requirement_tree(conn) -> str                             # tree visualization
```
Fields: id, name, points

### Monsters (`ragger.monster`)
```
Monster.by_name(conn, name, version=None) -> Monster | None
Monster.search(conn, name) -> list[Monster]
Monster.by_slayer_category(conn, category) -> list[Monster]
monster.drops(conn) -> list[MonsterDrop]           # item_name, quantity, rarity
monster.locations(conn) -> list[MonsterLocation]   # location, x, y, region
monster.skill_requirements(conn) -> list[GroupSkillRequirement]
```
Fields: id, name, version, combat_level, hitpoints, attack_speed, max_hit, attack_style, aggressive, slayer_xp, slayer_category, examine, members, plus full stat block

### Equipment (`ragger.equipment`)
```
Equipment.by_name(conn, name, version=None) -> Equipment | None
Equipment.search(conn, name) -> list[Equipment]
Equipment.by_slot(conn, slot) -> list[Equipment]   # EquipmentSlot enum
Equipment.for_item(conn, item_id) -> list[Equipment]
equip.skill_requirements(conn) -> list[GroupSkillRequirement]
equip.quest_requirements(conn) -> list[GroupQuestRequirement]
```
Fields: id, name, version, item_id, slot, two_handed, attack_stab/slash/crush/magic/ranged, defence_stab/slash/crush/magic/ranged, melee_strength, ranged_strength, magic_damage, prayer, speed, attack_range, combat_style

### NPCs (`ragger.npc`)
```
Npc.by_name(conn, name, version=None) -> Npc | None
Npc.search(conn, name) -> list[Npc]
Npc.with_option(conn, option, region=None) -> list[Npc]  # e.g. "Trade", "Travel"
Npc.at_location(conn, location) -> list[Npc]
npc.locations(conn) -> list[NpcLocation]
NpcLocation.near(conn, x, y, radius=50) -> list[NpcLocation]
```
Fields: id, name, version, location, x, y, options (comma-separated), region

### Locations (`ragger.location`)
```
Location.by_name(conn, name) -> Location | None
Location.search(conn, name) -> list[Location]
Location.nearest(conn, x, y) -> Location | None
Location.with_facilities(conn, facilities, region=None) -> list[Location]  # list of Facility enums
loc.facility_list() -> list[Facility]
loc.shops(conn) -> list[Shop]
loc.adjacencies(conn) -> list[Adjacency]
loc.nearby(conn, max_distance) -> list[tuple[Location, float]]
```
Fields: id, name, region, type, members, x, y, facilities (bitmask)
Facility enum: BANK, FURNACE, ANVIL, ALTAR, SPINNING_WHEEL, LOOM, POTTERY_WHEEL, RANGE, WATER_SOURCE, TANNING

### Shops (`ragger.shop`)
```
Shop.by_name(conn, name) -> Shop | None
Shop.search(conn, name) -> list[Shop]
Shop.selling(conn, item_name, region=None) -> list[Shop]  # "where can I buy X?"
shop.items(conn) -> list[ShopItem]  # item_name, stock, restock, sell_price, buy_price
```
Fields: id, name, location, owner, members, region, shop_type, sell_multiplier, buy_multiplier

### Spells (`ragger.spell`)
```
CombatSpell.by_name(conn, name) -> CombatSpell | None
CombatSpell.search(conn, name) -> list[CombatSpell]
CombatSpell.by_element(conn, element) -> list[CombatSpell]  # AIR, WATER, EARTH, FIRE
CombatSpell.at_level(conn, level) -> list[CombatSpell]      # all spells <= level

UtilitySpell.by_name(conn, name) -> UtilitySpell | None
UtilitySpell.search(conn, name) -> list[UtilitySpell]

TeleportSpell.by_name(conn, name) -> TeleportSpell | None
TeleportSpell.search(conn, name) -> list[TeleportSpell]

spell.runes(conn) -> list[SpellRune]  # item_name, quantity
```
Spellbook enum: NORMAL, ANCIENT, LUNAR

### Actions (`ragger.action`) — skilling/crafting
```
Action.by_name(conn, name) -> Action | None
Action.search(conn, name) -> list[Action]
Action.producing_item(conn, item_name) -> list[Action]       # "how do I make X?"
Action.consuming_item(conn, item_name) -> list[Action]       # "what uses X?"
Action.producing_experience(conn, skill) -> list[Action]     # "how to train X?" (Skill enum)
action.input_items(conn) -> list[ActionInputItem]             # item_name, quantity
action.output_items(conn) -> list[ActionOutputItem]           # item_name, quantity
action.output_experience(conn) -> list[ActionOutputExperience] # skill, xp
action.skill_requirements(conn) -> list[GroupSkillRequirement]
```
Fields: id, name, members, ticks, notes

### Activities (`ragger.activity`) — minigames
```
Activity.by_name(conn, name) -> Activity | None
Activity.search(conn, name) -> list[Activity]
Activity.for_skill(conn, skill) -> list[Activity]  # Skill enum
```

### Ground Items (`ragger.ground_item`)
```
GroundItem.by_item_name(conn, name) -> list[GroundItem]  # permanent spawns
GroundItem.search(conn, name) -> list[GroundItem]
GroundItem.near(conn, x, y, radius=50) -> list[GroundItem]
```

### Facilities (`ragger.facility`)
```
FacilityEntry.nearest(conn, x, y, facility_type=None) -> FacilityEntry | None
```

### Navigation (`ragger.map`)
```
from ragger.map import find_path, MapLink
find_path(conn, src, dst, allowed_types=None) -> list[MapLink] | None  # A* shortest path
MapLink.departing(conn, location) -> list[MapLink]  # travel options from a location
```
MapLinkType enum: WALKABLE, ENTRANCE, EXIT, FAIRY_RING, CHARTER_SHIP, TELEPORT, SPIRIT_TREE, GNOME_GLIDER, CANOE, MINECART, SHIP, QUETZAL, NPC_TRANSPORT

### Diary Tasks (`ragger.diary`)
```
DiaryTask.all(conn, location=None, tier=None) -> list[DiaryTask]
```
DiaryLocation enum: ARDOUGNE, DESERT, FALADOR, FREMENNIK, KANDARIN, KARAMJA, KOUREND_AND_KEBOS, LUMBRIDGE_AND_DRAYNOR, MORYTANIA, VARROCK, WESTERN_PROVINCES, WILDERNESS
DiaryTier enum: EASY, MEDIUM, HARD, ELITE

## Enums (`ragger.enums`)

Skill: ATTACK, STRENGTH, DEFENCE, RANGED, PRAYER, MAGIC, RUNECRAFT, CONSTRUCTION, HITPOINTS, AGILITY, HERBLORE, THIEVING, CRAFTING, FLETCHING, SLAYER, HUNTER, MINING, SMITHING, FISHING, COOKING, FIREMAKING, WOODCUTTING, FARMING, SAILING

Region: GENERAL, ASGARNIA, DESERT, FREMENNIK, KANDARIN, KARAMJA, KOUREND, MISTHALIN, MORYTANIA, TIRANNWN, WILDERNESS

EquipmentSlot: HEAD, CAPE, NECK, AMMO, WEAPON, BODY, SHIELD, LEGS, HANDS, FEET, RING, TWO_HANDED

## Patterns

Lookup then detail:
```python
quest = Quest.by_name(conn, "Dragon Slayer I")
reqs = quest.skill_requirements(conn)
rewards = quest.xp_rewards(conn)
```

Find where to buy something:
```python
shops = Shop.selling(conn, "Rune scimitar")
for s in shops: print(f"{s.name} in {s.location}")
```

How to make something:
```python
actions = Action.producing_item(conn, "Gold necklace")
for a in actions:
    print(a.name, a.input_items(conn), a.output_experience(conn))
```

Navigate between locations:
```python
from ragger.map import find_path
path = find_path(conn, "Lumbridge", "Falador")
for link in path:
    print(f"{link.src_location} -> {link.dst_location} ({link.link_type.value})")
```
