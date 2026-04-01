from dataclasses import dataclass

from clogger.enums import DiaryLocation, DiaryTier


@dataclass
class DiaryTask:
    id: int
    location: DiaryLocation
    tier: DiaryTier
    description: str
