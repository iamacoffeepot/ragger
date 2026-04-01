from dataclasses import dataclass

from clogger.enums import Skill


@dataclass
class ExperienceReward:
    id: int
    skill: Skill
    amount: int
