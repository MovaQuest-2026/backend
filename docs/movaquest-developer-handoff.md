# MovaQuest — handoff для розробників

Документ описує реалізований backend contract і дані, які потрібно отримати від frontend/mobile команди.

## Поточний стан

- Git branch: `codex/p1-progress`
- Commit: `e32b9f8`
- Production migrations до `d4f7a2c9e611` застосовані.
- Production admin credentials уже налаштовані в Render.
- Секрети не зберігаються в репозиторії або цьому файлі.

## Mobile password auth

Mobile-запити передають заголовок `X-Client: mobile`.

Login:

```http
POST /api/v1/auth/login
Content-Type: application/x-www-form-urlencoded
X-Client: mobile
```

Поля: `username`, `password`, `remember_me`.

Відповідь містить `access_token`, `refresh_token`, `token_type=bearer` і `expires_in=3600`.

Захищені запити використовують:

```http
Authorization: Bearer <access_token>
```

Refresh:

```http
POST /api/v1/auth/refresh
Content-Type: application/json

{"refresh_token":"..."}
```

Refresh token ротуються. Після refresh застосунок має замінити обидва токени. Старий refresh token повторно не приймається.

Logout:

```http
POST /api/v1/auth/logout
Authorization: Bearer <access_token>
Content-Type: application/json

{"refresh_token":"..."}
```

Очікувана mobile-відповідь — `204`.

## Google OAuth для Android

### Backend callback

У Google Web OAuth client додати точний redirect URI:

```text
https://backend-hb2j.onrender.com/api/v1/auth/oauth/callback/google
```

Це HTTPS callback backend. Його не потрібно замінювати на `movaquest://`.

### Mobile flow

Застосунок запускає:

```http
GET /api/v1/auth/oauth/mobile/google?redirect_uri=movaquest%3A%2F%2Fauth%2Fcallback
```

Для dev-збірки дозволено `exp+movaquest://auth/callback`.

Після успішного login backend повертає `movaquest://auth/callback?code=<one-time-code>`.

Обмін коду:

```http
POST /api/v1/auth/oauth/exchange
X-Client: mobile
Content-Type: application/json

{"code":"..."}
```

Код одноразовий і діє приблизно 60 секунд.

### Що потрібно отримати від Android/frontend команди

- Android `applicationId` / package name.
- SHA-1 debug certificate.
- SHA-1 release certificate.
- SHA-1 Play App Signing certificate, якщо застосунок опублікований у Google Play.
- Підтвердження deep link: `movaquest://auth/callback`.
- Dev deep link, якщо використовується Expo: `exp+movaquest://auth/callback`.
- Назву Google Cloud project або доступ до нього.
- Підтвердження, що використовується system browser/Expo flow або Google Sign-In SDK.

Android OAuth client створюється з package name + SHA-1. Web OAuth client створюється окремо для backend ([Google client authentication](https://developers.google.com/android/guides/client-auth)).

## Deepgram pronunciation feedback

Endpoint: `POST /api/v1/transcription`.

Multipart fields:

```text
audio=<audio file>
expected_text=<phrase expected from learner>
hint=<word or accepted variant; field may be repeated>
```

Для мобільного аудіо підтримуються `audio/mp4` і m4a.

Відповідь містить `transcript`, загальний `confidence`, word-level `start/end/confidence` і `pronunciation_feedback` зі `score`, `status` та token-level comparison.

Статуси feedback: `good`, `needs_practice`, `not_recognized`.

Score є heuristic на основі текстової схожості та Deepgram confidence, а не фонемною діагностикою. Frontend має узгодити спосіб відображення score і слів для повторення.

## Video storage у PostgreSQL

Відео зберігаються у таблиці `media_videos` як PostgreSQL `BYTEA`. Persistent Disk для відео не використовується.

API:

```http
GET  /api/v1/content/lessons
GET  /api/v1/content/lessons/{lesson_id}
POST /api/v1/content/videos?name=lesson-1.mp4
GET  /api/v1/content/videos
GET  /api/v1/content/videos/lesson-1.mp4
DELETE /api/v1/content/videos/lesson-1.mp4
```

`GET /api/v1/content/lessons` повертає каталог у форматі frontend `index.json`.
Поточний каталог можна імпортувати скриптом `scripts/import_lesson_catalog.py`; імпорт оновлює
існуючі записи за `id` і не видаляє відсутні записи.

Upload/list/delete доступні тільки superuser. Multipart field для upload — `video`.

Підтримуються `.mp4`, `.m4v`, `.mov`, `.webm`. Stream endpoint підтримує HTTP `Range`, `ETag` і `Accept-Ranges`.

Render Postgres має обмежений storage, тому потрібно визначити сумарний розмір відео, перевірити доступне місце та зберігати незалежну копію оригіналів.

## Admin panel і видалення акаунта

Admin panel:

```text
https://backend-hb2j.onrender.com/admin
```

Production admin credentials уже налаштовані в Render. У панелі доступні уроки, відео, користувачі,
ролі, tiers, коментарі/reports та read-only audit log. Upload відео залишається bounded Content API;
адмінка дозволяє перевіряти metadata і видаляти вже завантажені файли.

Видалення власного акаунта:

```http
DELETE /api/v1/users/me
Authorization: Bearer <access_token>
```

Для Google Play ще потрібна публічна frontend-сторінка з описом account deletion.

## Чекліст frontend/mobile

- [ ] Package name збігається з Android OAuth client.
- [ ] Debug/release/Play SHA-1 додані до Google Cloud.
- [ ] Зареєстровано `movaquest://auth/callback`.
- [ ] Access token зберігається у secure device storage.
- [ ] При refresh замінюються access і refresh tokens.
- [ ] Після невдалого refresh застосунок очищає сесію.
- [ ] OAuth code обмінюється через `/auth/oauth/exchange`.
- [ ] Deepgram надсилає `audio/mp4` і `expected_text`.
- [ ] Video player підтримує HTTP Range.
- [ ] Передані реальні відеофайли та їхні lesson IDs.

## Чекліст Render/DevOps

- [ ] Render deploy містить commit `e32b9f8` або новіший.
- [ ] `OAUTH_GOOGLE_CLIENT_ID` — Web OAuth client ID.
- [ ] `OAUTH_GOOGLE_CLIENT_SECRET` встановлений у Render Secrets.
- [ ] `OAUTH_REDIRECT_BASE_URL=https://backend-hb2j.onrender.com`.
- [ ] `OAUTH_ALLOWED_BASE_URLS` містить production backend origin.
- [ ] `DEEPGRAM_API_KEY` встановлений у Render Secrets.
- [ ] Postgres має достатньо місця для `media_videos`.
- [ ] Login, refresh, OAuth exchange, transcription і video stream перевірені після deploy.

## Джерело mobile-вимог

Початкові вимоги описані у `backend-mobile-auth.md`. Цей документ фіксує реалізований backend contract і список даних, які потрібно підтвердити на Android/frontend стороні.
