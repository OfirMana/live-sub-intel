# פריסת חדר המשחק ל־Azure App Service

האפליקציה היא `scripts/serve_app.py`: חדר המשחק עם הסברים מ־Foundry. כל קוד שנכנס ל־`main` נפרס אוטומטית דרך GitHub Actions.

## 1. יצירת Web App

ב־portal.azure.com: **Create a resource ← Web App**.

| שדה | ערך |
|---|---|
| Subscription | אותו מנוי של Foundry |
| Resource group | אותה קבוצה שבה נמצא `live-sub-intel-resource` |
| Name | `live-sub-intel` (אם תפוס, מוסיפים סיומת) |
| Publish | Code |
| Runtime stack | Python 3.12 |
| Operating System | Linux |
| Region | אזור קרוב, למשל West Europe. אם אין מכסה, בוחרים אזור אחר |
| Pricing plan | Basic B1. Free F1 נרדם ומוגבל ב־CPU, ולא מתאים לדמו |

בלשונית **Deployment**:
- **Continuous deployment**: Enable.
- מתחברים ל־GitHub ובוחרים `TomThomasPrintac` ← `live-sub-intel` ← `main`.

Azure יוסיף לריפו קובץ workflow תחת `.github/workflows/`. זה תקין וצפוי.

**Review + create ← Create.**

## 2. משתני סביבה

בדף האפליקציה: **Settings ← Environment variables ← App settings ← Add**:

| שם | ערך |
|---|---|
| `FOUNDRY_ENDPOINT` | `https://live-sub-intel-resource.openai.azure.com/` |
| `FOUNDRY_DEPLOYMENT` | `gpt-4.1-mini` |
| `FOUNDRY_API_KEY` | המפתח מ־Keys and Endpoint |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | `true` (אם לא קיים כבר) |

**Apply ← Confirm.** האפליקציה תופעל מחדש.

המפתח נשמר רק כאן, בשרת. הוא לא מגיע לדפדפן ולא נכנס לריפו.

## 3. פקודת הפעלה

**Settings ← Configuration ← General settings ← Startup Command**:

```
python scripts/serve_app.py --host 0.0.0.0
```

**Save.** השרת מאזין לפורט ש־App Service מגדיר במשתנה `PORT`. אם המשתנה לא קיים, ברירת המחדל היא 8000.

## 4. בדיקה

1. ב־GitHub, בלשונית **Actions**, מחכים שה־workflow יסתיים בירוק.
2. בדף האפליקציה ב־Azure, **Overview ← Default domain**, פותחים את הכתובת. הטעינה הראשונה לוקחת בערך 10–30 שניות, כי השרת מוריד את נתוני המשחקים ומשחזר אותם.
3. `https://<הכתובת>/healthz` צריך להחזיר `"llm_configured": true`.
4. בחדר המשחק: מתקדמים לנקודת בדיקה ← **בדוק חילופים** ← **הסבר את ההחלטה**. מתחת להסבר צריך להיות כתוב "נכתב על ידי gpt-4.1-mini ב־Microsoft Foundry".

אם משהו לא עובד: **Monitoring ← Log stream** מציג את יומן השרת, כולל שגיאות של Foundry.

## מה למדנו בפריסה הראשונה (20.10.2026)

- **West Europe לא קיבל לקוחות חדשים** ("The selected region is currently not accepting new customers"). עברנו ל־**Sweden Central**.
  כתובת האפליקציה: https://live-sub-intel-fcfudheze9b5ewfz.swedencentral-01.azurewebsites.net/
- **ההרצה הראשונה של ה־workflow נכשלה ב־Login to Azure** עם `No subscriptions found`. ההרשאה של GitHub ב־Azure עוד לא התעדכנה. אחרי כמה דקות, **Re-run failed jobs** עבר.
- **כפתור Browse ב־Overview נפתח ל־`about:blank#blocked`**, כי Chrome חסם חלון חדש. פותחים את הכתובת ידנית בכרטיסייה חדשה.
- **`llm_configured: true` לא מוכיח שהמודל עונה.** אם ההסבר מסומן כתבנית, פותחים **Monitoring ← Log stream**, לוחצים "הסבר", ומחפשים שורה `Explanation failed: type=... cause=...`.
  - הערכים של `FOUNDRY_*` מנוקים מרווחים בתחילתם ובסופם, כי רווח בסוף מפתח שהודבק פוסל כל קריאה.

## בסיום ההאקתון

כדי שלא להמשיך לשלם, מוחקים את ה־Web App ואת ה־App Service plan, או את כל קבוצת המשאבים.
