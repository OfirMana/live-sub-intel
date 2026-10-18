"""Rebuild committed cards offline from frozen FIFA attributes and StatsBomb evidence.

Use --refresh-fifa to verify/refresh the source subset from cached players_16.csv.
Run collect_demo_evidence.py first to refresh event evidence from the network.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

from subintel.demo_dataset import DIMS, FIFA_POSITION, GENERAL_CAP, RECENT_CAP, WEIGHTS, build_player
from subintel.statsbomb import ROLE_BY_POSITION

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'demo_data'


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8', newline='\n')


def refresh_fifa():
    import pandas as pd
    anchors = json.loads((DATA / 'fifa16_anchors.json').read_text(encoding='utf-8'))
    raw = ROOT / 'data/raw/players_16.csv'
    frame = pd.read_csv(raw)
    # SoFIFA exports attach update annotations (e.g. '82-1'). The leading
    # number is the rating; the suffix is a change annotation, not arithmetic.
    for col in frame.columns:
        if col.startswith(('attacking_', 'skill_', 'movement_', 'power_', 'mentality_', 'defending_', 'goalkeeping_')):
            frame[col] = pd.to_numeric(frame[col].astype(str).str.extract(r'^(\d+)', expand=False), errors='coerce')
    by_id = {str(r['sofifa_id']): r for r in frame.to_dict('records')}
    # Retain identity crosswalk only. Replace every available rating from the source CSV.
    for anchor in anchors:
        old = anchor['fifa']
        source = by_id.get(str(old.get('sofifa_id')))
        if source:
            anchor['fifa'] = {k: (None if pd.isna(v) else v) for k, v in source.items()}
            anchor['fifa']['source_status'] = 'OBSERVED_FIFA16_REPUBLISHED_SOFIFA_SNAPSHOT'
        else:
            role = ROLE_BY_POSITION[FIFA_POSITION[old['player_positions'].split(',')[0].strip()]].value
            low, high = anchor.get('fallback_overall_band', [60, 68])
            foot = anchor.get('fallback_foot', 'Left')
            pool = frame[(frame.overall >= low) & (frame.overall <= high) & frame.player_positions.map(
                lambda s: any(ROLE_BY_POSITION[FIFA_POSITION[p.strip()]].value == role for p in s.split(',')))]
            values = {k: float(pool[k].median()) for k in frame.select_dtypes('number').columns if not pool[k].isna().all()}
            values.update(player_positions=old['player_positions'], preferred_foot=foot,
                          source_status='SYNTHETIC_FIFA_LIKE_ROLE_COHORT_MEDIAN',
                          fallback_rule=f'FIFA16 same-role players with overall {low}..{high}; numeric medians; {foot} foot is a demo assumption',
                          sofifa_id=None, short_name=anchor['name'])
            anchor['fifa'] = values
        anchor['fifa']['source_url'] = 'https://github.com/kushal-gopal/EA-Sports-Fifa/blob/658e9f96cafcfdb636d6ca96fcc9bfdb1c064868/players_16.csv'
        anchor['fifa']['source_sha256'] = hashlib.sha256(raw.read_bytes()).hexdigest()
        anchor['fifa']['snapshot_caveat'] = 'FIFA16 edition snapshot; precise SoFIFA update date unverified; not claimed to be January 2016.'
    save(DATA / 'fifa16_anchors.json', anchors)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--refresh-fifa', action='store_true')
    args = ap.parse_args()
    if args.refresh_fifa:
        refresh_fifa()
    anchors = json.loads((DATA / 'fifa16_anchors.json').read_text(encoding='utf-8'))
    evidence = json.loads((DATA / 'source_evidence.json').read_text(encoding='utf-8'))
    players = sorted((build_player(a, evidence) for a in anchors), key=lambda p: (p['team'], p['primary_role'], p['name']))
    dataset = dict(metadata=dict(target_match_id='3754305', target_matches=evidence.get('target_matches'), target_date=evidence['cutoff'],
                                player_count=len(players), general_adjustment_cap=GENERAL_CAP, recent_adjustment_cap=RECENT_CAP,
                                mapping=WEIGHTS, source_evidence_sha256=hashlib.sha256((DATA / 'source_evidence.json').read_bytes()).hexdigest(),
                                team_windows=evidence['team_windows'],
                                warning='Real historical benchmark player evidence; final event stream must be labelled SYNTHETIC.'), players=players)
    save(DATA / 'demo_player_profiles.json', dataset)
    rows = []
    for p in players:
        row = dict(player_id=p['player_id'], player=p['name'], team=p['team'], primary_position=p['positions']['primary'])
        for block in ('general', 'recent'):
            row.update({f'{block}_{d}': p[block]['ratings'][d] for d in DIMS})
        row.update(recent_minutes=p['recent']['minutes'], recent_reliability=p['recent']['reliability'],
                   height_cm=p['identity']['height_cm'], pace=p['physical']['pace'],
                   max_speed_kmh=(p['physical']['tracking'] or {}).get('max_speed_kmh'),
                   stamina=p['physical']['stamina'], strength=p['physical']['strength'])
        row.update({k: p['season']['totals'][k] for k in ('goals','non_penalty_goals','penalty_goals','assists','dribble_attempts','dribbles_completed','pass_attempts','passes_completed')})
        row.update(pass_completion=p['season']['pass_completion'], dribble_success=p['season']['dribble_success'])
        rows.append(row)
    with (DATA / 'demo_player_profiles.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    print(f'Built {len(players)} reproducible demo profiles')


if __name__ == '__main__':
    main()
