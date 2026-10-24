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


def test_scripted_substitutions_update_timeline_stats_and_actor_eligibility():
    bootstrap, evaluate = create_synthetic_room(scenario='lively')
    from subintel.auto_plans import AutoConfig
    views = {v['team_id']: v for v in bootstrap['views']}
    active = {tid: {p['player_id'] for p in v['lineup_timeline'][0]['lineup']} for tid,v in views.items()}
    used = set().union(*active.values())
    counts = {'24': 0, '1': 0}
    events = bootstrap['fixtures']['synthetic-demo']['stat_events']
    for event in events:
        tid, pid = event['team_id'], event.get('player_id')
        if pid:
            assert pid in active[tid], event
        if event.get('recipient_id'):
            assert event['recipient_id'] in active[tid], event
        if event['kind'] == 'substitution':
            incoming = event['replacement_id']
            assert incoming not in used
            active[tid].remove(pid); active[tid].add(incoming); used.add(incoming)
            counts[tid] += 1
            assert len(active[tid]) == 11
    assert counts == {'24': 2, '1': 2}
    config = AutoConfig().model_dump_json()
    before = evaluate('synthetic-demo', '24', 55, config)
    after = evaluate('synthetic-demo', '24', 60, config)
    assert '3535' in {p['player_id'] for p in before['observed']['lineup']}
    assert '3380' in {p['player_id'] for p in after['observed']['lineup']}
    assert '3535' not in {p['player_id'] for p in after['observed']['lineup']}
    benteke = next(p for p in after['observed']['lineup'] if p['player_id']=='3380')
    assert benteke['number'] == 9
    assert all(p['in_player']['id'] != '3380' for p in after['alternatives'])
    end = evaluate('synthetic-demo','24',90,config)
    assert end['state']['subs_left'] == 1
    assert end['alternatives']
    # Rewinding reconstructs the original lineup rather than mutating cached history.
    assert evaluate('synthetic-demo','24',55,config) == before


def test_late_arsenal_keeps_a_sub_and_evaluates_tactics_after_conceding():
    from subintel.auto_plans import AutoConfig
    _, evaluate = create_synthetic_room(scenario='lively')
    config = AutoConfig(stance='attack',objective='win').model_dump_json()
    after_goal = evaluate('synthetic-demo','1',85,config)
    assert after_goal['state']['goal_diff'] == -1
    assert after_goal['state']['subs_left'] == 1
    assert after_goal['recommendation'] == 'TACTICAL_ADJUSTMENT'
    assert after_goal['selected_plan']['formation']
    final = evaluate('synthetic-demo','1',90,config)
    assert final['state']['subs_left'] == 1
    assert final['alternatives']
    assert final['no_substitution_reason'] == 'BELOW_THRESHOLD'
    assert final['formation_only']['benefit'] < final['threshold']
