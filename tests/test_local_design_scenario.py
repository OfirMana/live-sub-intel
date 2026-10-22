from synthetic_coach_room import create_synthetic_room


def test_lively_scenario_is_reproducible_with_early_goal_and_distinct_bookings():
    first, _ = create_synthetic_room(scenario='lively')
    again, _ = create_synthetic_room(scenario='lively')
    events = first['fixtures']['synthetic-demo']['stat_events']
    assert events == again['fixtures']['synthetic-demo']['stat_events']
    goals = [e for e in events if e['kind'] == 'goal']
    assert len(goals) == 3 and 27 <= goals[0]['elapsed'] < 28
    cards = [e for e in events if e.get('card')]
    assert len(cards) == len({e['player_id'] for e in cards}) == 5
    assert all(e['card'] == 'yellow' for e in cards)


def test_original_scenario_still_has_original_goal_and_card_schedule():
    bootstrap, _ = create_synthetic_room()
    events = bootstrap['fixtures']['synthetic-demo']['stat_events']
    assert [int(e['elapsed']) for e in events if e['kind'] == 'goal'] == [54, 78, 82]
    assert [int(e['elapsed']) for e in events if e.get('card')] == [32, 61]
