"""Priority scoring + deadline ranking — the deterministic core.

Clean-room Python port of whatfirst's scoring engine, re-implemented from the
formula's documented behaviour. It depends on nothing but the standard library
(math, datetime) and imports nothing from the original app. Two parallel scores
compete; the higher one is what the user sees.

    do_score   = (I * U * R_eff * QW) / 10
    prep_score = (I * U * (10 - R)) / 10 * 0.7 * QW

where:
    U       = max(calendar_urgency, completion_urgency)
    QW      = 1 + 0.6 * (I/10) * exp(-E/1.5)        quick-win boost
    R_floor = clamp((U - 6) / 4 * 10, 0, 10)        urgency's target readiness
    R_eff   = R + max(0, R_floor - R) * READY_LIFT  urgency lifts an unready task
    defer   = U_comp >= 9 and slack < 0.5 and I < 7 flag, not a number

READY_LIFT (< 1) keeps the readiness control live: R_eff stays strictly
increasing in R, so readiness always moves the do-score while urgency can still
drag an unready-but-urgent task up to where it competes. All inputs are coerced
to finite numbers and clamped to their domains (I,R in [1,10], E >= 0.05) so the
displayed score can never be NaN/Infinity.

Urgency is unbounded near zero: a rational decay holds for d > 2 days, then an
inverse-distance term takes over and grows past 10 as the deadline approaches
(saturating at 30 the instant before due). Crossing the deadline hands off
continuously: the overdue branch picks up at 30 and ramps to 40 over five days,
so a task never loses urgency merely by going late.

If task["execute_anyway"] is true, R_eff is forced to max(R, 9), prep_score is
zeroed, and the defer flag is suppressed (the user opted in to risk-on mode).
"""

from __future__ import annotations

import math
from datetime import datetime

# -- Tunable scoring knobs ----------------------------------------------------
# READY_LIFT and PREP_BIAS are both 0.7 by coincidence; they are unrelated and
# may drift apart, so they are named separately rather than sharing a literal.

# How far urgency may close the gap between a task's readiness and the
# urgency-driven target R_floor. Strictly < 1 so a fully unready task is never
# lifted all the way to "ready".
READY_LIFT = 0.7

# Action bias on the prep branch: < 1 so a tie in raw value tilts to "do".
PREP_BIAS = 0.7

# Upper guard on the two score branches. Sits above the formula's natural
# maximum on purpose, so it never clips a real task — only a backstop.
SCORE_CAP = 1000

# Closeness band for the value tier, realized as a transitive log-bucket.
TIE_BAND = 0.10

# Quick-win lens thresholds (a short, ready-to-start task for a spare moment).
QUICK_WIN_MAX_EFFORT_HOURS = 0.25  # 15 minutes
QUICK_WIN_MIN_READINESS = 7


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def finite(x, fallback: float) -> float:
    """Coerce anything non-numeric or non-finite to a known default before it
    enters the formula — one bad field must yield a sane number, never NaN."""
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return fallback
    return xf if math.isfinite(xf) else fallback


def readiness_of(t: dict) -> float:
    """Default readiness is 8 (a task is presumed mostly-ready)."""
    return finite(t.get("readiness"), 8)


# -- Urgency curves -----------------------------------------------------------

def cal_urgency(d: float) -> float:
    if d <= 0:
        return min(40, 30 + (-d) * 2)
    base = 1 + 9 / (1 + (d / 7) ** 1.5)
    T, k, eps = 2, 8, 0.25
    accel = max(0, k / (d + eps) - k / (T + eps)) if d < T else 0
    return min(30, base + accel)


def comp_urgency(d: float, e_hours: float) -> float:
    if d <= 0:
        return min(40, 30 + (-d) * 2)
    e_days = max(e_hours, 0.05) / 4
    slack = d / e_days
    base = 1 + 9 / (1 + slack / 2)
    T, k, eps = 1, 4, 0.1
    accel = max(0, k / (slack + eps) - k / (T + eps)) if slack < T else 0
    return min(30, base + accel)


def urgency(due_date, effort_hours) -> float:
    if not due_date:
        return 2
    d = days_to_due_raw(due_date)
    return max(cal_urgency(d), comp_urgency(d, effort_hours or 0.05))


# -- Core score ---------------------------------------------------------------

def score_components(t: dict) -> dict:
    I = clamp(finite(t.get("impact"), 5), 1, 10)
    R = clamp(readiness_of(t), 1, 10)
    E = max(finite(t.get("effort_hours"), 0.05), 0.05)
    d = days_to_due_raw(t.get("due_date"))
    has_due = bool(t.get("due_date")) and math.isfinite(d)
    U_cal = cal_urgency(d) if has_due else 1.5
    U_comp = comp_urgency(d, E) if has_due else 1.5
    U = max(U_cal, U_comp)
    if has_due and d > 0:
        slack = d / (E / 4)
    elif d <= 0:
        slack = 0.0
    else:
        slack = math.inf
    QW = 1 + 0.6 * (I / 10) * math.exp(-E / 1.5)
    risk_on = bool(t.get("execute_anyway"))
    R_floor = clamp((U - 6) / 4 * 10, 0, 10)
    # Partial lift toward R_floor (not max(R, R_floor)): urgency pulls an unready
    # task up so it still competes, but readiness keeps moving the score.
    R_eff = max(R, 9) if risk_on else R + max(0, R_floor - R) * READY_LIFT
    do_score = clamp((I * U * R_eff * QW) / 10, 0.1, SCORE_CAP)
    prep_score = 0.0 if risk_on else clamp((I * U * (10 - R)) / 10 * PREP_BIAS * QW, 0, SCORE_CAP)
    defer = (not risk_on) and has_due and U_comp >= 9 and slack < 0.5 and I < 7
    display = max(do_score, prep_score)
    prep_wins = prep_score > do_score and R <= 5 and not risk_on
    return {
        "I": I, "R": R, "E": E, "d": d, "U": U, "U_cal": U_cal, "U_comp": U_comp,
        "slack": slack, "qw": QW, "R_floor": R_floor, "R_eff": R_eff,
        "do_score": do_score, "prep_score": prep_score, "defer": defer,
        "display": display, "prep_wins": prep_wins,
    }


def priority(t: dict) -> float:
    return score_components(t)["display"]


def value_bucket(v: float) -> int:
    return math.floor(math.log(max(v, 0.1)) / math.log(1 + TIE_BAND))


# -- Assignment (collapses to "always mine" with no teams) --------------------

def assignee_ids(task: dict) -> list:
    ids = task.get("assignee_user_ids")
    if isinstance(ids, list):
        return ids
    if task.get("assignee_user_id") is not None:
        return [task["assignee_user_id"]]
    return []


def mine_to_do(task: dict, current_user_id=None) -> bool:
    if current_user_id is None:
        return True
    ids = assignee_ids(task)
    return len(ids) == 0 or current_user_id in ids


# -- Dates --------------------------------------------------------------------

def normalize_iso(due_date):
    """A bare date ('YYYY-MM-DD') names a day; treat it as 5pm local so a
    date-only deadline isn't read as midnight. A full datetime passes through."""
    if not isinstance(due_date, str):
        return due_date
    return f"{due_date}T17:00:00" if len(due_date) == 10 else due_date


def _parse(due_date):
    try:
        return datetime.fromisoformat(normalize_iso(due_date))
    except (TypeError, ValueError):
        return None


def days_to_due_raw(due_date, now: datetime | None = None) -> float:
    if not due_date:
        return math.inf
    due = _parse(due_date)
    if due is None:
        return math.inf
    now = now or datetime.now()
    return (due - now).total_seconds() / 86400


def deadline_status(task: dict, now: datetime | None = None):
    """Deadline pressure as a discrete tier, orthogonal to the priority score.
    Returns 'overdue' | 'today' | 'tomorrow' | None."""
    if not task or task.get("completed") or not task.get("due_date"):
        return None
    due = _parse(task["due_date"])
    if due is None:
        return None
    now = now or datetime.now()
    if due < now:
        return "overdue"
    start = lambda d: datetime(d.year, d.month, d.day)
    day_diff = round((start(due) - start(now)).total_seconds() / 86400)
    if day_diff == 0:
        return "today"
    if day_diff == 1:
        return "tomorrow"
    return None


# -- Ranking ------------------------------------------------------------------

def deadline_risk_map(sorted_active: list, now: datetime | None = None, current_user_id=None) -> dict:
    """Cumulative deadline-risk tiers across the ranked active queue.

    Walk the queue in priority order, accumulate effort, and project a
    continuous wall-clock finish for each task. A task whose projected finish
    lands past its own deadline is at risk even if it would have fit alone — the
    work ahead of it ate the runway. Returns {id: 'at-risk' | 'tight'}.
    """
    out = {}
    now = now or datetime.now()
    acc = 0.0  # cumulative effort-hours of the queue so far, inclusive
    for t in sorted_active:
        if not t or t.get("completed"):
            continue
        if not mine_to_do(t, current_user_id):
            continue
        E = max(t.get("effort_hours") or 0, 0)
        acc += E
        if not t.get("due_date"):
            continue
        due = _parse(t["due_date"])
        if due is None:
            continue
        hours_to_due = (due - now).total_seconds() / 3600
        if not (hours_to_due > 0):
            continue  # overdue — skip; deadline_status owns that signal
        slack = hours_to_due - acc
        if slack <= 0:
            out[t["id"]] = "at-risk"
        elif slack < 0.5 * E:
            out[t["id"]] = "tight"
    return out


def rank_active(tasks: list, now: datetime | None = None, current_user_id=None) -> list:
    """Rank the active queue with deadlines as a constraint, not a term folded
    into the value score. Three tiers: 0 overdue (EDF), 1 binding/at-risk (EDF,
    lifted above the value pack), 2 value pack (value bucket, sooner due breaks
    near-ties)."""
    now = now or datetime.now()
    active = [t for t in tasks if not t.get("completed")]
    V = {t["id"]: priority(t) for t in active}
    D = {t["id"]: days_to_due_raw(t.get("due_date"), now) for t in active}
    by_value = sorted(active, key=lambda t: V[t["id"]], reverse=True)
    risk = deadline_risk_map(by_value, now, current_user_id)

    def tier_of(t):
        if not mine_to_do(t, current_user_id):
            return 2
        if t.get("due_date") and D[t["id"]] <= 0:
            return 0
        return 1 if risk.get(t["id"]) == "at-risk" else 2

    def sort_key(t):
        tid = t["id"]
        tr = tier_of(t)
        if tr < 2:
            return (tr, D[tid], 0.0)  # overdue/binding: earliest-deadline-first
        # value pack: higher bucket first, then sooner due breaks near-ties
        return (tr, -value_bucket(V[tid]), D[tid])

    # Python's sort is stable, so equal keys keep by_value (value-desc) order.
    return sorted(by_value, key=sort_key)


# -- Quick-win lens -----------------------------------------------------------

def is_quick_win(task: dict) -> bool:
    """Short enough and ready enough to knock out in a spare moment?"""
    if not task or task.get("completed"):
        return False
    e = task.get("effort_hours")
    if not isinstance(e, (int, float)) or not math.isfinite(e) or e <= 0 or e > QUICK_WIN_MAX_EFFORT_HOURS:
        return False
    return readiness_of(task) >= QUICK_WIN_MIN_READINESS or bool(task.get("execute_anyway"))


def quick_wins(tasks: list) -> list:
    """Quick wins ordered for the spare-moment view: shortest first, ties by
    priority desc."""
    return sorted(
        (t for t in tasks if is_quick_win(t)),
        key=lambda t: (t["effort_hours"], -priority(t)),
    )


# -- Display helpers ----------------------------------------------------------

def format_score(n: float) -> str:
    rounded = round(n * 10) / 10
    return str(int(rounded)) if rounded == int(rounded) else f"{rounded:.1f}"


def due_label(due_date, now: datetime | None = None) -> str:
    """Compact relative deadline label ('now', '3h', 'tomorrow', '2d', '5d late')."""
    if not due_date:
        return "-"
    due = _parse(due_date)
    if due is None:
        return "-"
    now = now or datetime.now()
    raw = (due - now).total_seconds() / 86400
    if raw < 0:
        ab = -raw
        return f"{max(1, round(ab * 24))}h late" if ab < 1 else f"{round(ab)}d late"
    start = lambda d: datetime(d.year, d.month, d.day)
    day_diff = round((start(due) - start(now)).total_seconds() / 86400)
    if day_diff == 0:
        return "now" if raw < 1 / 24 else f"{round(raw * 24)}h"
    if day_diff == 1:
        return "tomorrow"
    return f"{day_diff}d"
