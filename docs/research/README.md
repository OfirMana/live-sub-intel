# בדיקות החלטות בכל חמש דקות

העדכון הנוכחי הוא מ־18.10.2026: 12 הרצות קבוצה־משחק, 216 נקודות.

הורידו [research-review.zip](research-review.zip), חלצו ופתחו research/index.html.
החבילה כוללת גם את כרטיסי השחקנים והאקסל בתיקייה player-cards.
אפשר לבחור קבוצה ומשחק וללחוץ על דקה כדי לראות את פירוט הניקוד והמועמדים.

- [דוח HTML](index.html) — ב־GitHub הוא מוצג כקוד; יש לפתוח מקומית.
- [טבלת CSV של כל הנקודות](five_minute_decisions.csv).
- [JSON מלא דחוס](four_team_benchmark.json.gz), או JSON רגיל בתוך חבילת ההורדה.
- [רגישות לרענון](four_team_sensitivity.json).
- [רגישות להנחת סון](son_assumption_sensitivity.json).
- [פירוט בעברית](../MODEL_UPDATE_HE.md).

ההמלצות אינן מבוצעות בשחזור ההיסטורי, והכרטיסים קפואים לפני 13.01.2016.
נקודות חיוביות אינן חילופים שונים. ציון התועלת אינו הסתברות או שערים צפויים.
match_load_audit.json הוא דוח היסטורי מ־16.10.2026, עם חמש נקודות בלבד למשחק;
הוא נשמר להשוואה ואינו הדוח העדכני.

שחזור, אחרי הורדת קבצי StatsBomb באמצעות collector:

```bash
PYTHONPATH=src python scripts/benchmark_demo.py --out data/four_team_benchmark.json
PYTHONPATH=src python scripts/export_research_browser.py --report data/four_team_benchmark.json
PYTHONPATH=src python scripts/audit_match_load.py --out docs/research/four_team_sensitivity.json
PYTHONPATH=src python scripts/audit_son_assumption.py
```
