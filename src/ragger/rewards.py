from dataclasses import dataclass


@dataclass
class ExperienceReward:
    id: int
    eligible_skills: int
    amount: int


@dataclass
class ItemReward:
    id: int
    item_id: int
    quantity: int
