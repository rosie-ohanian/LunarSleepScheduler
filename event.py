from dataclasses import dataclass
from datetime import datetime

@dataclass
class Event:
    id: int
    name: str
    start_time: datetime
    end_time: datetime

