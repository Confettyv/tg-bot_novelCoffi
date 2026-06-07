from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from dotenv import load_dotenv

from app.bot import create_router
from app.config import Settings
from app.db import Database
from app.services.libretranslate import LibreTranslateClient
from app.services.llm import LLMClient
from app.services.translator import TranslationService


async def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    settings = Settings()
    settings.input_dir.mkdir(parents=True, exist_ok=True)
    settings.output_dir.mkdir(parents=True, exist_ok=True)

    db = Database(
        settings.database_path,
        default_translation_mode=settings.default_translation_mode,
        default_llm_provider=settings.llm_provider,
    )
    await db.init()

    llm = LLMClient(settings)
    libretranslate = LibreTranslateClient(settings)
    translator = TranslationService(
        llm=llm,
        libretranslate=libretranslate,
        chunk_max_chars=settings.chunk_max_chars,
    )

    bot = Bot(token=settings.telegram_bot_token)
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="запустить бота"),
            BotCommand(command="menu", description="панель управления"),
            BotCommand(command="status", description="статус последней задачи"),
            BotCommand(command="glossary", description="показать глоссарий"),
            BotCommand(command="help", description="помощь"),
        ]
    )

    dp = Dispatcher()
    dp.include_router(create_router(db, translator, settings))

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
