from dataclasses import dataclass
from datetime import datetime

@dataclass
class SleepBlock:
    member: str
    start_time: datetime
    end_time: datetime
    kind: str   # "sleep" or "nap"
