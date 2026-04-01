from dataclasses import dataclass


@dataclass
class QuestRequirement:
    id: int
    required_quest_id: int
    partial: bool
