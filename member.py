from dataclasses import dataclass
from event import Event

@dataclass
class Member:
    name: str
    min_sleep: float
    fatigue_score: int


    

    