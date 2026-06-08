"""Priority scoring + deadline ranking — the deterministic core.

Two scores compete; the higher one is displayed:

    do_score   = (I * U * R_eff * QW) / 10
    prep_score = (I * U * (10 - R)) / 10 * 0.7 * QW

with U = max(calendar_urgency, completion_urgency), a quick-win boost QW, and a
partial readiness lift R_eff. All inputs are coerced to finite numbers and
clamped to their domains, so the score can never be NaN/Infinity. Standard
library only.
"""

from __future__ import annotations

import math
from datetime import datetime

# -- Scoring knobs ------------------------------------------------------------
READY_LIFT = 0.7   # how far urgency lifts an unready task toward its target (<1)
PREP_BIAS = 0.7    # action bias on the prep branch (<1)
SCORE_CAP = 1000   # backstop guard, above the formula's natural max
TIE_BAND = 0.10    # value-closeness band (log-bucketed for transitivity)

# Quick-win lens: a short, ready-to-start task for a spare moment.
QUICK_WIN_MAX_EFFORT_HOURS = 0.25  # 15 minutes
QUICK_WIN_MIN_READINESS = 7


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def finite(x, fallback: float) -> float:
    """Coerce non-numeric / non-finite input to a default before the formula."""
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return fallback
    return xf if math.isfinite(xf) else fallback


def readiness_of(t: dict) -> float:
    return finite(t.get("readiness"), 8)  # default: presumed mostly-ready


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
    """A bare date ('YYYY-MM-DD') is treated as 5pm local; a datetime passes through."""
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
    """Discrete deadline tier: 'overdue' | 'today' | 'tomorrow' | None."""
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
    """Walk the queue in priority order, accumulate effort, and flag any task
    whose projected wall-clock finish lands past its deadline. Returns
    {id: 'at-risk' | 'tight'}."""
    out = {}
    now = now or datetime.now()
    acc = 0.0  # cumulative effort-hours so far, inclusive
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
            continue  # overdue — deadline_status owns that signal
        slack = hours_to_due - acc
        if slack <= 0:
            out[t["id"]] = "at-risk"
        elif slack < 0.5 * E:
            out[t["id"]] = "tight"
    return out


def rank_active(tasks: list, now: datetime | None = None, current_user_id=None) -> list:
    """Rank with deadlines as a constraint, not a blended term. Three tiers:
    0 overdue (EDF), 1 binding/at-risk (EDF, lifted above the value pack),
    2 value pack (value bucket, then sooner due breaks near-ties)."""
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
            return (tr, D[tid], 0.0)  # earliest-deadline-first
        return (tr, -value_bucket(V[tid]), D[tid])

    # Stable sort: equal keys keep by_value (value-desc) order.
    return sorted(by_value, key=sort_key)


# -- Quick-win lens -----------------------------------------------------------

def is_quick_win(task: dict) -> bool:
    if not task or task.get("completed"):
        return False
    e = task.get("effort_hours")
    if not isinstance(e, (int, float)) or not math.isfinite(e) or e <= 0 or e > QUICK_WIN_MAX_EFFORT_HOURS:
        return False
    return readiness_of(task) >= QUICK_WIN_MIN_READINESS or bool(task.get("execute_anyway"))


def quick_wins(tasks: list) -> list:
    """Quick wins, shortest first, ties by priority desc."""
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
