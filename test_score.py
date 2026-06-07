"""Self-contained tests for the scoring engine.

Numeric anchors are derived by hand from the formula (worked through on paper),
not copied from score.py's own output, so they actually constrain the port. The
rest assert structural invariants (monotonicity, tier order, quick-win
direction) that catch regressions a single magic number would miss.
"""

from datetime import datetime

import score as s


def approx(a, b, tol=1e-3):
    assert abs(a - b) <= tol, f"expected {b}, got {a}"


# -- Hand-computed urgency anchors --------------------------------------------

def test_cal_urgency_week_out():
    # d=7: base = 1 + 9/(1+(7/7)**1.5) = 1 + 9/2 = 5.5; d>=T so no accel.
    approx(s.cal_urgency(7), 5.5)


def test_cal_urgency_overdue_saturates():
    # d=0 -> 30; d=-5 -> 30 + 5*2 = 40 (capped at 40).
    approx(s.cal_urgency(0), 30.0)
    approx(s.cal_urgency(-5), 40.0)
    approx(s.cal_urgency(-100), 40.0)  # hard cap


def test_comp_urgency_comfortable_slack():
    # d=7, e=4h -> e_days=1, slack=7, base = 1 + 9/(1+3.5) = 3; no accel.
    approx(s.comp_urgency(7, 4), 3.0)


def test_comp_urgency_explodes_near_zero_slack():
    # Tiny slack drives the inverse-distance term up hard.
    assert s.comp_urgency(0.1, 4) > 20


# -- Hand-computed full-score anchor ------------------------------------------

def test_priority_default_no_due():
    # I=5, R=8, E=0.05, no due -> U=1.5, R_eff=8,
    # QW = 1 + 0.3*exp(-1/30) = 1.2901648,
    # do = (5*1.5*8*QW)/10 = 7.740989; prep loses.
    t = {"id": "x", "impact": 5, "readiness": 8, "effort_hours": 0.05}
    approx(s.priority(t), 7.7410)


# -- Structural invariants ----------------------------------------------------

def test_readiness_moves_the_score():
    # The whole point of READY_LIFT: readiness stays live. Higher R -> higher do.
    base = {"id": "x", "impact": 6, "effort_hours": 1}
    assert s.priority({**base, "readiness": 10}) > s.priority({**base, "readiness": 8})


def test_quick_win_boost_rewards_short_effort():
    # Lower effort -> larger QW -> higher displayed score, all else equal.
    base = {"id": "x", "impact": 6, "readiness": 8}
    assert s.priority({**base, "effort_hours": 0.05}) > s.priority({**base, "effort_hours": 4})


def test_prep_wins_for_unready_high_impact():
    # R=2, I=8, no due: prep (6.72*QW) beats do (2.4*QW) and R<=5.
    c = s.score_components({"id": "x", "impact": 8, "readiness": 2})
    assert c["prep_wins"] is True
    assert c["prep_score"] > c["do_score"]


def test_risk_on_zeroes_prep_and_lifts_readiness():
    c = s.score_components({"id": "x", "impact": 8, "readiness": 2, "execute_anyway": True})
    assert c["prep_score"] == 0.0
    assert c["R_eff"] >= 9
    assert c["prep_wins"] is False


def test_value_bucket_monotone():
    assert s.value_bucket(100) > s.value_bucket(10) > s.value_bucket(1)


def test_bad_fields_never_nan():
    # A garbage field must fall back, not poison the score.
    c = s.score_components({"id": "x", "impact": None, "readiness": float("nan"), "effort_hours": "oops"})
    assert c["display"] == c["display"]  # not NaN
    assert 0.1 <= c["display"] <= s.SCORE_CAP


# -- Ranking ------------------------------------------------------------------

NOW = datetime(2026, 6, 7, 12, 0, 0)


def test_overdue_ranks_first():
    tasks = [
        {"id": "B", "impact": 10, "readiness": 10, "effort_hours": 0.1},          # high value, no due
        {"id": "A", "impact": 2, "readiness": 8, "effort_hours": 1, "due_date": "2026-06-01"},  # overdue
        {"id": "C", "impact": 7, "readiness": 8, "effort_hours": 1, "due_date": "2026-06-20"},  # future
    ]
    order = [t["id"] for t in s.rank_active(tasks, NOW)]
    assert order[0] == "A", order  # overdue lifted above the value pack


def test_binding_deadline_lifts_above_value():
    # A low-value task that genuinely won't finish in time must beat a juicy
    # future task it would otherwise sit below.
    tasks = [
        {"id": "big", "impact": 10, "readiness": 9, "effort_hours": 2, "due_date": "2026-06-30"},
        {"id": "tight", "impact": 3, "readiness": 9, "effort_hours": 10, "due_date": "2026-06-07T18:00:00"},
    ]
    order = [t["id"] for t in s.rank_active(tasks, NOW)]
    assert order[0] == "tight", order


def test_completed_tasks_excluded():
    tasks = [
        {"id": "done", "impact": 10, "completed": True},
        {"id": "live", "impact": 4},
    ]
    order = [t["id"] for t in s.rank_active(tasks, NOW)]
    assert order == ["live"]


# -- Quick wins ---------------------------------------------------------------

def test_quick_win_filter_and_order():
    tasks = [
        {"id": "a", "impact": 5, "readiness": 9, "effort_hours": 0.1},   # qualifies
        {"id": "b", "impact": 9, "readiness": 9, "effort_hours": 0.05},  # qualifies, shorter
        {"id": "c", "impact": 5, "readiness": 3, "effort_hours": 0.1},   # too unready
        {"id": "d", "impact": 5, "readiness": 9, "effort_hours": 2},     # too long
    ]
    order = [t["id"] for t in s.quick_wins(tasks)]
    assert order == ["b", "a"], order  # shortest first


def test_due_label():
    assert s.due_label("2026-06-08T12:00:00", NOW) == "tomorrow"
    assert s.due_label("2026-06-12T12:00:00", NOW) == "5d"
    assert s.due_label("2026-06-05T12:00:00", NOW) == "2d late"


if __name__ == "__main__":
    import sys

    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  ok   {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
