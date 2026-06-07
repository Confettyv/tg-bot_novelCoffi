from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from app.config import Settings
from app.db import Database, Project
from app.services.translator import TranslationService
from app.text_utils import read_text_safely, safe_filename

logger = logging.getLogger(__name__)

HELP_TEXT = """
Как пользоваться:

1. Открой «Настройки» и выбери режим, LLM, язык и стиль.
2. Добавь термины через /glossary оригинал = перевод.
3. Отправь .txt файл с главой.
4. Бот вернёт готовый перевод файлом.

Основные команды:
/menu — открыть меню
/status — последняя задача
/glossary — глоссарий
/project <название> — новый проект
/help — помощь
""".strip()

START_TEXT = """
NovelCoffi переводит .txt главы новелл на русский.

Рекомендуемый режим для качества:
/mode hybrid + /provider gemini или /provider openai

Загружай только тексты, на перевод которых у тебя есть права.
""".strip()

STYLE_LABELS = {
    "literal": "буквальный",
    "neutral": "нейтральный",
    "literary": "литературный",
    "ranobe": "ранобэ-стиль",
}

LANG_LABELS = {
    "auto": "авто",
    "en": "английский",
    "ja": "японский",
    "ko": "корейский",
}

MODE_LABELS = {
    "free": "free — LibreTranslate",
    "hybrid": "hybrid — черновик + LLM-редактура",
    "quality": "quality — прямой LLM-перевод",
}

PROVIDER_LABELS = {
    "openai": "OpenAI",
    "gemini": "Gemini",
}

JOB_STATUS_LABELS = {
    "queued": "в очереди",
    "running": "в работе",
    "done": "готово",
    "failed": "ошибка",
}

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📤 Перевести главу")],
        [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="📊 Статус")],
        [KeyboardButton(text="📘 Глоссарий"), KeyboardButton(text="❓ Помощь")],
    ],
    resize_keyboard=True,
    input_field_placeholder="Отправь .txt файл или выбери пункт меню",
)


def mark_current(value: str, current: str, label: str) -> str:
    return f"✓ {label}" if value == current else label


def project_summary(project: Project) -> str:
    return (
        f"Проект: {project.title}\n"
        f"Язык: {LANG_LABELS.get(project.source_language, project.source_language)}\n"
        f"Стиль: {STYLE_LABELS.get(project.style_mode, project.style_mode)}\n"
        f"Режим: {MODE_LABELS.get(project.translation_mode, project.translation_mode)}\n"
        f"LLM: {PROVIDER_LABELS.get(project.llm_provider, project.llm_provider)}"
    )


def settings_keyboard(project: Project) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Режим перевода", callback_data="settings:mode")],
            [InlineKeyboardButton(text="LLM-провайдер", callback_data="settings:provider")],
            [InlineKeyboardButton(text="Язык исходника", callback_data="settings:lang")],
            [InlineKeyboardButton(text="Стиль", callback_data="settings:style")],
            [InlineKeyboardButton(text="Глоссарий", callback_data="show:glossary")],
        ]
    )


def mode_keyboard(project: Project) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=mark_current("free", project.translation_mode, "Free — бесплатно, качество ниже"), callback_data="set:mode:free")],
            [InlineKeyboardButton(text=mark_current("hybrid", project.translation_mode, "Hybrid — лучший баланс"), callback_data="set:mode:hybrid")],
            [InlineKeyboardButton(text=mark_current("quality", project.translation_mode, "Quality — максимум качества"), callback_data="set:mode:quality")],
            [InlineKeyboardButton(text="Назад", callback_data="settings:main")],
        ]
    )


def provider_keyboard(project: Project) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=mark_current("gemini", project.llm_provider, "Gemini"), callback_data="set:provider:gemini")],
            [InlineKeyboardButton(text=mark_current("openai", project.llm_provider, "OpenAI"), callback_data="set:provider:openai")],
            [InlineKeyboardButton(text="Назад", callback_data="settings:main")],
        ]
    )


def lang_keyboard(project: Project) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=mark_current("auto", project.source_language, "Автоопределение"), callback_data="set:lang:auto")],
            [InlineKeyboardButton(text=mark_current("en", project.source_language, "English"), callback_data="set:lang:en")],
            [InlineKeyboardButton(text=mark_current("ja", project.source_language, "Japanese"), callback_data="set:lang:ja")],
            [InlineKeyboardButton(text=mark_current("ko", project.source_language, "Korean"), callback_data="set:lang:ko")],
            [InlineKeyboardButton(text="Назад", callback_data="settings:main")],
        ]
    )


def style_keyboard(project: Project) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=mark_current("literary", project.style_mode, "Литературный"), callback_data="set:style:literary")],
            [InlineKeyboardButton(text=mark_current("ranobe", project.style_mode, "Ранобэ-стиль"), callback_data="set:style:ranobe")],
            [InlineKeyboardButton(text=mark_current("neutral", project.style_mode, "Нейтральный"), callback_data="set:style:neutral")],
            [InlineKeyboardButton(text=mark_current("literal", project.style_mode, "Буквальный"), callback_data="set:style:literal")],
            [InlineKeyboardButton(text="Назад", callback_data="settings:main")],
        ]
    )


class JobProcessor:
    def __init__(self, db: Database, translator: TranslationService, settings: Settings):
        self.db = db
        self.translator = translator
        self.settings = settings
        self.semaphore = asyncio.Semaphore(settings.max_parallel_jobs)

    async def run(
        self,
        *,
        bot: Bot,
        chat_id: int,
        status_message_id: int,
        job_id: int,
        project: Project,
        input_path: Path,
        original_file_name: str,
    ) -> None:
        async with self.semaphore:
            try:
                await self.db.update_job(job_id, status="running")
                try:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_message_id,
                        text=(
                            f"Задача #{job_id}\n"
                            f"Файл принят. Перевожу главу.\n\n"
                            f"Режим: {MODE_LABELS.get(project.translation_mode, project.translation_mode)}\n"
                            f"LLM: {PROVIDER_LABELS.get(project.llm_provider, project.llm_provider)}"
                        ),
                    )
                except Exception:
                    logger.debug("Could not edit initial job message", exc_info=True)

                text = read_text_safely(input_path)
                glossary = await self.db.list_glossary(project.id)

                async def progress(done: int, total: int) -> None:
                    await self.db.update_job(
                        job_id,
                        status="running",
                        progress_done=done,
                        progress_total=total,
                    )
                    if done == total or done == 1 or done % 2 == 0:
                        try:
                            await bot.edit_message_text(
                                chat_id=chat_id,
                                message_id=status_message_id,
                                text=f"Задача #{job_id}\nПрогресс: {done}/{total} фрагментов.",
                            )
                        except Exception:
                            logger.debug("Could not edit progress message", exc_info=True)

                result = await self.translator.translate_chapter(
                    text=text,
                    project=project,
                    glossary=glossary,
                    progress=progress,
                )

                output_file = self.settings.output_dir / f"{job_id}_{safe_filename(original_file_name).replace('.txt', '')}_ru.txt"
                output_file.write_text(result.translated_text, encoding="utf-8")

                await self.db.save_chapter(
                    project_id=project.id,
                    title=Path(original_file_name).stem,
                    source_language=result.source_language,
                    original_path=str(input_path),
                    translated_path=str(output_file),
                    summary=result.context_summary,
                )
                await self.db.update_context_summary(project.id, result.context_summary)
                await self.db.update_job(
                    job_id,
                    status="done",
                    progress_done=result.chunks_total,
                    progress_total=result.chunks_total,
                    output_path=str(output_file),
                )

                await bot.send_document(
                    chat_id=chat_id,
                    document=FSInputFile(output_file),
                    caption=(
                        f"Готово. Задача #{job_id}.\n"
                        f"Язык: {LANG_LABELS.get(result.source_language, result.source_language)}\n"
                        f"Режим: {MODE_LABELS.get(result.translation_mode, result.translation_mode)}\n"
                        f"LLM: {PROVIDER_LABELS.get(result.llm_provider, result.llm_provider)}"
                    ),
                )
                try:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_message_id,
                        text=f"Задача #{job_id}: перевод завершён. Файл отправлен.",
                    )
                except Exception:
                    logger.debug("Could not edit completion message", exc_info=True)
            except Exception as exc:
                logger.exception("Translation job failed")
                await self.db.update_job(job_id, status="failed", error_message=str(exc))
                try:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_message_id,
                        text=f"Задача #{job_id}: ошибка перевода. {type(exc).__name__}: {exc}",
                    )
                except Exception:
                    logger.debug("Could not report failed job", exc_info=True)


def create_router(db: Database, translator: TranslationService, settings: Settings) -> Router:
    router = Router()
    processor = JobProcessor(db, translator, settings)

    async def current_project(message: Message) -> Project:
        if not message.from_user:
            raise RuntimeError("Не удалось определить пользователя Telegram.")
        return await db.get_or_create_current_project(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )

    async def current_project_from_callback(callback: CallbackQuery) -> Project:
        if not callback.from_user:
            raise RuntimeError("Не удалось определить пользователя Telegram.")
        return await db.get_or_create_current_project(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
        )

    async def send_project_menu(message: Message) -> None:
        project = await current_project(message)
        await message.answer(
            "Панель управления\n\n" + project_summary(project),
            reply_markup=settings_keyboard(project),
        )

    async def build_status_text(project: Project) -> str:
        job = await db.latest_job(project.id)
        if not job:
            return "Задач перевода пока нет."
        progress = f"{job['progress_done']}/{job['progress_total']}" if job["progress_total"] else "0/0"
        text = (
            f"Последняя задача #{job['id']}\n"
            f"Файл: {job['file_name']}\n"
            f"Статус: {JOB_STATUS_LABELS.get(job['status'], job['status'])}\n"
            f"Прогресс: {progress}"
        )
        if job["error_message"]:
            text += f"\nОшибка: {job['error_message']}"
        return text

    async def build_glossary_text(project: Project) -> str:
        terms = await db.list_glossary(project.id)
        if not terms:
            return (
                "Глоссарий пуст.\n\n"
                "Добавление термина:\n"
                "/glossary Young Master = молодой господин"
            )
        lines = ["Глоссарий:"]
        for term in terms[:50]:
            lines.append(f"• {term['source_term']} = {term['target_term']}")
        if len(terms) > 50:
            lines.append("…показаны первые 50 терминов")
        return "\n".join(lines)

    @router.message(Command("start"))
    async def start(message: Message) -> None:
        await current_project(message)
        await message.answer(START_TEXT, reply_markup=MAIN_KEYBOARD)
        await send_project_menu(message)

    @router.message(Command("menu"))
    async def menu_cmd(message: Message) -> None:
        await send_project_menu(message)

    @router.message(Command("help"))
    async def help_cmd(message: Message) -> None:
        await message.answer(HELP_TEXT, reply_markup=MAIN_KEYBOARD)

    @router.message(F.text == "⚙️ Настройки")
    async def settings_button(message: Message) -> None:
        await send_project_menu(message)

    @router.message(F.text == "📤 Перевести главу")
    async def translate_button(message: Message) -> None:
        project = await current_project(message)
        await message.answer(
            "Отправь .txt файл с главой.\n\nТекущие настройки:\n" + project_summary(project),
            reply_markup=MAIN_KEYBOARD,
        )

    @router.message(F.text == "📊 Статус")
    async def status_button(message: Message) -> None:
        project = await current_project(message)
        await message.answer(await build_status_text(project), reply_markup=MAIN_KEYBOARD)

    @router.message(F.text == "📘 Глоссарий")
    async def glossary_button(message: Message) -> None:
        project = await current_project(message)
        await message.answer(await build_glossary_text(project), reply_markup=MAIN_KEYBOARD)

    @router.message(F.text == "❓ Помощь")
    async def help_button(message: Message) -> None:
        await message.answer(HELP_TEXT, reply_markup=MAIN_KEYBOARD)

    @router.message(Command("project"))
    async def project_cmd(message: Message, command: CommandObject) -> None:
        title = (command.args or "").strip()
        if not title:
            project = await current_project(message)
            await message.answer(project_summary(project), reply_markup=MAIN_KEYBOARD)
            return
        if not message.from_user:
            await message.answer("Не удалось определить пользователя Telegram.")
            return
        project = await db.create_project(message.from_user.id, message.from_user.username, title)
        await message.answer(f"Создан проект: {project.title}", reply_markup=MAIN_KEYBOARD)
        await send_project_menu(message)

    @router.message(Command("lang"))
    async def lang_cmd(message: Message, command: CommandObject) -> None:
        lang = (command.args or "").strip().lower()
        if lang not in LANG_LABELS:
            project = await current_project(message)
            await message.answer("Выбери язык исходника:", reply_markup=lang_keyboard(project))
            return
        project = await current_project(message)
        await db.set_project_language(project.id, lang)
        await message.answer(f"Исходный язык: {LANG_LABELS[lang]}", reply_markup=MAIN_KEYBOARD)

    @router.message(Command("style"))
    async def style_cmd(message: Message, command: CommandObject) -> None:
        style = (command.args or "").strip().lower()
        if style not in STYLE_LABELS:
            project = await current_project(message)
            await message.answer("Выбери стиль:", reply_markup=style_keyboard(project))
            return
        project = await current_project(message)
        await db.set_project_style(project.id, style)
        await message.answer(f"Стиль: {STYLE_LABELS[style]}", reply_markup=MAIN_KEYBOARD)

    @router.message(Command("mode"))
    async def mode_cmd(message: Message, command: CommandObject) -> None:
        mode = (command.args or "").strip().lower()
        if mode not in MODE_LABELS:
            project = await current_project(message)
            await message.answer("Выбери режим перевода:", reply_markup=mode_keyboard(project))
            return
        project = await current_project(message)
        await db.set_project_mode(project.id, mode)
        await message.answer(f"Режим: {MODE_LABELS[mode]}", reply_markup=MAIN_KEYBOARD)

    @router.message(Command("provider"))
    async def provider_cmd(message: Message, command: CommandObject) -> None:
        provider = (command.args or "").strip().lower()
        if provider not in PROVIDER_LABELS:
            project = await current_project(message)
            await message.answer("Выбери LLM-провайдер:", reply_markup=provider_keyboard(project))
            return
        project = await current_project(message)
        await db.set_project_provider(project.id, provider)
        await message.answer(f"LLM: {PROVIDER_LABELS[provider]}", reply_markup=MAIN_KEYBOARD)

    @router.message(Command("glossary"))
    async def glossary_cmd(message: Message, command: CommandObject) -> None:
        project = await current_project(message)
        args = (command.args or "").strip()
        if not args:
            await message.answer(await build_glossary_text(project), reply_markup=MAIN_KEYBOARD)
            return

        if "=>" in args:
            source, target = args.split("=>", 1)
        elif "=" in args:
            source, target = args.split("=", 1)
        else:
            await message.answer("Формат: /glossary оригинал = перевод", reply_markup=MAIN_KEYBOARD)
            return

        source = source.strip()
        target = target.strip()
        if not source or not target:
            await message.answer("Формат: /glossary оригинал = перевод", reply_markup=MAIN_KEYBOARD)
            return
        await db.add_glossary_term(project.id, source, target)
        await message.answer(f"Добавлено: {source} = {target}", reply_markup=MAIN_KEYBOARD)

    @router.message(Command("status"))
    async def status_cmd(message: Message) -> None:
        project = await current_project(message)
        await message.answer(await build_status_text(project), reply_markup=MAIN_KEYBOARD)

    @router.callback_query(F.data == "settings:main")
    async def cb_settings_main(callback: CallbackQuery) -> None:
        project = await current_project_from_callback(callback)
        if callback.message:
            await callback.message.edit_text(
                "Панель управления\n\n" + project_summary(project),
                reply_markup=settings_keyboard(project),
            )
        await callback.answer()

    @router.callback_query(F.data == "settings:mode")
    async def cb_settings_mode(callback: CallbackQuery) -> None:
        project = await current_project_from_callback(callback)
        if callback.message:
            await callback.message.edit_text("Выбери режим перевода:", reply_markup=mode_keyboard(project))
        await callback.answer()

    @router.callback_query(F.data == "settings:provider")
    async def cb_settings_provider(callback: CallbackQuery) -> None:
        project = await current_project_from_callback(callback)
        if callback.message:
            await callback.message.edit_text("Выбери LLM-провайдер:", reply_markup=provider_keyboard(project))
        await callback.answer()

    @router.callback_query(F.data == "settings:lang")
    async def cb_settings_lang(callback: CallbackQuery) -> None:
        project = await current_project_from_callback(callback)
        if callback.message:
            await callback.message.edit_text("Выбери язык исходника:", reply_markup=lang_keyboard(project))
        await callback.answer()

    @router.callback_query(F.data == "settings:style")
    async def cb_settings_style(callback: CallbackQuery) -> None:
        project = await current_project_from_callback(callback)
        if callback.message:
            await callback.message.edit_text("Выбери стиль перевода:", reply_markup=style_keyboard(project))
        await callback.answer()

    @router.callback_query(F.data.startswith("set:"))
    async def cb_set_value(callback: CallbackQuery) -> None:
        data = callback.data or ""
        parts = data.split(":", 2)
        if len(parts) != 3:
            await callback.answer("Некорректное действие", show_alert=True)
            return

        _, field, value = parts
        project = await current_project_from_callback(callback)

        if field == "mode" and value in MODE_LABELS:
            await db.set_project_mode(project.id, value)
        elif field == "provider" and value in PROVIDER_LABELS:
            await db.set_project_provider(project.id, value)
        elif field == "lang" and value in LANG_LABELS:
            await db.set_project_language(project.id, value)
        elif field == "style" and value in STYLE_LABELS:
            await db.set_project_style(project.id, value)
        else:
            await callback.answer("Некорректное значение", show_alert=True)
            return

        updated_project = await current_project_from_callback(callback)
        if callback.message:
            await callback.message.edit_text(
                "Настройки обновлены\n\n" + project_summary(updated_project),
                reply_markup=settings_keyboard(updated_project),
            )
        await callback.answer("Сохранено")

    @router.callback_query(F.data == "show:glossary")
    async def cb_show_glossary(callback: CallbackQuery) -> None:
        project = await current_project_from_callback(callback)
        if callback.message:
            await callback.message.edit_text(
                await build_glossary_text(project),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="settings:main")]]
                ),
            )
        await callback.answer()

    @router.message(F.document)
    async def document_handler(message: Message, bot: Bot) -> None:
        if not message.from_user or not message.document:
            return

        document = message.document
        file_name = document.file_name or "chapter.txt"
        if not file_name.lower().endswith(".txt"):
            await message.answer("Сейчас MVP принимает только .txt файлы.", reply_markup=MAIN_KEYBOARD)
            return
        if document.file_size and document.file_size > settings.max_download_bytes:
            await message.answer(
                f"Файл слишком большой для MVP: максимум {settings.max_download_mb} MB. "
                "Раздели книгу на главы или уменьши файл.",
                reply_markup=MAIN_KEYBOARD,
            )
            return

        project = await current_project(message)
        settings.input_dir.mkdir(parents=True, exist_ok=True)
        settings.output_dir.mkdir(parents=True, exist_ok=True)

        input_path = settings.input_dir / f"{message.from_user.id}_{document.file_unique_id}_{safe_filename(file_name)}"
        await bot.download(document, destination=input_path)

        job_id = await db.create_job(project.id, message.from_user.id, file_name)
        # This message will be edited while the job is running.
        # Do not attach ReplyKeyboardMarkup to an editable message: Telegram can reject such edits.
        status_message = await message.answer(
            f"Задача #{job_id} добавлена в очередь.\nФайл: {file_name}"
        )

        asyncio.create_task(
            processor.run(
                bot=bot,
                chat_id=message.chat.id,
                status_message_id=status_message.message_id,
                job_id=job_id,
                project=project,
                input_path=input_path,
                original_file_name=file_name,
            )
        )

    @router.message()
    async def fallback(message: Message) -> None:
        await message.answer("Отправь .txt файл или открой /menu.", reply_markup=MAIN_KEYBOARD)

    return router
