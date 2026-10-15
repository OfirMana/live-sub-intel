from subintel.engine import substitution_score
from subintel.metrics import ComponentTracker
from subintel.schema import Event, EventType, TeamNeeds


def ev(**kw) -> Event:
    base = dict(event_id="e", match_id="m", period=1, minute=10, second=0, team_id="A", player_id="p1")
    return Event(**{**base, **kw})


def components(*events: Event) -> list[tuple[str, str, float]]:
    t = ComponentTracker()
    return [(c.player_id, c.component, c.value) for e in events for c in t.feed(e)]


def test_progressive_pass_into_box_credits_passer_and_receiver():
    out = components(ev(type=EventType.PASS, x=80, y=40, end_x=110, end_y=40, success=True, recipient_id="p2"))
    assert ("p1", "prog_passes", 1.0) in out
    assert ("p1", "box_passes", 1.0) in out
    assert ("p2", "box_presence", 1.0) in out


def test_short_pass_from_own_third_is_not_progressive():
    out = components(ev(type=EventType.PASS, x=20, y=40, end_x=45, end_y=40, success=True))
    assert all(c != "prog_passes" for _, c, _ in out)


def test_failed_pass_is_a_ball_loss_and_nothing_else():
    out = components(ev(type=EventType.PASS, x=80, y=40, end_x=110, end_y=40, success=False))
    assert [c for _, c, _ in out] == ["ball_actions", "ball_losses"]


def test_set_pieces_do_not_count():
    assert components(ev(type=EventType.PASS, x=119, y=1, end_x=110, end_y=40, success=True, set_piece=True)) == []


def test_shot_credits_xg_to_shooter_and_xa_to_key_passer():
    key_pass = ev(event_id="k", type=EventType.PASS, x=100, y=30, end_x=108, end_y=40, success=True, recipient_id="p2")
    shot = ev(event_id="s", player_id="p2", type=EventType.SHOT, x=108, y=40, xg=0.3, key_pass_id="k")
    out = components(key_pass, shot)
    assert ("p2", "npxg", 0.3) in out
    assert ("p1", "xa", 0.3) in out


def test_penalties_are_excluded():
    assert components(ev(type=EventType.SHOT, x=108, y=40, xg=0.76, penalty=True)) == []


def needs(**values: float) -> TeamNeeds:
    dims = ("threat", "creation", "progression", "retention", "defense")
    return TeamNeeds(
        team_id="A",
        needs={d: values.get(d, 0.5) for d in dims},
        deficit_z={d: 0.0 for d in dims},
        importance={d: 1.0 for d in dims},
    )


def test_flat_needs_give_no_credit_for_a_better_all_rounder():
    # A specialist (great threat) replaced by an all-rounder when nothing is wrong: no gain.
    delta = {"threat": -1.5, "creation": 0.5, "progression": 0.8, "retention": 0.8, "defense": 1.0}
    assert substitution_score(needs(), delta) < 0


def test_gain_in_the_problem_dimension_wins():
    delta = {"threat": 1.2, "creation": 0.0, "progression": -0.3, "retention": 0.0, "defense": 0.0}
    assert substitution_score(needs(threat=0.85), delta) > 0
