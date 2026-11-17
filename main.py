import os
import sqlite3
import questionary
from datetime import datetime, timedelta, date
from db import (init_db, add_member, add_event, get_events_for, get_member,
                list_members, get_members_on)
from planner import (RULES, plan_shift, make_sleep_blocks, resolve_conflicts,
                     fatigue_score, total_slept, caffeine_cutoff, verdict,
                     auto_target, auto_nights, recovery_suggestions, hours)
from sleep import SleepBlock

habits = {}       # member name -> usual bedtime "HH:MM"
naps = {}         # member name -> [SleepBlock]
recoveries = {}   # member name -> [(night_start, SleepBlock)] accepted recovery sleep
rejected = {}     # member name -> set of night_start times the user said no to


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")
clear_screen()

def pause():
    try:
        questionary.press_any_key_to_continue("Press any key to continue...").ask()
    except Exception:
        input("Press Enter to continue...")


def reset():
    if os.path.exists("ssrs.db"):
        os.remove("ssrs.db")
    init_db()
    habits.clear()
    naps.clear()
    recoveries.clear()
    rejected.clear()


def register(name, bed):
    habits[name] = bed
    naps[name] = []
    recoveries[name] = []
    rejected[name] = set()


# ---------- pickers (each returns None if the user cancels) ----------

def ask_float(prompt):
    def valid(text):
        try:
            float(text)
            return True
        except ValueError:
            return "Enter a number, e.g. 8 or 7.5"
    text = questionary.text(prompt, validate=valid).ask()
    return None if text is None else float(text)


def pick_day(prompt):
    today = date.today()
    choices = []
    for i in range(14):
        d = today + timedelta(days=i)
        label = f"Day {i + 1} - {d:%a %b %d}" + ("  (today)" if i == 0 else "")
        choices.append(questionary.Choice(label, value=d))
    return questionary.select(prompt, choices=choices).ask()


def pick_time(prompt, default="08:00"):
    times = [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 30)]
    try:
        return questionary.select(prompt, choices=times, default=default,
                                  use_search_filter=True, use_jk_keys=False).ask()
    except (TypeError, ValueError):
        return questionary.select(prompt, choices=times, default=default).ask()


def pick_datetime(prompt, default_time="08:00"):
    d = pick_day(f"{prompt}: which day?")
    if d is None:
        return None
    t = pick_time(f"{prompt}: what time?", default_time)
    if t is None:
        return None
    return datetime.combine(d, datetime.strptime(t, "%H:%M").time())


def pick_hours(prompt, options, default=None):
    choices = [questionary.Choice(f"{h:g} hr", value=h) for h in options]
    choices.append(questionary.Choice("Other (type it)", value="other"))
    kwargs = {}
    if default is not None:
        kwargs["default"] = next(c for c in choices if c.value == default)
    pick = questionary.select(prompt, choices=choices, **kwargs).ask()
    if pick is None:
        return None
    if pick == "other":
        return ask_float("Hours:")
    return pick


def ask_member(prompt="Which crew member?"):
    names = list_members()
    if not names:
        print("  No crew yet. Add a member first.")
        return None
    return questionary.select(prompt, choices=names).ask()


# ---------- menu actions ----------

def menu_add_member():
    name = questionary.text("Name:").ask()
    if not name or not name.strip():
        return
    name = name.strip()
    need = pick_hours("Sleep need per night?", [5, 5.5, 6, 6.5, 7, 7.5, 8, 8.5, 9, 9.5, 10], default=8)
    if need is None:
        return
    bed = pick_time("Usual bedtime?", "23:00")
    if bed is None:
        return
    try:
        add_member(name, need)
    except sqlite3.IntegrityError:
        print("  That member already exists.")
        return
    register(name, bed)
    print(f"  Added {name}: needs {need:g} hr, usually sleeps at {bed}.")


def menu_add_event():
    names = list_members()
    if not names:
        print("  Add a member first.")
        return
    title = questionary.text("Event name (e.g. EVA 2):").ask()
    if not title or not title.strip():
        return
    start = pick_datetime("Start", "08:00")
    if start is None:
        return
    dur = pick_hours("How long?", [1, 2, 3, 4, 6, 8, 10, 12])
    if dur is None:
        return
    who = questionary.checkbox("Who is on it? (space to select, enter to confirm)",
                               choices=names).ask()
    if not who:
        print("  Pick at least one person.")
        return
    add_event(title.strip(), start, start + timedelta(hours=dur), who)
    print(f"  Added {title.strip()} for {', '.join(who)}.")


def menu_add_nap():
    name = ask_member()
    if not name:
        return
    start = pick_datetime("Nap start", "14:00")
    if start is None:
        return
    dur = pick_hours("Nap length?", [0.5, 1, 1.5, 2])
    if dur is None:
        return
    naps[name].append(SleepBlock(name, start, start + timedelta(hours=dur), "nap"))
    print("  Nap added.")


def print_plan(name):
    """Print the full plan. Returns the list of recovery suggestions still open."""
    need = get_member(name)
    events = sorted(get_events_for(name), key=lambda e: e.start_time)
    bed = datetime.strptime(habits[name], "%H:%M").time()
    normal = datetime.combine(date.today(), bed)

    target, first = auto_target(normal, need, events)
    nights = auto_nights(normal, events)
    starts = plan_shift(normal, target, nights)
    blocks = make_sleep_blocks(name, starts, need)
    resolved = resolve_conflicts(blocks, events)
    my_naps = resolve_conflicts(naps.get(name, []), events)
    recs = []
    for night_start, r in recoveries.get(name, []):
        for rb in resolve_conflicts([r], events):
            recs.append((night_start, rb))
    score, reasons = fatigue_score(blocks, resolved, need, my_naps, recs)

    print(f"\n=== {name} (sleep need {need:g} hr, usual bedtime {habits[name]}) ===")
    for e in events:
        crew = ", ".join(get_members_on(e.id))
        print(f"OPS: {e.name} {e.start_time:%a %b %d %H:%M} -> {e.end_time:%a %b %d %H:%M}  [{crew}]")
    if first:
        print(f"Auto-plan: shifting sleep toward {target:%H:%M} to be rested for {first.name}")
        shift_needed = abs((target - normal).total_seconds()) / 3600
        nights_before = sum(1 for b in blocks if b.start_time < first.start_time)
        allowed = RULES["max_shift_hours"] * nights_before
        if shift_needed > allowed:
            print(f"WARNING: ideal prep needs a {shift_needed:.0f} hr shift before {first.name}, "
                  f"but the shift cap allows only {allowed:g} hr in time.")
    print()
    for i, b in enumerate(blocks, 1):
        slept = total_slept(b, resolved, my_naps, recs)
        flag = " (SHORT)" if slept < need else ""
        print(f"Night {i}: sleep {b.start_time:%a %b %d %H:%M} -> {b.end_time:%a %H:%M}, {slept:.1f} hr{flag}")
        wind = b.start_time - timedelta(hours=RULES.get("winddown_hours_before_sleep", 2))
        print(f"   asleep by {b.start_time:%H:%M}, wind-down by {wind:%H:%M}, "
              f"no caffeine after {caffeine_cutoff(b):%H:%M}")
    for n in my_naps:
        print(f"Nap: {n.start_time:%a %b %d %H:%M} -> {n.end_time:%H:%M} ({hours(n):.1f} hr)")
    for _, r in recs:
        print(f"Recovery sleep (accepted): {r.start_time:%a %b %d %H:%M} -> {r.end_time:%H:%M} ({hours(r):.1f} hr)")

    suggestions = recovery_suggestions(blocks, resolved, events, need, my_naps, recs,
                                       rejected.get(name, set()))
    for b, s, e, short in suggestions:
        print(f"Suggested recovery: {short:.1f} hr short on {b.start_time:%b %d}. "
              f"Sleep {s:%a %b %d %H:%M} -> {e:%H:%M} after ops")
    print(f"\nFatigue score: {score}/100 ({verdict(score)})")
    for r in reasons:
        print("  ", r)
    print()
    return suggestions


def show_plan(name):
    while True:
        suggestions = print_plan(name)
        if not suggestions:
            return
        changed = False
        for b, s, e, short in suggestions:
            hrs = (e - s).total_seconds() / 3600
            ok = questionary.confirm(
                f"Accept {hrs:.1f} hr recovery sleep {s:%a %b %d %H:%M} -> {e:%H:%M}?",
                default=True).ask()
            if ok is None:          # Ctrl+C
                return
            if ok:
                recoveries[name].append((b.start_time, SleepBlock(name, s, e, "recovery")))
            else:
                rejected[name].add(b.start_time)
            changed = True
        if not changed:
            return
        print("\n--- Updated plan ---")


def menu_show():
    name = ask_member()
    if name:
        show_plan(name)


def menu_show_all():
    names = list_members()
    if not names:
        print("  No crew yet.")
        return
    for n in names:
        show_plan(n)


def load_demo():
    reset()
    for name, need, bed in [("Rose", 8.0, "23:00"), ("Sam", 7.5, "22:30")]:
        add_member(name, need)
        register(name, bed)
    eva_start = datetime.combine(date.today() + timedelta(days=2), datetime.strptime("02:00", "%H:%M").time())
    add_event("EVA 1", eva_start, eva_start + timedelta(hours=8), ["Rose", "Sam"])
    print("  Demo loaded: Rose and Sam, with an EVA on Day 3.")


def menu_reset():
    reset()
    print("  Everything cleared.")


ACTIONS = {
    "Add crew member": menu_add_member,
    "Add event (EVA, etc.)": menu_add_event,
    "Add nap": menu_add_nap,
    "Show plan + fatigue score": menu_show,
    "Show plans for the whole crew": menu_show_all,
    "Load demo scenario": load_demo,
    "Reset everything": menu_reset,
}

reset()
while True:
    clear_screen()
    choice = questionary.select("What now?", choices=list(ACTIONS) + ["Quit"]).ask()
    if choice is None or choice == "Quit":   # None means Ctrl+C
        break
    ACTIONS[choice]()
    pause()