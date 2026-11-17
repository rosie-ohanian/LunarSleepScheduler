from datetime import timedelta
from sleep import SleepBlock
import json

def load_rules(path="rules.json"):
    with open(path) as f:
        return json.load(f)

RULES = load_rules()

def overlaps(event1, event2):
    return not (event1.end_time <= event2.start_time or event2.end_time <= event1.start_time)


def plan_shift(current_start, target_start, nights):
    """Return a list of sleep start times, one per night, moving toward the target."""
    step = timedelta(hours=RULES["max_shift_hours"])
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

def caffeine_cutoff(sleep_block):
    return sleep_block.start_time - timedelta(hours=RULES["caffeine_cutoff_hours_before_sleep"])

def make_sleep_blocks(member, start_times, sleep_need_hours):
    blocks = []
    for night, start in enumerate(start_times):
        start = start + timedelta(days=night)
        end = start + timedelta(hours=sleep_need_hours)
        blocks.append(SleepBlock(member, start, end, "sleep"))
    return blocks

def free_windows(day_start, day_end, events):
    """Return (start, end) gaps between events within [day_start, day_end]."""
    windows = []
    cursor = day_start
    for e in sorted(events, key=lambda e: e.start_time):
        if e.end_time <= cursor or e.start_time >= day_end:
            continue
        if e.start_time > cursor:
            windows.append((cursor, e.start_time))
        cursor = max(cursor, e.end_time)
    if cursor < day_end:
        windows.append((cursor, day_end))
    return windows

def hours(block):
    return (block.end_time - block.start_time).total_seconds() / 3600

def sleep_for_night(original, resolved):
    """Hours actually slept inside one original block after trimming."""
    return sum(hours(r) for r in resolved
               if r.start_time >= original.start_time and r.end_time <= original.end_time)

def fatigue_score(originals, resolved, need):
    score, reasons = 100, []
    weight = RULES["fatigue_penalty_per_hour_short"]
    for b in originals:
        short = max(0, need - sleep_for_night(b, resolved))
        if short > 0:
            penalty = round(short * weight)
            score -= penalty
            reasons.append(f"-{penalty}: {short:.1f} hr under sleep need ({b.start_time:%b %d})")
    return max(score, 0), reasons

def resolve_conflicts(blocks, events):
    """Operations win: trim sleep blocks around events. Drops blocks left empty."""
    result = []
    for block in blocks:
        start, end = block.start_time, block.end_time
        for event in events:
            if event.end_time <= start or event.start_time >= end:
                continue                          # no overlap with the (trimmed) block
            if event.start_time <= start and event.end_time >= end:
                start = end                       # event covers everything: no sleep
                break
            elif event.start_time <= start:
                start = event.end_time            # event covers the beginning
            elif event.end_time >= end:
                end = event.start_time            # event covers the end
            else:
                # event sits in the middle: keep the longer side
                if event.start_time - start >= end - event.end_time:
                    end = event.start_time
                else:
                    start = event.end_time
        if end > start:
            result.append(SleepBlock(block.member, start, end, block.kind))
    return result

def verdict(score):
    if score >= RULES["score_ok"]:
        return "ACCEPTABLE"
    if score >= RULES["score_warn"]:
        return "CAUTION"
    return "UNACCEPTABLE"

def auto_target(normal_start, need, events):
    """Pick the sleep start to shift toward, based on the next upcoming event.
    Returns (target_start, that_event). Placeholder logic, pending biomedical review."""
    upcoming = [e for e in events if e.start_time > normal_start]
    if not upcoming:
        return normal_start, None
    first = min(upcoming, key=lambda e: e.start_time)
    buffer = timedelta(hours=RULES.get("pre_event_buffer_hours", 2))
    ideal = first.start_time - buffer - timedelta(hours=need)
    shift_hr = ((ideal - normal_start).total_seconds() / 3600) % 24
    if shift_hr > 12:
        shift_hr -= 24                      # take the shorter way around the clock
    return normal_start + timedelta(hours=shift_hr), first

def auto_nights(normal_start, events):
    """Plan through the last event, plus one recovery night."""
    upcoming = [e for e in events if e.start_time > normal_start]
    if not upcoming:
        return 3
    last = max(upcoming, key=lambda e: e.end_time)
    return max(3, (last.end_time.date() - normal_start.date()).days + 2)

def total_slept(original, resolved, naps=(), recoveries=()):
    nap_hrs = sum(hours(n) for n in naps
                  if timedelta(0) <= original.start_time - n.end_time <= timedelta(hours=24))
    rec_hrs = sum(hours(r) for night_start, r in recoveries
                  if night_start == original.start_time)
    return sleep_for_night(original, resolved) + nap_hrs + rec_hrs


def fatigue_score(originals, resolved, need, naps=(), recoveries=()):
    score, reasons = 100, []
    weight = RULES["fatigue_penalty_per_hour_short"]
    for b in originals:
        short = max(0, need - total_slept(b, resolved, naps, recoveries))
        if short > 0:
            penalty = round(short * weight)
            score -= penalty
            reasons.append(f"-{penalty}: {short:.1f} hr under sleep need ({b.start_time:%b %d})")
    return max(score, 0), reasons


def recovery_suggestions(blocks, resolved, events, need, naps=(), recoveries=(), rejected=()):
    """For each short night, find the first free window after it. Returns suggestions only."""
    out = []
    min_len = timedelta(hours=RULES.get("min_sleep_block_hours", 1))
    busy = list(events) + list(naps) + [r for _, r in recoveries] + list(blocks)
    for b in blocks:
        if b.start_time in rejected:
            continue
        short = need - total_slept(b, resolved, naps, recoveries)
        if short <= 0.25:
            continue
        for s, e in free_windows(b.end_time, b.end_time + timedelta(hours=24), busy):
            if e - s >= min_len:
                out.append((b, s, s + min(timedelta(hours=short), e - s), short))
                break
    return out