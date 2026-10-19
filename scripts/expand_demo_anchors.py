"""Reviewed StatsBomb-to-SoFIFA identity crosswalk for two extra matchday squads.

IDs are explicit, never accepted from fuzzy matching. The builder refreshes all
attributes from the pinned CSV; absent records use the disclosed cohort fallback.
"""
import json

from build_demo_dataset import DATA, refresh_fifa, save
from collect_demo_evidence import TARGETS, fetch

CROSSWALK = {
    3339:172723, 3381:191202, 3456:204311, 3472:180403, 3478:162895,
    3504:213666, 3509:192119, 3645:164468, 3666:215639, 3957:184432,
    3958:189505, 5198:179844, 5475:164477, 5594:178372, 6623:179527,
    20287:13732, 28100:184943, 40122:188152,
    3037:162240, 3043:190460, 3077:172871, 3083:200104, 3086:205923,
    3094:211117, 3099:167948, 3205:188377, 3308:186345, 3310:202491,
    3585:170368, 3594:169595, 3609:137677, 3611:209997, 10955:202126,
    10956:202335, 16067:222079, 20005:184087,
}


def main():
    anchors = json.loads((DATA/'fifa16_anchors.json').read_text(encoding='utf-8'))
    anchors = [a for a in anchors if a['team'] not in ('Chelsea', 'Tottenham Hotspur')]
    for team_name in ('Chelsea', 'Tottenham Hotspur'):
        team = next(t for t in fetch(f'lineups/{TARGETS[team_name]}.json') if t['team_name'] == team_name)
        for p in team['lineup']:
            pid = p['player_id']
            starter = bool(p['positions'] and p['positions'][0]['start_reason'] == 'Starting XI')
            anchors.append(dict(player_id=pid, name=p.get('player_nickname') or p['player_name'],
                                team=team_name, matchday_status='Starter' if starter else 'Bench',
                                fifa=dict(sofifa_id=CROSSWALK[pid], player_positions='LW' if pid == 3083 else 'CM')))
            if pid == 3083:
                # No Son record in this particular republished CSV. This band is
                # an explicit demo assumption, not an observed Son FIFA rating.
                anchors[-1].update(fallback_overall_band=[75, 85], fallback_foot='Right')
    save(DATA/'fifa16_anchors.json', anchors)
    refresh_fifa()
    print(f'Expanded identity crosswalk to {len(anchors)} players')


if __name__ == '__main__':
    main()
