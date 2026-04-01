from dataclasses import dataclass


@dataclass
class Quest:
    id: int
    name: str
    points: int
