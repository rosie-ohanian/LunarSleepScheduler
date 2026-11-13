from datetime import datetime
import sqlite3
from event import Event

DB_PATH = "ssrs.db"

def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            sleep_need_hours REAL NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS event_members (
            event_id INTEGER NOT NULL REFERENCES events(id),
            member_id INTEGER NOT NULL REFERENCES members(id),
            PRIMARY KEY (event_id, member_id)
        )
    """)
    conn.commit()
    conn.close()

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def add_event(name, start_time, end_time, member_names):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO events (name, start_time, end_time) VALUES (?, ?, ?)",
        (name, start_time.isoformat(), end_time.isoformat()),
    )
    event_id = cur.lastrowid   # the id SQLite just gave this event

    for member_name in member_names:
        row = conn.execute(
            "SELECT id FROM members WHERE name = ?", (member_name,)
        ).fetchone()
        conn.execute(
            "INSERT INTO event_members (event_id, member_id) VALUES (?, ?)",
            (event_id, row[0]),
        )

    conn.commit()   # one commit at the end: all saved, or none
    conn.close()

def add_member(name, sleep_need_hours):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO members (name, sleep_need_hours) VALUES (?, ?)",
        (name, sleep_need_hours),
    )
    conn.commit()
    conn.close()


def get_events_for(member_name):
    conn = get_conn()
    rows = conn.execute("""
        SELECT events.id, events.name, events.start_time, events.end_time
        FROM events
        JOIN event_members ON event_members.event_id = events.id
        JOIN members ON members.id = event_members.member_id
        WHERE members.name = ?
    """, (member_name,)).fetchall()
    conn.close()

    events = []
    for row in rows:
        # row[0] is the name, row[1] is the start string, row[2] is the end string
        events.append(Event(row[0], row[1], datetime.fromisoformat(row[2]), datetime.fromisoformat(row[3])))
    return events

def get_members_on(event_id):
    conn = get_conn()
    rows = conn.execute("""
        SELECT members.name
        FROM members
        JOIN event_members ON event_members.member_id = members.id
        WHERE event_members.event_id = ?
    """, (event_id,)).fetchall()
    conn.close()
    return [row[0] for row in rows]