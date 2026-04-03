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
