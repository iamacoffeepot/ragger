from dataclasses import dataclass


@dataclass
class ExperienceReward:
    id: int
    eligible_skills: int
    amount: int
