"""Builds data/player_buckets.csv: metric components per player, match and 15-minute bucket.

Downloads the whole StatsBomb Premier League 2015/16 season (380 matches, ~1 GB
of JSON) into a cache directory once. Pass --delete-raw to keep only the CSV.

    python scripts/build_player_buckets.py --out data/player_buckets.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from subintel.metrics import COMPONENTS, ComponentTracker
from subintel.schema import EventType
from subintel.statsbomb import OPEN_DATA, PREMIER_LEAGUE, SEASON_2015_16, load_events, load_lineups

BUCKET_STARTS = (0, 15, 30, 45, 60, 75)


def fetch(url: str, dest: Path) -> Path:
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".part")
        tmp.write_bytes(urllib.request.urlopen(url, timeout=120).read())
        tmp.rename(dest)
    return dest


def bucket_of(period: int, minute: int) -> int:
    if period == 1:
        return min(minute // 15, 2)
    return min(max(minute, 45) // 15, 5)


def bucket_minutes(on: float, off: float) -> list[float]:
    """Minutes on the pitch inside each bucket. First-half stoppage time is ignored (~1% error)."""
    ends = list(BUCKET_STARTS[1:]) + [max(off / 60, 90)]
    return [max(0.0, min(off / 60, end) - max(on / 60, start)) for start, end in zip(BUCKET_STARTS, ends)]


def match_rows(match: dict, cache: Path) -> list[dict]:
    mid = str(match["match_id"])
    events = load_events(fetch(f"{OPEN_DATA}/events/{mid}.json", cache / "events" / f"{mid}.json"), mid)
    players, slots = load_lineups(fetch(f"{OPEN_DATA}/lineups/{mid}.json", cache / "lineups" / f"{mid}.json"))
    end_clock = max(e.clock for e in events if e.type is EventType.PERIOD_END)
    by_player = {p.player_id: p for p in players}

    counts: dict[tuple[str, int], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    tracker = ComponentTracker()
    for ev in events:
        b = bucket_of(ev.period, ev.minute)
        for c in tracker.feed(ev):
            counts[(c.player_id, b)][c.component] += c.value

    rows = []
    for slot in slots:
        if slot.on_from_clock is None or slot.player_id not in by_player:
            continue
        p = by_player[slot.player_id]
        mins = bucket_minutes(slot.on_from_clock, slot.off_at_clock or end_clock)
        for b, m in enumerate(mins):
            if m <= 0:
                continue
            row = {
                "match_id": mid,
                "match_date": match["match_date"],
                "team_id": p.team_id,
                "player_id": p.player_id,
                "name": p.name,
                "role": p.role.value,
                "started": slot.on_from_clock == 0,
                "bucket": b,
                "minutes": round(m, 3),
            }
            row.update({k: round(counts[(p.player_id, b)].get(k, 0.0), 4) for k in COMPONENTS})
            rows.append(row)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("data/player_buckets.csv"))
    ap.add_argument("--cache", type=Path, default=Path("data/raw"))
    ap.add_argument("--delete-raw", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    matches_path = fetch(
        f"{OPEN_DATA}/matches/{PREMIER_LEAGUE}/{SEASON_2015_16}.json",
        args.cache / "matches" / f"{PREMIER_LEAGUE}_{SEASON_2015_16}.json",
    )
    matches = json.loads(matches_path.read_text())

    def work(match: dict) -> list[dict]:
        rows = match_rows(match, args.cache)
        if args.delete_raw:
            for kind in ("events", "lineups"):
                (args.cache / kind / f"{match['match_id']}.json").unlink(missing_ok=True)
        return rows

    with ThreadPoolExecutor(args.workers) as pool:
        all_rows = [r for rows in pool.map(work, matches) for r in rows]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(all_rows[0]))
        w.writeheader()
        w.writerows(all_rows)
    print(f"{len(matches)} matches -> {len(all_rows)} rows -> {args.out}")


if __name__ == "__main__":
    main()
