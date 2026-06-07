# Novel Translator Telegram Bot

MVP Telegram-бота для перевода корейских, японских и английских новелл на русский язык.

## Что умеет

- принимает `.txt` файл с главой;
- определяет язык автоматически или использует выбранный язык проекта;
- делит главу на смысловые фрагменты;
- хранит глоссарий имён, терминов и обращений;
- хранит краткий контекст между фрагментами и главами;
- возвращает готовый `.txt` файл с переводом;
- хранит проекты, глоссарий и статусы задач в SQLite;
- поддерживает 3 режима перевода:
  - `free` — LibreTranslate без оплаты за API;
  - `quality` — прямой литературный перевод через выбранный LLM-провайдер;
  - `hybrid` — LibreTranslate делает бесплатный черновик, выбранный LLM делает литературную редактуру;
- поддерживает переключатель LLM-провайдера: `openai` или `gemini`.

## Стек

- Python 3.11+
- aiogram 3
- SQLite через aiosqlite
- LibreTranslate API
- OpenAI Responses API для провайдера `openai`
- Gemini API через OpenAI-compatible endpoint для провайдера `gemini`

## Управление в Telegram

В интерфейсе бота оставлены только основные команды:

```text
/start — запустить бота
/menu — открыть панель управления
/status — последняя задача
/glossary — глоссарий
/help — помощь
```

Настройки режима, LLM-провайдера, языка и стиля теперь выбираются кнопками через `/menu`.
Старые команды `/mode`, `/provider`, `/lang` и `/style` сохранены как быстрые команды для продвинутого использования, но не показываются в меню команд Telegram.

## Режимы перевода

| Режим | Как работает | Цена | Качество |
|---|---|---:|---|
| `free` | Только LibreTranslate | $0 за API | Машинный перевод, слабее для новелл |
| `hybrid` | LibreTranslate черновик → выбранный LLM редактирует | дешевле полного LLM-перевода | Хороший баланс |
| `quality` | выбранный LLM переводит напрямую | дороже | Лучшее качество в этом MVP |

LLM-провайдер выбирается отдельно:

```text
/provider openai
/provider gemini
```

## Быстрый запуск локально

### 1. Создать Telegram-бота

В Telegram открой `@BotFather`:

```text
/newbot
```

Скопируй токен и вставь его в `.env`.

### 2. Запустить LibreTranslate

В отдельном терминале можно запустить через Python:

```bash
pip install libretranslate
libretranslate --load-only en,ja,ko,ru
```

После запуска проверь в браузере:

```text
http://localhost:5000
```

Или запусти всё через Docker Compose — тогда отдельный запуск LibreTranslate не нужен.

### 3. Запустить бота локально

```bash
cd novel_translator_bot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Для Windows PowerShell:

```powershell
cd novel_translator_bot
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Заполни `.env`:

```env
TELEGRAM_BOT_TOKEN=токен_от_BotFather

LLM_PROVIDER=gemini
GEMINI_API_KEY=твой_gemini_api_key
GEMINI_MODEL=gemini-3.1-flash-lite

# Можно оставить пустым, если используешь только Gemini.
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5-mini

LIBRETRANSLATE_URL=http://127.0.0.1:5001
DEFAULT_TRANSLATION_MODE=hybrid
```

Если нужен только бесплатный режим:

```env
OPENAI_API_KEY=
GEMINI_API_KEY=
DEFAULT_TRANSLATION_MODE=free
```

Запуск:

```bash
python main.py
```

## Запуск через Docker Compose

```bash
cp .env.example .env
# заполни TELEGRAM_BOT_TOKEN и GEMINI_API_KEY или OPENAI_API_KEY, если нужен hybrid/quality

docker compose up --build
```

В Docker Compose поднимаются два сервиса:

- `novel-translator-bot` — Telegram-бот;
- `libretranslate` — локальный бесплатный переводчик.

## Первый сценарий в Telegram

```text
/start
/menu
```

В панели управления выбери:

```text
Режим: hybrid
LLM: gemini или openai
Язык: auto
Стиль: literary или ranobe
```

Создать отдельный проект можно командой:

```text
/project Shadow Academy
```

Добавить термины:

```text
/glossary Young Master = молодой господин
/glossary Sect Master = глава секты
```

После этого отправь `.txt` файл с главой.

## Как разместить бота 24/7

Для новичка проще всего использовать polling. В этом режиме не нужен домен, HTTPS и webhook. Достаточно, чтобы процесс `python main.py` постоянно работал на сервере.

Минимальная схема:

```text
Telegram BotFather → токен → .env → сервер/VPS → python main.py или docker compose up
```

Для первого деплоя проще использовать VPS с Docker:

1. Купить/получить VPS.
2. Установить Docker и Docker Compose.
3. Загрузить проект на сервер.
4. Заполнить `.env`.
5. Запустить `docker compose up -d --build`.
6. Проверить бота командой `/start`.

## Ограничения MVP

- Только `.txt`.
- Нет EPUB/PDF/OCR.
- Нет парсинга сайтов.
- Бесплатный режим даёт машинный перевод, а не полноценную литературную адаптацию.
- В `hybrid` и `quality` нужен ключ выбранного провайдера: `GEMINI_API_KEY` или `OPENAI_API_KEY`.
- Файл для скачивания ботом ограничен настройкой `MAX_DOWNLOAD_MB`. По умолчанию стоит 18 MB.
- Фоновые задачи выполняются внутри процесса. Для продакшена лучше вынести их в Redis + worker.

## Юридическая оговорка

Используй бота для личного перевода, собственных текстов, public domain или материалов, на перевод которых у пользователя есть права. Не стоит делать публичное распространение переводов защищённых новелл без разрешения правообладателя.
