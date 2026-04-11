from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ragger.enums import ComparisonOperator, DiaryLocation, DiaryTier, Region, Skill, TaskDifficulty
from ragger.experience import level_for_xp, xp_for_level
from ragger.quest import Quest
from ragger.requirements import (
    GroupDiaryRequirement,
    GroupItemRequirement,
    GroupQuestRequirement,
    GroupRegionRequirement,
    GroupSkillRequirement,
    RequirementGroup,
)


@dataclass
class LeagueTask:
    id: int
    name: str
    description: str
    difficulty: TaskDifficulty
    region: Region

    @property
    def points(self) -> int:
        return self.difficulty.points

    @classmethod
    def all(
        cls,
        conn: sqlite3.Connection,
        difficulty: TaskDifficulty | None = None,
        region: Region = None,
    ) -> list[LeagueTask]:
        query = "SELECT id, name, description, difficulty, region FROM league_tasks"
        params: list[int] = []
        conditions: list[str] = []

        if difficulty is not None:
            conditions.append("difficulty = ?")
            params.append(difficulty.value)
        if region is not None:
            conditions.append("region = ?")
            params.append(region.value)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY id"

        rows = conn.execute(query, params).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def by_skill(
        cls,
        conn: sqlite3.Connection,
        skill: Skill,
        difficulty: TaskDifficulty | None = None,
        region: Region | None = None,
    ) -> list[LeagueTask]:
        query = """
            SELECT DISTINCT lt.id, lt.name, lt.description, lt.difficulty, lt.region
            FROM league_tasks lt
            JOIN league_task_requirement_groups ltrg ON ltrg.league_task_id = lt.id
            JOIN group_skill_requirements gsr ON gsr.group_id = ltrg.group_id
            WHERE gsr.skill = ?
        """
        params: list[int] = [skill.value]

        if difficulty is not None:
            query += " AND lt.difficulty = ?"
            params.append(difficulty.value)
        if region is not None:
            query += " AND lt.region = ?"
            params.append(region.value)

        query += " ORDER BY gsr.level, lt.difficulty"
        rows = conn.execute(query, params).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def by_name(cls, conn: sqlite3.Connection, name: str) -> LeagueTask | None:
        row = conn.execute(
            "SELECT id, name, description, difficulty, region FROM league_tasks WHERE name = ?",
            (name,),
        ).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    def search(cls, conn: sqlite3.Connection, name: str) -> list[LeagueTask]:
        rows = conn.execute(
            "SELECT id, name, description, difficulty, region FROM league_tasks WHERE name LIKE ? ORDER BY name",
            (f"%{name}%",),
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def _from_row(cls, row: tuple) -> LeagueTask:
        return cls(
            id=row[0],
            name=row[1],
            description=row[2],
            difficulty=TaskDifficulty(row[3]),
            region=Region(row[4]),
        )

    def requirement_groups(self, conn: sqlite3.Connection) -> list[RequirementGroup]:
        return RequirementGroup.for_league_task(conn, self.id)

    def skill_requirements(self, conn: sqlite3.Connection) -> list[GroupSkillRequirement]:
        rows = conn.execute(
            """
            SELECT gsr.id, gsr.group_id, gsr.skill, gsr.level, gsr.boostable, gsr.operator
            FROM group_skill_requirements gsr
            JOIN league_task_requirement_groups ltrg ON ltrg.group_id = gsr.group_id
            WHERE ltrg.league_task_id = ?
            ORDER BY gsr.level DESC
            """,
            (self.id,),
        ).fetchall()
        return [
            GroupSkillRequirement(r[0], r[1], Skill(r[2]), r[3], bool(r[4]), ComparisonOperator(r[5]))
            for r in rows
        ]

    def quest_requirements(self, conn: sqlite3.Connection) -> list[GroupQuestRequirement]:
        rows = conn.execute(
            """
            SELECT gqr.id, gqr.group_id, gqr.required_quest_id, gqr.partial
            FROM group_quest_requirements gqr
            JOIN league_task_requirement_groups ltrg ON ltrg.group_id = gqr.group_id
            WHERE ltrg.league_task_id = ?
            """,
            (self.id,),
        ).fetchall()
        return [GroupQuestRequirement(r[0], r[1], r[2], bool(r[3])) for r in rows]

    def item_requirements(self, conn: sqlite3.Connection) -> list[GroupItemRequirement]:
        rows = conn.execute(
            """
            SELECT gir.id, gir.group_id, gir.item_id, gir.quantity, gir.operator
            FROM group_item_requirements gir
            JOIN league_task_requirement_groups ltrg ON ltrg.group_id = gir.group_id
            WHERE ltrg.league_task_id = ?
            """,
            (self.id,),
        ).fetchall()
        return [GroupItemRequirement(r[0], r[1], r[2], r[3], ComparisonOperator(r[4])) for r in rows]

    def diary_requirements(self, conn: sqlite3.Connection) -> list[GroupDiaryRequirement]:
        rows = conn.execute(
            """
            SELECT gdr.id, gdr.group_id, gdr.location, gdr.tier
            FROM group_diary_requirements gdr
            JOIN league_task_requirement_groups ltrg ON ltrg.group_id = gdr.group_id
            WHERE ltrg.league_task_id = ?
            """,
            (self.id,),
        ).fetchall()
        return [GroupDiaryRequirement(r[0], r[1], DiaryLocation(r[2]), DiaryTier(r[3])) for r in rows]

    def region_requirements(self, conn: sqlite3.Connection) -> list[GroupRegionRequirement]:
        rows = conn.execute(
            """
            SELECT grr.id, grr.group_id, grr.region
            FROM group_region_requirements grr
            JOIN league_task_requirement_groups ltrg ON ltrg.group_id = grr.group_id
            WHERE ltrg.league_task_id = ?
            """,
            (self.id,),
        ).fetchall()
        return [GroupRegionRequirement(r[0], r[1], Region(r[2])) for r in rows]


@dataclass
class RelicChoice:
    name: str
    description: str


@dataclass
class RelicTier:
    tier: int
    choices: list[RelicChoice]


@dataclass
class LeagueConfig:
    starting_region: Region
    starting_location: str
    always_accessible: list[Region]
    unlockable_regions: list[Region]
    max_region_unlocks: int
    starting_skills: dict[Skill, int]
    autocompleted_quests: list[str]
    relic_thresholds: list[int] = field(default_factory=list)
    xp_multipliers: list[int] = field(default_factory=list)
    drop_multipliers: list[int] = field(default_factory=list)
    minigame_multipliers: list[int] = field(default_factory=list)
    relics: list[RelicTier] = field(default_factory=list)

    @staticmethod
    def from_yaml(path: Path) -> LeagueConfig:
        with open(path) as f:
            data = yaml.safe_load(f)

        starting_skills: dict[Skill, int] = {}
        for skill_name, level in data.get("starting-skills", {}).items():
            starting_skills[Skill.from_label(skill_name)] = level

        def _parse_tier_list(raw: dict | list | None) -> list[int]:
            if raw is None:
                return []
            if isinstance(raw, list):
                return raw
            return [raw[k] for k in sorted(raw)]

        relics: list[RelicTier] = []
        raw_relics = data.get("relics")
        if raw_relics:
            for tier_num in sorted(raw_relics):
                tier_data = raw_relics[tier_num]
                choices = [
                    RelicChoice(name=c["name"], description=c["description"].strip())
                    for c in tier_data["choices"]
                ]
                relics.append(RelicTier(tier=tier_num, choices=choices))

        return LeagueConfig(
            starting_region=Region.from_label(data["starting-region"]),
            starting_location=data.get("starting-location", ""),
            always_accessible=[Region.from_label(r) for r in data["always-accessible"]],
            unlockable_regions=[Region.from_label(r) for r in data["unlockable-regions"]],
            max_region_unlocks=data["max-region-unlocks"],
            starting_skills=starting_skills,
            autocompleted_quests=data["autocompleted-quests"],
            relic_thresholds=_parse_tier_list(data.get("relic-thresholds")),
            xp_multipliers=_parse_tier_list(data.get("xp-multipliers")),
            drop_multipliers=_parse_tier_list(data.get("drop-multipliers")),
            minigame_multipliers=_parse_tier_list(data.get("minigame-multipliers")),
            relics=relics,
        )

    def completed_quests(self, conn: sqlite3.Connection, resolve_chains: bool = True) -> list[Quest]:
        completed: list[Quest] = []
        for name in self.autocompleted_quests:
            quest = Quest.by_name(conn, name)
            if quest is None:
                continue
            completed.append(quest)
            if resolve_chains:
                completed.extend(quest.requirement_chain(conn))
        # Deduplicate preserving order
        seen: set[int] = set()
        unique: list[Quest] = []
        for q in completed:
            if q.id not in seen:
                seen.add(q.id)
                unique.append(q)
        return unique

    def starting_quest_points(self, conn: sqlite3.Connection) -> int:
        return sum(q.points for q in self.completed_quests(conn))

    def available_regions(self, unlocked: list[Region] | None = None) -> list[Region]:
        regions = list(self.always_accessible)
        if unlocked:
            for r in unlocked:
                if r in self.unlockable_regions and r not in regions:
                    regions.append(r)
        return regions


class Account:
    def __init__(self, config: LeagueConfig, conn: sqlite3.Connection) -> None:
        self.config = config
        self.conn = conn
        self.xp: dict[Skill, int] = {s: xp_for_level(1) for s in Skill}
        self.xp[Skill.HITPOINTS] = xp_for_level(10)
        for skill, level in config.starting_skills.items():
            self.xp[skill] = xp_for_level(level)
        self.completed_quest_ids: set[int] = set()
        self.completed_task_ids: set[int] = set()
        self.unlocked_regions: list[Region] = list(config.always_accessible)
        self.current_location: str = config.starting_location

        # Apply autocompleted quests
        for quest in config.completed_quests(conn):
            self.completed_quest_ids.add(quest.id)

    @property
    def quest_points(self) -> int:
        total = 0
        for qid in self.completed_quest_ids:
            row = self.conn.execute("SELECT points FROM quests WHERE id = ?", (qid,)).fetchone()
            if row:
                total += row[0]
        return total

    @property
    def league_points(self) -> int:
        total = 0
        for tid in self.completed_task_ids:
            row = self.conn.execute("SELECT difficulty FROM league_tasks WHERE id = ?", (tid,)).fetchone()
            if row:
                total += TaskDifficulty(row[0]).points
        return total

    @property
    def regions(self) -> list[Region]:
        return list(self.unlocked_regions)

    @property
    def relic_tier(self) -> int:
        """Current relic tier based on league points earned."""
        tier = 0
        for i, threshold in enumerate(self.config.relic_thresholds):
            if self.league_points >= threshold:
                tier = i + 1
        return tier

    @property
    def xp_multiplier(self) -> int:
        """Active XP multiplier for the current relic tier."""
        tier = self.relic_tier
        if tier == 0 or not self.config.xp_multipliers:
            return 1
        return self.config.xp_multipliers[min(tier - 1, len(self.config.xp_multipliers) - 1)]

    @property
    def drop_multiplier(self) -> int:
        """Active drop rate multiplier for the current relic tier."""
        tier = self.relic_tier
        if tier == 0 or not self.config.drop_multipliers:
            return 1
        return self.config.drop_multipliers[min(tier - 1, len(self.config.drop_multipliers) - 1)]

    @property
    def minigame_multiplier(self) -> int:
        """Active minigame point multiplier for the current relic tier."""
        tier = self.relic_tier
        if tier == 0 or not self.config.minigame_multipliers:
            return 1
        return self.config.minigame_multipliers[min(tier - 1, len(self.config.minigame_multipliers) - 1)]

    def complete_quest(
        self,
        quest: Quest,
        xp_choices: dict[int, Skill] | None = None,
    ) -> bool:
        if quest.id in self.completed_quest_ids:
            return False
        self.completed_quest_ids.add(quest.id)
        for prereq in quest.requirement_chain(self.conn):
            self.completed_quest_ids.add(prereq.id)

        # Apply XP rewards
        choices = xp_choices or {}
        for reward in quest.xp_rewards(self.conn):
            bits = bin(reward.eligible_skills).count("1")
            if bits == 1:
                # Fixed reward — find the single skill
                for skill in Skill:
                    if reward.eligible_skills & skill.mask:
                        self.add_xp(skill, reward.amount)
                        break
            else:
                # Choice reward — must be specified
                skill = choices.get(reward.id)
                if skill is None:
                    raise ValueError(
                        f"XP reward {reward.id} ({reward.amount} XP) requires a skill choice"
                    )
                if not (reward.eligible_skills & skill.mask):
                    raise ValueError(
                        f"Skill {skill.label} is not eligible for reward {reward.id}"
                    )
                self.add_xp(skill, reward.amount)

        return True

    def complete_task(self, task: LeagueTask) -> bool:
        if task.id in self.completed_task_ids:
            return False
        self.completed_task_ids.add(task.id)
        return True

    def unlock_region(self, region: Region) -> bool:
        if region in self.unlocked_regions:
            return False
        if region not in self.config.unlockable_regions:
            return False
        if len(self.unlocked_regions) - len(self.config.always_accessible) >= self.config.max_region_unlocks:
            return False
        self.unlocked_regions.append(region)
        return True

    def add_xp(self, skill: Skill, amount: int) -> None:
        self.xp[skill] = self.xp.get(skill, 0) + amount

    def set_skill(self, skill: Skill, level: int) -> None:
        self.xp[skill] = xp_for_level(level)

    def get_level(self, skill: Skill) -> int:
        return level_for_xp(self.xp.get(skill, 0))

    def get_xp(self, skill: Skill) -> int:
        return self.xp.get(skill, 0)

    def has_quest(self, quest: Quest) -> bool:
        return quest.id in self.completed_quest_ids

    def has_skill(self, skill: Skill, level: int) -> bool:
        return self.get_level(skill) >= level

    def has_region(self, region: Region) -> bool:
        return region in self.unlocked_regions or region == Region.GENERAL

    def available_quests(
        self,
        check_skills: bool = True,
        check_regions: bool = True,
        check_quests: bool = True,
    ) -> list[Quest]:
        quests = Quest.all(self.conn)
        result: list[Quest] = []
        for quest in quests:
            if quest.id in self.completed_quest_ids:
                continue

            if check_skills:
                reqs = quest.skill_requirements(self.conn)
                if any(not self.has_skill(r.skill, r.level) for r in reqs):
                    continue

            if check_regions:
                region_reqs = quest.region_requirements(self.conn)
                if any(not self.has_region(r.region) for r in region_reqs):
                    continue

            if check_quests:
                quest_reqs = quest.quest_requirements(self.conn)
                if any(r.required_quest_id not in self.completed_quest_ids for r in quest_reqs):
                    continue

            result.append(quest)
        return result

    def available_tasks(
        self,
        check_skills: bool = True,
        check_regions: bool = True,
        check_quests: bool = True,
    ) -> list[LeagueTask]:
        tasks = LeagueTask.all(self.conn)
        result: list[LeagueTask] = []
        for task in tasks:
            if task.id in self.completed_task_ids:
                continue

            if check_regions and not self.has_region(task.region):
                continue

            if check_skills:
                reqs = task.skill_requirements(self.conn)
                if any(not self.has_skill(r.skill, r.level) for r in reqs):
                    continue

            if check_regions:
                region_reqs = task.region_requirements(self.conn)
                if any(not self.has_region(r.region) for r in region_reqs):
                    continue

            if check_quests:
                quest_reqs = task.quest_requirements(self.conn)
                if any(r.required_quest_id not in self.completed_quest_ids for r in quest_reqs):
                    continue

            result.append(task)
        return result

    def completed_quests(self) -> list[Quest]:
        if not self.completed_quest_ids:
            return []
        placeholders = ",".join("?" * len(self.completed_quest_ids))
        rows = self.conn.execute(
            f"SELECT id, name, points FROM quests WHERE id IN ({placeholders}) ORDER BY name",
            list(self.completed_quest_ids),
        ).fetchall()
        return [Quest(*row) for row in rows]

    def completed_tasks(self) -> list[LeagueTask]:
        if not self.completed_task_ids:
            return []
        placeholders = ",".join("?" * len(self.completed_task_ids))
        rows = self.conn.execute(
            f"SELECT id, name, description, difficulty, region"
            f" FROM league_tasks WHERE id IN ({placeholders}) ORDER BY id",
            list(self.completed_task_ids),
        ).fetchall()
        return [LeagueTask._from_row(row) for row in rows]
