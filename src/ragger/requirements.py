from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ragger.enums import DiaryLocation, DiaryTier, Region, Skill


@dataclass
class SkillRequirement:
    id: int
    skill: Skill
    level: int


@dataclass
class QuestRequirement:
    id: int
    required_quest_id: int
    partial: bool


@dataclass
class QuestPointRequirement:
    id: int
    points: int


@dataclass
class ItemRequirement:
    id: int
    item_id: int
    quantity: int


@dataclass
class DiaryRequirement:
    id: int
    location: DiaryLocation
    tier: DiaryTier


@dataclass
class RegionRequirement:
    id: int
    regions: int
    any_region: bool

    def region_list(self) -> list[Region]:
        return [r for r in Region if self.regions & r.mask]


# ---------------------------------------------------------------------------
# Generic requirement group system
# ---------------------------------------------------------------------------


@dataclass
class GroupSkillRequirement:
    id: int
    group_id: int
    skill: Skill
    level: int
    boostable: bool


@dataclass
class GroupQuestRequirement:
    id: int
    group_id: int
    required_quest_id: int
    partial: bool


@dataclass
class GroupQuestPointRequirement:
    id: int
    group_id: int
    points: int


@dataclass
class GroupItemRequirement:
    id: int
    group_id: int
    item_id: int
    quantity: int


@dataclass
class GroupDiaryRequirement:
    id: int
    group_id: int
    location: DiaryLocation
    tier: DiaryTier


@dataclass
class GroupRegionRequirement:
    id: int
    group_id: int
    region: Region


@dataclass
class RequirementGroup:
    """A requirement group. All requirements within a group are OR'd (any one
    satisfies the group). Groups linked to an entity are AND'd (all must be
    satisfied)."""

    id: int

    def skill_requirements(self, conn: sqlite3.Connection) -> list[GroupSkillRequirement]:
        rows = conn.execute(
            "SELECT id, group_id, skill, level, boostable FROM group_skill_requirements WHERE group_id = ?",
            (self.id,),
        ).fetchall()
        return [GroupSkillRequirement(r[0], r[1], Skill(r[2]), r[3], bool(r[4])) for r in rows]

    def quest_requirements(self, conn: sqlite3.Connection) -> list[GroupQuestRequirement]:
        rows = conn.execute(
            "SELECT id, group_id, required_quest_id, partial FROM group_quest_requirements WHERE group_id = ?",
            (self.id,),
        ).fetchall()
        return [GroupQuestRequirement(r[0], r[1], r[2], bool(r[3])) for r in rows]

    def quest_point_requirements(self, conn: sqlite3.Connection) -> list[GroupQuestPointRequirement]:
        rows = conn.execute(
            "SELECT id, group_id, points FROM group_quest_point_requirements WHERE group_id = ?",
            (self.id,),
        ).fetchall()
        return [GroupQuestPointRequirement(r[0], r[1], r[2]) for r in rows]

    def item_requirements(self, conn: sqlite3.Connection) -> list[GroupItemRequirement]:
        rows = conn.execute(
            "SELECT id, group_id, item_id, quantity FROM group_item_requirements WHERE group_id = ?",
            (self.id,),
        ).fetchall()
        return [GroupItemRequirement(r[0], r[1], r[2], r[3]) for r in rows]

    def diary_requirements(self, conn: sqlite3.Connection) -> list[GroupDiaryRequirement]:
        rows = conn.execute(
            "SELECT id, group_id, location, tier FROM group_diary_requirements WHERE group_id = ?",
            (self.id,),
        ).fetchall()
        return [GroupDiaryRequirement(r[0], r[1], DiaryLocation(r[2]), DiaryTier(r[3])) for r in rows]

    def region_requirements(self, conn: sqlite3.Connection) -> list[GroupRegionRequirement]:
        rows = conn.execute(
            "SELECT id, group_id, region FROM group_region_requirements WHERE group_id = ?",
            (self.id,),
        ).fetchall()
        return [GroupRegionRequirement(r[0], r[1], Region(r[2])) for r in rows]

    @staticmethod
    def for_quest(conn: sqlite3.Connection, quest_id: int) -> list[RequirementGroup]:
        rows = conn.execute(
            "SELECT group_id FROM quest_requirement_groups WHERE quest_id = ?",
            (quest_id,),
        ).fetchall()
        return [RequirementGroup(r[0]) for r in rows]

    @staticmethod
    def for_league_task(conn: sqlite3.Connection, league_task_id: int) -> list[RequirementGroup]:
        rows = conn.execute(
            "SELECT group_id FROM league_task_requirement_groups WHERE league_task_id = ?",
            (league_task_id,),
        ).fetchall()
        return [RequirementGroup(r[0]) for r in rows]

    @staticmethod
    def for_diary_task(conn: sqlite3.Connection, diary_task_id: int) -> list[RequirementGroup]:
        rows = conn.execute(
            "SELECT group_id FROM diary_task_requirement_groups WHERE diary_task_id = ?",
            (diary_task_id,),
        ).fetchall()
        return [RequirementGroup(r[0]) for r in rows]
