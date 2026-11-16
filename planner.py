from datetime import datetime, timedelta

def overlaps(event1, event2):
    return not (event1.end_time <= event2.start_time or event2.end_time <= event1.start_time)

MAX_SHIFT_HOURS = 1

def plan_shift(current_start, target_start, nights):
    """Return a list of sleep start times, one per night, moving toward the target."""
    step = timedelta(hours=MAX_SHIFT_HOURS)
    schedule = []
    for night in range(nights):
        gap = target_start - current_start        # + means target is later, - means earlier
        if gap > timedelta(0):
            move = min(gap, step)                 # go later, never past the target
        else:
            move = max(gap, -step)                # go earlier, never past the target
        current_start += move
        schedule.append(current_start)
    return schedule

def caffeine_cutoff(sleep_block, rules):
    return sleep_block.start_time - timedelta(hours=rules["caffeine_cutoff_hours_before_sleep"])