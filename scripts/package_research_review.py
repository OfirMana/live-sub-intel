"""Bundle all current offline review artifacts, retaining relative browser links."""
import gzip
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]


def main():
    docs = ROOT/'docs'
    research = ['index.html','five_minute_decisions.csv','four_team_benchmark.json.gz',
                'four_team_sensitivity.json','son_assumption_sensitivity.json']
    cards = ['index.html','Four_Club_Player_Cards.xlsx']
    destination = docs/'research/research-review.zip'
    with ZipFile(destination,'w',ZIP_DEFLATED) as z:
        for folder, names in [('research',research),('player-cards',cards)]:
            for name in names:
                z.write(docs/folder/name,f'{folder}/{name}')
        z.writestr('research/four_team_benchmark.json',gzip.decompress((docs/'research/four_team_benchmark.json.gz').read_bytes()))
        z.write(docs/'MODEL_UPDATE_HE.md','MODEL_UPDATE_HE.md')
        z.writestr('READ_ME_FIRST.txt',('סקירת ארבע קבוצות — 18.10.2026\n\n'
                   'חלצו את כל החבילה.\n'
                   'פתחו research/index.html לבדיקת החלטות בכל חמש דקות.\n'
                   'פתחו player-cards/index.html לכרטיסי השחקנים.\n'
                   'האקסל נמצא בתיקייה player-cards.\n'
                   'המלצות חוזרות אינן חילופים שונים. בשחזור לא מבצעים את המלצות המנוע.\n'
                   'כל הכרטיסים קפואים לפני 13.01.2016. נתוני ריצה והחלופות לבראד ולסון סינתטיים.\n').encode('utf-8'))
    with ZipFile(destination) as z:
        assert z.testzip() is None
        for folder, names in [('research',research),('player-cards',cards)]:
            for name in names:
                assert z.read(f'{folder}/{name}') == (docs/folder/name).read_bytes()
    print(f'Offline research and cards bundle: {destination}')


if __name__ == '__main__':
    main()
