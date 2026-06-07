# Размещение Telegram-бота для новичка

Этот бот использует polling. Это самый простой способ запуска: бот сам постоянно спрашивает Telegram, есть ли новые сообщения. Для polling не нужен домен, HTTPS и настройка webhook.

## Часть 1. Создание бота в Telegram

1. Открой Telegram.
2. Найди официального бота `@BotFather`.
3. Напиши:

```text
/newbot
```

4. Введи обычное имя бота, например:

```text
Novel Translator
```

5. Введи username. Он должен заканчиваться на `bot`, например:

```text
my_novel_translator_bot
```

6. BotFather выдаст токен вида:

```text
1234567890:ABCDEF_xxxxxxxxx
```

Этот токен нельзя публиковать. Он нужен в `.env`.

## Часть 2. Локальный запуск на компьютере

### 1. Установи Python

Проверь:

```bash
python --version
```

или:

```bash
python3 --version
```

Нужен Python 3.11 или новее.

### 2. Распакуй проект

```bash
cd путь/до/novel_translator_bot
```

### 3. Создай виртуальное окружение

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 4. Установи зависимости

```bash
pip install -r requirements.txt
```

### 5. Создай `.env`

macOS/Linux:

```bash
cp .env.example .env
```

Windows:

```powershell
copy .env.example .env
```

Заполни:

```env
TELEGRAM_BOT_TOKEN=твой_токен_от_BotFather
LLM_PROVIDER=gemini
GEMINI_API_KEY=твой_gemini_api_key
GEMINI_MODEL=gemini-3.1-flash-lite

# Если хочешь OpenAI вместо Gemini:
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5-mini

LIBRETRANSLATE_URL=http://127.0.0.1:5001
DEFAULT_TRANSLATION_MODE=hybrid
```

Для полностью бесплатного режима:

```env
OPENAI_API_KEY=
GEMINI_API_KEY=
DEFAULT_TRANSLATION_MODE=free
```

### 6. Запусти LibreTranslate

В отдельном терминале:

```bash
pip install libretranslate
libretranslate --host 127.0.0.1 --port 5001 --load-only en,ja,ko,ru
```

Оставь этот терминал открытым.

### 7. Запусти бота

В терминале проекта:

```bash
python main.py
```

Оставь терминал открытым. Если закрыть терминал, бот перестанет отвечать.

## Часть 3. Проверка в Telegram

Открой своего бота и отправь:

```text
/start
```

Потом:

```text
/project Test Novel
/lang auto
/style literary
/mode hybrid
/provider gemini
```

Для бесплатной проверки:

```text
/mode free
```

Отправь маленький `.txt` файл.

## Часть 4. Размещение 24/7 на сервере

Если бот должен работать всегда, нужен сервер. Самый понятный вариант — VPS + Docker Compose.

### Общая схема

```text
Твой компьютер → загружаешь проект на VPS → запускаешь docker compose → бот работает 24/7
```

### Команды на сервере

Установи Docker по инструкции хостинга, затем загрузи папку проекта на сервер и выполни:

```bash
cd novel_translator_bot
cp .env.example .env
nano .env
```

Заполни `.env`, затем:

```bash
docker compose up -d --build
```

Проверить логи:

```bash
docker compose logs -f novel-translator-bot
```

Остановить:

```bash
docker compose down
```

Перезапустить:

```bash
docker compose restart
```

## Частые проблемы

### Бот не отвечает

Проверь:

1. Запущен ли `python main.py` или `docker compose up`.
2. Верный ли `TELEGRAM_BOT_TOKEN`.
3. Не вставлен ли токен с пробелами или кавычками.

### Ошибка LibreTranslate

Проверь, открыт ли адрес:

```text
http://127.0.0.1:5001
```

Если бот запущен через Docker Compose, внутри контейнера используется:

```text
http://libretranslate:5000
```

### Ошибка OpenAI API

Для `/mode hybrid` и `/mode quality` нужен `OPENAI_API_KEY`.
Если ключа нет, используй:

```text
/mode free
```

### Бот работает только когда включён компьютер

Это нормально для локального запуска. Для постоянной работы нужен сервер/VPS.
