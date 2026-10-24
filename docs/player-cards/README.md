> Research archive. Generated ZIP/Excel/preview artifacts are no longer bundled. Use the live Azure app for the submission; existing HTML is a historical research snapshot, not the current product.

# כרטיסי ארבע קבוצות

תצוגת 72 כרטיסי שחקנים לפני המשחק ב־13.01.2016. אין כאן נתוני משחק חיים.

## לפתיחה מהירה

1. הורידו את `player-cards.zip` (local generated export; not bundled) באמצעות Download raw file בגיטהאב.
2. חלצו את הקבצים לאותה תיקייה.
3. פתחו את `index.html` בדפדפן. אין צורך בהתקנה או בחיבור לרשת.

האתר כולל חיפוש, סינון לפי קבוצה ותפקיד, מעבר בין General/Recent/Season/Physical וכרטיס שחקן מלא. קישור האקסל יעבוד כשהקבצים נשארים באותה תיקייה.

- [קוד האתר העצמאי](index.html)
- `Four_Club_Player_Cards.xlsx` (יצוא מקומי שאינו כלול במאגר)
- [סיכום ההתקדמות והמשימות הפתוחות](../TEAM_HANDOFF_HE.md)

**GitHub מציג את קוד ה־HTML. GitHub Pages לא הופעל במסגרת העבודה.** כדי לראות את התצוגה, יש להוריד ולפתוח את הקובץ. כתובת localhost במחשב של חבר צוות אינה אתר ציבורי.

אפשר גם לשכפל את הענף ולהריץ:

```bash
python -m http.server 8767 --bind 127.0.0.1 --directory docs/player-cards
```

אז פתחו `http://127.0.0.1:8767` במחשב שלכם.

## האקסל

שבעה גיליונות: Cards, Rating detail, Season output, Physical, Positions, All fields, Guide.
יש טבלאות עם מסננים וכותרות קפואות. פירוט הרייטינג מפריד עוגן FIFA, התאמת עונה, General, שינוי Recent והדירוג האחרון. All fields כולל 19,635 שדות, לרבות תכונות FIFA וראיות העמדה. חוזק ראיות אינו הסתברות לנכונות.

## מקורות ומגבלות

StatsBomb Open Data מספק ראיות לפני תאריך החיתוך. General מעוגן בצילום FIFA16 שתאריך העדכון המדויק שלו אינו מאומת. לבראד סמית׳ ולסון חלופות סינתטיות מתועדות. אומדני המהירות/הריצה מבוססי FIFA ו־SkillCorner הם סינתטיים; אין מדידות tracking של השחקנים. שוערים אינם מקבלים ציוני שחקן שדה.

המקורות, המשקולות והנוסחאות המלאים נמצאים ב־[תיעוד הדאטה](../../demo_data/README.md) ובגיליון Guide.

## יצירה מחדש מהדאטה

```bash
node scripts/export_player_browser.mjs
```

ייצוא האקסל דורש `@oai/artifact-tool` בסביבת Node. בסביבת Codex המקומית אפשר להשתמש בחבילת התלויות המצורפת. אם החבילה נמצאת במקום אחר, מגדירים `ARTIFACT_NODE_MODULES` לנתיב תיקיית node_modules לפני ההרצה:

```bash
node scripts/export_player_workbook.mjs
```

הייצוא אינו משנה את כרטיסי השחקנים. פלטי QA זמניים אינם חלק מחבילת ההורדה.



Season output מציג שערים, פנדלים, בישולים, ניסיונות והצלחות דריבל ומסירה לפני החיתוך. שיעורי ל־90 ואחוזי הצלחה מחושבים בנוסחאות באקסל. [דוח ההחלטות](../research/README.md) מציג בדיקה בכל חמש דקות.
