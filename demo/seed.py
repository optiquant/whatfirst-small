"""Deterministic stand-in for the model's output, so the demo captures genuine
whatfirst-small UI pixels without a running llama.cpp server.

The brain-dump shown on screen is the app's own SAMPLE_DUMP (app.SAMPLE_DUMP);
these are the structured tasks a good parse of it would yield. Scores are hand-
picked to exercise every signal the engine shows off: a looming deadline, a
multi-hour high-impact deliverable, two 15-minute quick wins, and two valuable-
but-not-ready tasks that the prep branch lifts. Due dates are relative to *now*
so the ranking is live every time the capture runs.

Everything here is invented — no real names, clients, or details.
"""

from __future__ import annotations

from datetime import datetime, timedelta


def _date(days: int) -> str:
    d = datetime.now() + timedelta(days=days)
    return f"{d.year:04d}-{d.month:02d}-{d.day:02d}"


def _days_until_weekday(target_weekday: int, *, at_least: int = 1) -> int:
    """Days from today to the next given weekday (Mon=0 … Sun=6)."""
    today = datetime.now().weekday()
    delta = (target_weekday - today) % 7
    return delta if delta >= at_least else delta + 7


def build_tasks() -> list[dict]:
    friday = _days_until_weekday(4)          # next Friday
    next_wed = _days_until_weekday(2) + 7     # Wednesday of next week
    return [
        {
            "title": "Email the landlord about the lease renewal",
            "category": "Admin",
            "notes": "Confirm the renewal terms before the window closes.",
            "due_date": _date(friday),
            "impact": 6, "readiness": 9, "effort_hours": 0.3,
            "reason": "Due Friday; quick and ready to send.",
            "completed": False,
        },
        {
            "title": "Finish the Q3 board deck",
            "category": "Work",
            "notes": "Roughly four hours; needs the runway slide and three asks.",
            "due_date": _date(next_wed),
            "impact": 9, "readiness": 7, "effort_hours": 4.0,
            "reason": "High-impact and multi-hour — start it early.",
            "completed": False,
        },
        {
            "title": "Cancel the unused gym membership",
            "category": "Personal",
            "notes": "Five minutes online.",
            "due_date": None,
            "impact": 3, "readiness": 10, "effort_hours": 0.08,
            "reason": "Five-minute quick win.",
            "completed": False,
        },
        {
            "title": "Switch the team to the new CI",
            "category": "Work",
            "notes": "No rush, and not sure where to start.",
            "due_date": None,
            "impact": 6, "readiness": 3, "effort_hours": 3.0,
            "reason": "Valuable but unscoped — de-risk it before diving in.",
            "completed": False,
        },
        {
            "title": "Book the dentist",
            "category": "Personal",
            "notes": "Overdue checkup.",
            "due_date": _date(1),
            "impact": 5, "readiness": 8, "effort_hours": 0.3,
            "reason": "Due tomorrow; quick call.",
            "completed": False,
        },
        {
            "title": "Reply to Sam's thread",
            "category": "Work",
            "notes": "A one-liner he's waiting on.",
            "due_date": None,
            "impact": 4, "readiness": 9, "effort_hours": 0.1,
            "reason": "Quick reply — clear it.",
            "completed": False,
        },
        {
            "title": "Draft the hiring plan",
            "category": "Work",
            "notes": "Important, but blocked until we agree on budget.",
            "due_date": None,
            "impact": 8, "readiness": 2, "effort_hours": 2.0,
            "reason": "Important but blocked — prep it before it's ready.",
            "completed": False,
        },
    ]


# Canned single-task re-suggestion for the "Re-suggest with AI" button.
SCORE_SUGGEST = {
    "impact": 9,
    "readiness": 8,
    "effort_hours": 0.3,
    "reason": "Near-term and mostly ready; nudged up.",
}
