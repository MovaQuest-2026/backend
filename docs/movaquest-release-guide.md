# Гайд завершення backend задач MovaQuest

Цей гайд описує, що вже підготовлено в репозиторії та які кроки лишилися для інтеграції з мобільним фронтендом, Render і Google Play.

Зміни в цьому робочому дереві проходили lint і перевірку синтаксису, але інтеграційні тести та production міграції ще не запускалися.

## Поточний стан

| Напрям | Стан бекенду | Що лишилося |
| --- | --- | --- |
| Deepgram | Endpoint повертає транскрипт, загальну та word-level confidence, таймінги й опційний `pronunciation_feedback` за `expected_text`. | Перевірити з реальним ключем і мобільним записом; score є heuristic, тому за потреби окремо підібрати phoneme-level engine. |
| Mobile парольний вхід | `X-Client: mobile` повертає Bearer токени. Refresh-токени зберігаються як хеші та ротуються атомарно. | Під’єднати клієнт і пройти ручний сценарій. |
| Mobile Google OAuth | Є стартовий маршрут із перевіркою deep link, завершення через короткоживучий одноразовий код і exchange endpoint. | Під’єднати frontend flow та налаштувати Google credentials у Render/Google Cloud. OAuth помилки наразі ведуть на стандартний frontend redirect. |
| Видалення акаунта | `DELETE /api/v1/users/me` фізично видаляє акаунт і залежні дані, завершує сесії. | Додати frontend сторінку видалення та опублікувати її URL у Play Console. |
| Скарги на коментарі | Є `POST /api/v1/comments/{id}/report`; три унікальні скарги приховують коментар. Адмін може переглядати скарги й видаляти коментарі. | Увімкнути адмінпанель і перевірити moderation flow. |
| Контент / PostgreSQL | Є таблиця `media_videos` (`BYTEA`) та API upload/list/stream/delete із checksum і HTTP Range. | Застосувати міграцію, перевірити розмір бази та завантажити відео через admin API. |
| Адмінпанель | SQLAdmin та керування користувачами є в коді. | У Render вона вимкнена, поки не задані параметри адміністратора. |

## 1. Підготувати Google Cloud та Android дані

Перед налаштуванням Google Cloud зібрати:

1. Google Cloud project, який використовує вебверсія MovaQuest.
2. Android `applicationId` / package name із конфігурації мобільного застосунку.
3. SHA-1 fingerprint debug сертифіката та release/upload або Play App Signing сертифіката.
4. Права на зміну OAuth credentials у Google Cloud Console.

У Google Cloud Console:

1. Відкрити правильний проєкт і перевірити OAuth consent screen / Branding та Audience.
2. Переконатися, що існуючий **Web application OAuth client** має authorized redirect URI бекенду:
   `https://<render-service>.onrender.com/api/v1/auth/oauth/callback/google`.
3. Не замінювати цей URI на `movaquest://...`: Google повертається на backend callback, а вже бекенд перенаправляє в застосунок.
4. Якщо мобільний фронтенд використовує Google Sign-In SDK або потребує Android OAuth client, створити Android credential з точним package name та SHA-1. Для Play App Signing fingerprint дивитися в Play Console → App integrity. Google описує вимогу SHA-1 у [Client authentication](https://developers.google.com/android/guides/client-auth).
5. Зберегти client ID/secret Web OAuth client для Render. Android client ID не замінює серверні Web client credentials.

Якщо фронтенд використовує лише system browser / Custom Tab та бекендовий Google flow, узгодити з frontend розробником, чи потрібен Android OAuth client окремо. Не використовувати Google OAuth напряму з custom scheme: у цьому flow custom scheme використовується лише між нашим бекендом і застосунком, а callback Google залишається HTTPS URI бекенду.

## 2. Заповнити Render Environment Variables

У Render Dashboard → backend Web Service → Environment додати або перевірити:

```dotenv
OAUTH_GOOGLE_CLIENT_ID=<Web OAuth client ID>
OAUTH_GOOGLE_CLIENT_SECRET=<Web OAuth client secret>
OAUTH_REDIRECT_BASE_URL=https://<render-service>.onrender.com
OAUTH_ALLOWED_BASE_URLS=https://<render-service>.onrender.com
FRONTEND_URL=https://<frontend-host>
FRONTEND_ALLOWED_URLS=https://<frontend-host>
```

`OAUTH_REDIRECT_BASE_URL` має бути origin бекенду, без `/api/...` шляху. Повний Google callback складається з цього origin і маршруту `/api/v1/auth/oauth/callback/google`. Якщо OAuth запити проходять через додатковий proxy/custom domain, додати тільки реальні callback origins до `OAUTH_ALLOWED_BASE_URLS`.

Для адмінпанелі:

```dotenv
ADMIN_ENABLED=true
ADMIN_USERNAME=<унікальний логін адміністратора>
ADMIN_PASSWORD=<довгий випадковий пароль>
ADMIN_BASE_URL=/admin
```

Пароль має бути секретом Render, не записувати його у Git. Після оновлення Environment Variables зробити deploy/restart. Якщо панель лишається вимкненою, користувачі все одно керуються через наявні admin-only API endpoint-и, але SQLAdmin UI не буде змонтований.

Deepgram:

```dotenv
DEEPGRAM_ENABLED=true
DEEPGRAM_PUBLIC_ENABLED=false
DEEPGRAM_API_KEY=<секретний Deepgram API key>
DEEPGRAM_MODEL=nova-3
DEEPGRAM_LANGUAGE=es
```

API key має залишатися тільки в backend Environment Variables.

## 3. Вибрати та під’єднати storage для відео

На надісланому скріншоті показано `6.75% used out of 1GB` (приблизно 67.5 MB зайнято). Для обраної PostgreSQL стратегії цей ліміт включає і binary відео. Перед upload потрібно збільшити storage/план Postgres або обмежити сумарний розмір контенту. [Render: Free Postgres limits](https://render.com/docs/free).

### Варіант A — PostgreSQL BYTEA для поточного релізу

1. Переконатися, що Render Postgres має достатньо storage для бази, міграцій і всіх відео.
2. Production Docker image вже запускає `CONFIRM_PRODUCTION_MIGRATION=yes alembic upgrade head`
   перед FastAPI. Це покриває Free-план Render, де Pre-Deploy Command недоступна; при кожному restart
   Alembic перевіряє версію і застосовує лише нові міграції.
3. Через admin token/session завантажити файл: `POST /api/v1/content/videos?name=lesson-1.mp4` з multipart-полем `video`.
4. Перевірити `GET /api/v1/content/videos/lesson-1.mp4`, `DELETE /api/v1/content/videos/lesson-1.mp4` і `Range`-запити мобільним відеоплеєром.
5. Контролювати usage Postgres і зберігати оригінали відео окремо: database backup не замінює незалежну копію файлів.

Відео в `BYTEA` збільшують розмір бази, backup і час передачі через DB connection. Якщо контент стане великим або потрібне масштабування, storage adapter потрібно перенести на S3-compatible object storage.

### Варіант B — S3-compatible object storage + CDN

Вибрати цей варіант, якщо очікується кілька backend інстансів, багато відео, adaptive streaming або потрібні незалежні deploy-и. У цьому варіанті backend має зберігати metadata та видавати signed URLs або проксійований доступ. Перед реалізацією потрібен вибір провайдера й credentials; після отримання відеофайлів можна визначити формат transcoding та структуру каталогів.

## 4. Застосувати міграції бази даних

У репозиторії додані міграції для mobile refresh/OAuth credentials, скарг на коментарі, audit log та lesson catalog.
Для ручного запуску на платному Render-сервісі або локально встановити:

```bash
CONFIRM_PRODUCTION_MIGRATION=yes alembic upgrade head
```

Застосовувати міграції перед запуском нової версії застосунку. Перевірити deploy logs: команда має завершитися успішно, а сервіс після неї — стати healthy. Якщо production база ще не має `alembic_version`, спершу перевірити її схему. `alembic stamp ae2deece1038` дозволений тільки для бази, яка вже точно відповідає baseline; не stamp-ати неперевірену або порожню базу. Див. [Render deploys](https://render.com/docs/deploys).

Для локальної перевірки з кореня репозиторію:

```powershell
uv sync --all-packages --all-extras
Set-Location backend
uv run alembic upgrade head
uv run pytest
```

## 5. Під’єднати mobile password auth

### Login

Запит:

```http
POST /api/v1/auth/login
X-Client: mobile
Content-Type: application/x-www-form-urlencoded
```

Form fields лишаються як у web login: `username`, `password`, `remember_me` (для mobile ігнорується). Успіх повертає:

```json
{
  "access_token": "…",
  "refresh_token": "…",
  "token_type": "bearer",
  "expires_in": 3600
}
```

Зберігати токени в захищеному сховищі пристрою. Access token передавати для захищених запитів:

```http
Authorization: Bearer <access_token>
```

Мобільні запити не повинні покладатися на cookie браузера. Bearer-запити не потребують CSRF token; web cookie-flow продовжує його вимагати.

### Refresh

```http
POST /api/v1/auth/refresh
Content-Type: application/json

{"refresh_token":"…"}
```

Успішна відповідь повертає нову пару. Клієнт має замінити обидва токени одразу: старий refresh token після ротації повторно не приймається. `401` означає, що треба вийти з акаунта; `5xx` слід трактувати як тимчасову помилку.

### Logout

```http
POST /api/v1/auth/logout
Authorization: Bearer <access_token>
Content-Type: application/json

{"refresh_token":"…"}
```

Відповідь Bearer logout — `204`. Якщо refresh token уже не збережений, тіло можна опустити; access token діятиме не довше свого TTL.

## 6. Під’єднати mobile Google OAuth

У поточному backend реалізований окремий mobile entrypoint; він відрізняється від початкового draft `/oauth/google?redirect_to=...`:

1. Застосунок відкриває system browser / Custom Tab:

   ```text
   GET https://<backend-host>/api/v1/auth/oauth/mobile/google?redirect_uri=movaquest%3A%2F%2Fauth%2Fcallback
   ```

   Для dev-збірки можна передати `exp+movaquest://auth/callback`.

2. Backend перенаправляє на штатний `/api/v1/auth/oauth/google`, зберігає OAuth state/PKCE у browser flow і після успішного входу встановлює звичайну web session у browser.
3. Backend завершує flow через `movaquest://auth/callback?code=...`. Код одноразовий, зберігається як hash і діє приблизно 60 секунд.
4. Застосунок обмінює код:

   ```http
   POST /api/v1/auth/oauth/exchange
   X-Client: mobile
   Content-Type: application/json

   {"code":"…"}
   ```

5. Відповідь містить ті самі `access_token`, `refresh_token`, `token_type`, `expires_in`, що й mobile password login.

Точний frontend callback scheme має бути зареєстрований у Android app config. Перевірити, що застосунок відкриває тільки дозволений callback URI. Невдалий Google OAuth поки перенаправляється на `FRONTEND_URL` з помилкою, а не у deep link; перед релізом треба вирішити, чи фронтенду потрібен мобільний error callback.

## 7. Доробити Deepgram pronunciation feedback

`POST /api/v1/transcription` повертає transcript, `confidence`, `words[].confidence`, `start` і `end`. Це оцінка впевненості Deepgram у розпізнаному тексті, а не фонетичний pronunciation score. Deepgram описує ці поля як transcript/word confidence у [confidence guide](https://developers.deepgram.com/docs/confidence).

Що зробити у frontend:

1. Для запису з Android відправляти multipart файл як `audio/mp4` (AAC у контейнері m4a; наприклад, `answer.m4a`).
2. Передавати `hint` тільки як ключові слова для покращення recognition recall. `hint` не є гарантованою еталонною фразою й не змушує Deepgram видати оцінку вимови.
3. Для навчального фідбеку зіставляти отриманий transcript з очікуваною фразою: нормалізувати регістр/пунктуацію, порівняти токени та показати слова, що відрізняються. Низький word confidence можна показувати як «розпізнано невпевнено», не як «вимовлено неправильно».
4. Якщо потрібна фонетична оцінка звуків, окремо вибрати pronunciation-assessment сервіс або власну модель; STT confidence цього не замінює.

## 8. Увімкнути керування користувачами й модерування

1. У Render задати admin environment variables з розділу 2 і перейти на `https://<backend-host>/admin`.
2. Перевірити вхід адміністратора, пошук користувачів, зміну ролі/стану і вихід з панелі.
3. Перевірити comment report:
   - авторизований користувач надсилає `POST /api/v1/comments/{comment_id}/report`;
   - тіло має `reason: spam | abuse | other`, optional `details`;
   - повторна скарга того самого акаунта не збільшує лічильник;
   - після трьох унікальних акаунтів коментар зникає з публічної видачі;
   - адміністратор переглядає скарги в `/admin` та може видалити коментар.

## 9. Видалення акаунта та Google Play

Backend endpoint:

```http
DELETE /api/v1/users/me
Authorization: Bearer <access_token>
```

Web-виклик може використовувати cookie з CSRF захистом. Frontend має додати зрозумілу сторінку після входу, пояснити незворотність дії, запросити підтвердження та після `204` очистити локальну сесію.

Для Play Console потрібна також зовнішня URL сторінка, де користувач може знайти процес видалення акаунта. Опублікувати її без вимоги входу до застосунку (або чітко пояснити кроки підтвердження), вказати назву застосунку й помітно розмістити шлях до запиту видалення. Потім додати URL у Play Console в секції Data safety / Account deletion. Перевірити актуальні вимоги за [офіційною довідкою Google Play](https://support.google.com/googleplay/android-developer/answer/13327111).

## 10. Фінальний checklist

- [ ] Нові Alembic migrations успішно застосовані в Render Postgres.
- [ ] `DEEPGRAM_API_KEY` і Google Web OAuth client credentials встановлені як secrets Render.
- [ ] Адмінпанель або ввімкнена з сильними credentials, або свідомо лишена вимкненою.
- [ ] Android package name і signing fingerprints відповідають OAuth client config.
- [ ] Mobile password login повертає токени без `Set-Cookie`.
- [ ] Bearer GET/POST працюють без cookie та CSRF заголовка; cookie web login і CSRF працюють як раніше.
- [ ] Refresh повертає нову пару; повторне використання старого refresh token дає `401`.
- [ ] Google OAuth завершується через app deep link; код після exchange або після 60 секунд повторно не проходить.
- [ ] Android multipart transcription проходить з `audio/mp4` і повертає word-level feedback.
- [ ] Видалення акаунта прибирає user-linked data й завершує сесії.
- [ ] Три різні скарги приховують коментар; адмін може його переглянути й видалити.
- [ ] PostgreSQL storage збільшений; migration застосована; upload/stream endpoint-и перевірені після отримання відео.
- [ ] URL сторінки видалення акаунта доступний і внесений у Play Console.
- [ ] Інтеграційні тести та ручна перевірка web regression пройшли.
