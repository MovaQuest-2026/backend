# MovaQuest Backend

## Архітектура

Проєкт планується будувати на основі готового шаблону [FastAPI Boilerplate](https://github.com/benavlabs/FastAPI-boilerplate). Шаблон використовується як стартова основа для базових налаштувань автентифікації та авторизації. Для MovaQuest database layer переведений на синхронний SQLAlchemy Engine/Session з PostgreSQL-драйвером `psycopg2`; FastAPI/CRUD-контракт шаблону збережений через сумісний session adapter.

### Стартовий шаблон у репозиторії

Шаблон уже перенесено в цей репозиторій як основу проєкту. Його код не додається вкладеним Git-репозиторієм: файли шаблону знаходяться безпосередньо в корені MovaQuest, а власна історія Git цього проєкту зберігається.

Поточна структура:

```text
.
├── backend/       # FastAPI-застосунок, SQLAlchemy, Alembic, тести
├── cli/           # CLI-команди boilerplate
├── docs/          # документація шаблону
├── tools/         # допоміжні інструменти
├── pyproject.toml # uv workspace
└── uv.lock        # зафіксовані залежності
```

Для локального запуску потрібні Python 3.11+ та `uv`:

```bash
uv sync --all-packages --all-extras
uv run --no-sync bp deploy generate local
docker compose up --build
```

Після запуску API доступне за адресою `http://127.0.0.1:8000`, Swagger UI — за адресою `http://127.0.0.1:8000/docs`.

### Deployment на Render

Production deployment планується виконувати на Render:

- **Web Service** запускає Dockerfile зі stage `prod`.
- **Render Postgres** використовується як production database.
- `DATABASE_URL` передається через Environment Variables Render; для сервісу всередині Render потрібно використовувати internal database URL. Оскільки database layer синхронний, URL має використовувати драйвер `postgresql+psycopg2://`.
- Для Render production Docker image застосовує міграції перед стартом API:

  ```bash
  CONFIRM_PRODUCTION_MIGRATION=yes alembic upgrade head
  ```

  Команда вбудована в `prod` stage `backend/Dockerfile`, тому окреме поле Pre-Deploy Command на Free-плані не потрібне.
  Якщо міграція завершується помилкою, FastAPI не запускається.

  Для вже існуючої бази, яку раніше створював `scripts.create_tables`, спочатку виконайте
  `CONFIRM_PRODUCTION_MIGRATION=yes alembic stamp ae2deece1038`, а потім `alembic upgrade head`. Якщо база ще не містить
  актуальних таблиць профілю або прогресу, спочатку застосуйте їх через `scripts.create_tables`
  або окремий schema rollout, а вже після цього stamp-айте baseline.

- Якщо ASR або інші довгі операції працюватимуть через Taskiq, для них потрібно створити окремий Render **Background Worker**, а не виконувати їх у Web Service.

Dockerfile production stage слухає змінну `PORT`, яку задає Render, і має fallback на порт `8000` для локального запуску.

Відео зберігаються у PostgreSQL у таблиці `media_videos` як `BYTEA`; локальна файлова система Render для цього не використовується.
Content API має `POST /api/v1/content/videos?name=lesson-1.mp4` (тільки superuser),
`GET /api/v1/content/videos/{name}` для потокової роздачі та `DELETE /api/v1/content/videos/{name}`.
Розмір upload обмежується `MEDIA_MAX_FILE_BYTES`, а stream endpoint підтримує один HTTP byte range.
Для цього варіанту потрібно збільшити план/диск Render Postgres так, щоб у базі вистачило місця.

Каталог уроків доступний через `GET /api/v1/content/lessons` і повертається у frontend-сумісному форматі
з `title`/`description` для `es`, `en`, `uk`, `durationSec`, `cover`, `comingSoon` та optional `videoUrl`.
Імпорт наданого frontend `index.json` виконується ідемпотентно:

```powershell
cd backend
uv run python scripts/import_lesson_catalog.py "C:\path\to\index.json"
```

Відсутні у джерелі уроки не видаляються автоматично. Відеофайли імпортуються окремо після перевірки архіву.

Приклади конфігурації збережені у `backend/.env.example` для локального середовища та `backend/.env.render.example` для Render. Реальний `backend/.env` використовується тільки локально й ігнорується Git.

### Основні компоненти

| Компонент | Технологія | Призначення |
| --- | --- | --- |
| Backend | FastAPI (Python) | REST API, бізнес-логіка та інтеграція сервісів |
| Database | PostgreSQL | Основне зберігання користувачів, курсів, відео, слів і прогресу |
| ORM та міграції | SQLAlchemy + Alembic | Робота з даними та версіонування схеми бази даних |
| Video delivery | Object Storage + CDN | Масштабована доставка відео; на етапі прототипу — простий video hosting |
| ASR | faster-whisper | Транскрипція іспанської мови у відео |
| Spaced repetition | py-fsrs | Планування повторення вивчених слів |

### Мобільна автентифікація та адмінпанель

`POST /api/v1/auth/login` з заголовком `X-Client: mobile` повертає access/refresh JWT без cookie. Access-токен
діє 1 годину; refresh-токен — 60 днів, зберігається на бекенді лише як SHA-256 хеш і одноразово ротуються через
`POST /api/v1/auth/refresh`. Мобільні запити до існуючих захищених endpoint-ів використовують
`Authorization: Bearer <access_token>`. Веблогін без цього заголовка лишається cookie-based. `POST /api/v1/auth/logout`
з Bearer може прийняти `{"refresh_token": "…"}` і відкликати саме цей refresh-токен.

Мобільний Google OAuth запускається через `GET /api/v1/auth/oauth/mobile/google?redirect_uri=movaquest%3A%2F%2Fauth%2Fcallback`
(для dev-збірки дозволено `exp+movaquest://auth/callback`). Google повертає користувача на штатний backend callback,
який завершує web-сесію у системному браузері; backend перенаправляє на deep link з одноразовим кодом на 60 секунд.
Застосунок обмінює його через `POST /api/v1/auth/oauth/exchange` з `X-Client: mobile` і тілом `{"code":"…"}`.
Google redirect URI не змінюється. Помилки OAuth від callback поки ведуть на стандартний frontend redirect.

Адмінпанель і керування користувачами вже реалізовані. Для production панель монтується тільки коли задані
`ADMIN_ENABLED=true`, `ADMIN_USERNAME` та сильний `ADMIN_PASSWORD`; URL за замовчуванням — `/admin`.
У панелі доступні уроки, відео, користувачі, ролі, tiers, коментарі/reports та read-only audit log.

### Потік обробки відео

1. Відео завантажується у video hosting або object storage.
2. ASR-сервіс на базі `faster-whisper` генерує транскрипцію іспанською мовою.
3. Backend зберігає метадані відео та результати транскрипції у PostgreSQL.
4. На основі транскрипції формуються слова або навчальні одиниці.
5. `py-fsrs` розраховує наступну дату повторення для кожної вивченої одиниці.

### Deepgram: фідбек по вимові

`POST /api/v1/transcription` приймає multipart `audio`, повторювані `hint` і необов'язковий
`expected_text`. Відповідь містить транскрипцію, загальний та word-level confidence, таймінги
і `pronunciation_feedback` з token-level збігами та score. Score є explainable heuristic для
навчального фідбеку на основі схожості тексту й confidence Deepgram; Deepgram сам по собі не
повертає фонемний діагноз вимови. Для точнішої фонемної оцінки потрібен окремий pronunciation
assessment engine або спеціально підібрана модель.

`POST /api/v1/transcription` уже повертає транскрипт, загальну confidence, а також confidence і часові мітки
для кожного розпізнаного слова. Це корисний сигнал про впевненість ASR, але він не є оцінкою якості вимови або
фонетичним порівнянням із еталоном. Deepgram Nova-3 STT не надає окремий pronunciation score; для навчального
фідбеку потрібно порівнювати транскрипт з очікуваною фразою у застосунку або підключити pronunciation assessment.
Endpoint приймає `audio/mp4`/`audio/m4a` разом з іншими `audio/*` MIME типами та передає отриманий MIME у Deepgram.

### Еволюція video delivery

Для прототипу допускається простий video hosting, щоб зменшити складність початкової реалізації. У подальшому відео варто винести в object storage з CDN. Це дозволить розділити зберігання та API, зменшити навантаження на backend і забезпечити ефективнішу доставку великих файлів.
