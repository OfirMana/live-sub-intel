"""Package the standalone player-card browser and verified workbook for sharing."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'docs/player-cards'


def main():
    required = ('index.html', 'Four_Club_Player_Cards.xlsx')
    for name in required:
        if not (SITE / name).is_file():
            raise FileNotFoundError(f'Missing export: {name}')
    instructions = (
        'כרטיסי ארבע קבוצות — 72 שחקנים לפני 13.01.2016\n\n'
        'חלצו את כל הקבצים לאותה תיקייה ופתחו index.html בדפדפן.\n'
        'אין צורך בהתקנה, בשרת או ברשת. קובץ Excel נמצא באותה תיקייה.\n'
        'התצוגה מציגה כרטיסים בלבד, ללא נתוני משחק חיים.\n\n'
        'נתוני מעקב פיזיים הם סינתטיים. לבראד סמית׳ ולסון חלופות סינתטיות.\n'
        'תאריך עדכון FIFA16 המדויק אינו מאומת. חוזק ראיות אינו הסתברות.\n\n'
        'סיכום ומגבלות להמשך:\n'
        'https://github.com/OfirMana/live-sub-intel/blob/feature/demo-player-dataset/docs/TEAM_HANDOFF_HE.md\n'
    )
    destination = SITE / 'player-cards.zip'
    with ZipFile(destination, 'w', ZIP_DEFLATED) as bundle:
        for name in required:
            bundle.write(SITE / name, name)
        bundle.writestr('READ_ME_FIRST.txt', instructions.encode('utf-8'))
    with ZipFile(destination) as bundle:
        assert bundle.testzip() is None
        for name in required:
            assert bundle.read(name) == (SITE / name).read_bytes()
    print(f'Offline player-card package: {destination}')


if __name__ == '__main__':
    main()
