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
- Для Render використовується **Pre-Deploy Command** з міграціями:

  ```bash
  CONFIRM_PRODUCTION_MIGRATION=yes alembic upgrade head
  ```

  Для вже існуючої бази, яку раніше створював `scripts.create_tables`, спочатку виконайте
  `CONFIRM_PRODUCTION_MIGRATION=yes alembic stamp ae2deece1038`, а потім `alembic upgrade head`. Якщо база ще не містить
  актуальних таблиць профілю або прогресу, спочатку застосуйте їх через `scripts.create_tables`
  або окремий schema rollout, а вже після цього stamp-айте baseline.

- Якщо ASR або інші довгі операції працюватимуть через Taskiq, для них потрібно створити окремий Render **Background Worker**, а не виконувати їх у Web Service.

Dockerfile production stage слухає змінну `PORT`, яку задає Render, і має fallback на порт `8000` для локального запуску.

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

### Потік обробки відео

1. Відео завантажується у video hosting або object storage.
2. ASR-сервіс на базі `faster-whisper` генерує транскрипцію іспанською мовою.
3. Backend зберігає метадані відео та результати транскрипції у PostgreSQL.
4. На основі транскрипції формуються слова або навчальні одиниці.
5. `py-fsrs` розраховує наступну дату повторення для кожної вивченої одиниці.

### Еволюція video delivery

Для прототипу допускається простий video hosting, щоб зменшити складність початкової реалізації. У подальшому відео варто винести в object storage з CDN. Це дозволить розділити зберігання та API, зменшити навантаження на backend і забезпечити ефективнішу доставку великих файлів.
