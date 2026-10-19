"""Export derived, labelled per-position suitability for every canonical player."""
import hashlib
import json
from pathlib import Path

from subintel.auto_plans import position_fit
from subintel.coach_room import POSITIONS
from subintel.demo_data import load_demo_profiles

ROOT=Path(__file__).resolve().parents[1]


def main():
    source=ROOT/'demo_data/demo_player_profiles.json'
    data=load_demo_profiles()
    payload=dict(version='position-fit-v1',kind='HEURISTIC_NOT_MEASURED_CHEMISTRY',
        source_profile_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        rules=dict(primary=1.,supported_secondary=.85,supported_broad_only=.75,unsupported=0.,
                   observed_minutes_for_secondary=180),
        players={str(p['player_id']):dict(name=p['name'],positions={pos:dict(zip(('fit','source'),position_fit(p,pos))) for pos in POSITIONS}) for p in data['players']})
    target=ROOT/'demo_data/position_suitability.json'
    target.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Exported {len(payload["players"])} players × {len(POSITIONS)} positions -> {target.name}')


if __name__=='__main__':main()
