from datetime import datetime, timedelta

def overlaps(event1, event2):
    return not (event1.end_time <= event2.start_time or event2.end_time <= event1.start_time)

MAX_SHIFT_HOURS = 1

def plan_shift(current_start, target_start, nights):
    """Return a list of sleep start times, one per night, moving toward the target."""
    schedule = []
    for night in range(nights):
        remaining = current_start - target_start            # how far is start from target_start?
        move = min(remaining, timedelta(hours=MAX_SHIFT_HOURS))  if remaining >= 0 else max(remaining, timedelta(hours=MAX_SHIFT_HOURS))                # the smaller of the step and the remaining distance
        current_start+=move               # move start toward the target
        schedule.append(current_start)
    return schedule