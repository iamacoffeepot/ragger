from dataclasses import dataclass

from clogger.enums import Skill


@dataclass
class SkillRequirement:
    id: int
    skill: Skill
    level: int
