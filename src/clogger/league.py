from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import yaml

from clogger.enums import Region, Skill, TaskDifficulty
from clogger.experience import level_for_xp, xp_for_level
from clogger.quest import Quest
from clogger.requirements import DiaryRequirement, ItemRequirement, QuestRequirement, RegionRequirement, SkillRequirement


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
            JOIN league_task_skill_requirements ltsr ON ltsr.league_task_id = lt.id
            JOIN skill_requirements sr ON sr.id = ltsr.skill_requirement_id
            WHERE sr.skill = ?
        """
        params: list[int] = [skill.value]

        if difficulty is not None:
            query += " AND lt.difficulty = ?"
            params.append(difficulty.value)
        if region is not None:
            query += " AND lt.region = ?"
            params.append(region.value)

        query += " ORDER BY sr.level, lt.difficulty"
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
    def _from_row(cls, row: tuple) -> LeagueTask:
        return cls(
            id=row[0],
            name=row[1],
            description=row[2],
            difficulty=TaskDifficulty(row[3]),
            region=Region(row[4]),
        )

    def skill_requirements(self, conn: sqlite3.Connection) -> list[SkillRequirement]:
        rows = conn.execute(
            """
            SELECT sr.id, sr.skill, sr.level
            FROM skill_requirements sr
            JOIN league_task_skill_requirements ltsr ON ltsr.skill_requirement_id = sr.id
            WHERE ltsr.league_task_id = ?
            ORDER BY sr.level DESC
            """,
            (self.id,),
        ).fetchall()
        return [SkillRequirement(row[0], row[1], row[2]) for row in rows]

    def quest_requirements(self, conn: sqlite3.Connection) -> list[QuestRequirement]:
        rows = conn.execute(
            """
            SELECT qr.id, qr.required_quest_id, qr.partial
            FROM quest_requirements qr
            JOIN league_task_quest_requirements ltqr ON ltqr.quest_requirement_id = qr.id
            WHERE ltqr.league_task_id = ?
            """,
            (self.id,),
        ).fetchall()
        return [QuestRequirement(row[0], row[1], bool(row[2])) for row in rows]

    def item_requirements(self, conn: sqlite3.Connection) -> list[ItemRequirement]:
        rows = conn.execute(
            """
            SELECT ir.id, ir.item_id, ir.quantity
            FROM item_requirements ir
            JOIN league_task_item_requirements ltir ON ltir.item_requirement_id = ir.id
            WHERE ltir.league_task_id = ?
            """,
            (self.id,),
        ).fetchall()
        return [ItemRequirement(*row) for row in rows]

    def diary_requirements(self, conn: sqlite3.Connection) -> list[DiaryRequirement]:
        rows = conn.execute(
            """
            SELECT dr.id, dr.location, dr.tier
            FROM diary_requirements dr
            JOIN league_task_diary_requirements ltdr ON ltdr.diary_requirement_id = dr.id
            WHERE ltdr.league_task_id = ?
            """,
            (self.id,),
        ).fetchall()
        return [DiaryRequirement(row[0], row[1], row[2]) for row in rows]

    def region_requirements(self, conn: sqlite3.Connection) -> list[RegionRequirement]:
        rows = conn.execute(
            """
            SELECT rr.id, rr.regions, rr.any_region
            FROM region_requirements rr
            JOIN league_task_region_requirements ltrr ON ltrr.region_requirement_id = rr.id
            WHERE ltrr.league_task_id = ?
            """,
            (self.id,),
        ).fetchall()
        return [RegionRequirement(row[0], row[1], bool(row[2])) for row in rows]


@dataclass
class LeagueConfig:
    starting_region: Region
    starting_location: str
    always_accessible: list[Region]
    unlockable_regions: list[Region]
    max_region_unlocks: int
    starting_skills: dict[Skill, int]
    autocompleted_quests: list[str]

    @staticmethod
    def from_yaml(path: Path) -> LeagueConfig:
        with open(path) as f:
            data = yaml.safe_load(f)

        starting_skills: dict[Skill, int] = {}
        for skill_name, level in data.get("starting_skills", {}).items():
            starting_skills[Skill.from_label(skill_name)] = level

        return LeagueConfig(
            starting_region=Region.from_label(data["starting_region"]),
            starting_location=data.get("starting_location", ""),
            always_accessible=[Region.from_label(r) for r in data["always_accessible"]],
            unlockable_regions=[Region.from_label(r) for r in data["unlockable_regions"]],
            max_region_unlocks=data["max_region_unlocks"],
            starting_skills=starting_skills,
            autocompleted_quests=data["autocompleted_quests"],
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

    def _meets_region_reqs(self, reqs: list[RegionRequirement]) -> bool:
        for rr in reqs:
            regions = rr.region_list()
            if rr.any_region:
                if not any(self.has_region(r) for r in regions):
                    return False
            else:
                if not all(self.has_region(r) for r in regions):
                    return False
        return True

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
                if any(not self.has_skill(Skill(r.skill), r.level) for r in reqs):
                    continue

            if check_regions:
                region_reqs = quest.region_requirements(self.conn)
                if not self._meets_region_reqs(region_reqs):
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
                if any(not self.has_skill(Skill(r.skill), r.level) for r in reqs):
                    continue

            if check_regions:
                region_reqs = task.region_requirements(self.conn)
                if not self._meets_region_reqs(region_reqs):
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
            f"SELECT id, name, description, difficulty, region FROM league_tasks WHERE id IN ({placeholders}) ORDER BY id",
            list(self.completed_task_ids),
        ).fetchall()
        return [LeagueTask._from_row(row) for row in rows]
