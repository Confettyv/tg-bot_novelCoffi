from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiosqlite


@dataclass(slots=True)
class Project:
    id: int
    user_id: int
    title: str
    source_language: str
    target_language: str
    style_mode: str
    translation_mode: str
    llm_provider: str
    context_summary: str


class Database:
    def __init__(self, path: Path, default_translation_mode: str = "hybrid", default_llm_provider: str = "openai"):
        self.path = Path(path)
        self.default_translation_mode = default_translation_mode if default_translation_mode in {"free", "hybrid", "quality"} else "hybrid"
        self.default_llm_provider = default_llm_provider if default_llm_provider in {"openai", "gemini"} else "openai"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def connect(self):
        db = await aiosqlite.connect(self.path)
        try:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys = ON")
            yield db
        finally:
            await db.close()

    async def init(self) -> None:
        async with self.connect() as db:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL UNIQUE,
                    username TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    source_language TEXT NOT NULL DEFAULT 'auto',
                    target_language TEXT NOT NULL DEFAULT 'ru',
                    style_mode TEXT NOT NULL DEFAULT 'literary',
                    translation_mode TEXT NOT NULL DEFAULT 'hybrid',
                    llm_provider TEXT NOT NULL DEFAULT 'openai',
                    context_summary TEXT NOT NULL DEFAULT '',
                    is_current INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS glossary_terms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    source_term TEXT NOT NULL,
                    target_term TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(project_id, source_term),
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS chapters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    source_language TEXT NOT NULL,
                    original_path TEXT NOT NULL,
                    translated_path TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS translation_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    telegram_id INTEGER NOT NULL,
                    file_name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    progress_done INTEGER NOT NULL DEFAULT 0,
                    progress_total INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT NOT NULL DEFAULT '',
                    output_path TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
                );
                """
            )
            await self._migrate(db)
            await db.commit()

    async def _migrate(self, db: aiosqlite.Connection) -> None:
        project_columns = await db.execute_fetchall("PRAGMA table_info(projects)")
        project_column_names = {str(row["name"]) for row in project_columns}
        if "translation_mode" not in project_column_names:
            await db.execute("ALTER TABLE projects ADD COLUMN translation_mode TEXT NOT NULL DEFAULT 'hybrid'")
        if "llm_provider" not in project_column_names:
            await db.execute("ALTER TABLE projects ADD COLUMN llm_provider TEXT NOT NULL DEFAULT 'openai'")
            if self.default_llm_provider != "openai":
                await db.execute("UPDATE projects SET llm_provider = ?", (self.default_llm_provider,))

    async def upsert_user(self, telegram_id: int, username: str | None) -> int:
        async with self.connect() as db:
            await db.execute(
                """
                INSERT INTO users (telegram_id, username)
                VALUES (?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET username = excluded.username
                """,
                (telegram_id, username),
            )
            await db.commit()
            row = await db.execute_fetchall(
                "SELECT id FROM users WHERE telegram_id = ?",
                (telegram_id,),
            )
            return int(row[0]["id"])

    async def get_or_create_current_project(self, telegram_id: int, username: str | None = None) -> Project:
        user_id = await self.upsert_user(telegram_id, username)
        async with self.connect() as db:
            rows = await db.execute_fetchall(
                """
                SELECT * FROM projects
                WHERE user_id = ? AND is_current = 1
                ORDER BY id DESC
                LIMIT 1
                """,
                (user_id,),
            )
            if rows:
                return self._project_from_row(rows[0])

            cursor = await db.execute(
                """
                INSERT INTO projects (user_id, title, source_language, target_language, style_mode, translation_mode, llm_provider, is_current)
                VALUES (?, 'Default Novel', 'auto', 'ru', 'literary', ?, ?, 1)
                """,
                (user_id, self.default_translation_mode, self.default_llm_provider),
            )
            await db.commit()
            rows = await db.execute_fetchall("SELECT * FROM projects WHERE id = ?", (cursor.lastrowid,))
            return self._project_from_row(rows[0])

    async def create_project(self, telegram_id: int, username: str | None, title: str) -> Project:
        user_id = await self.upsert_user(telegram_id, username)
        async with self.connect() as db:
            await db.execute("UPDATE projects SET is_current = 0 WHERE user_id = ?", (user_id,))
            cursor = await db.execute(
                """
                INSERT INTO projects (user_id, title, source_language, target_language, style_mode, translation_mode, llm_provider, is_current)
                VALUES (?, ?, 'auto', 'ru', 'literary', ?, ?, 1)
                """,
                (user_id, title.strip() or "Untitled Novel", self.default_translation_mode, self.default_llm_provider),
            )
            await db.commit()
            rows = await db.execute_fetchall("SELECT * FROM projects WHERE id = ?", (cursor.lastrowid,))
            return self._project_from_row(rows[0])

    async def set_project_language(self, project_id: int, source_language: str) -> None:
        async with self.connect() as db:
            await db.execute(
                "UPDATE projects SET source_language = ? WHERE id = ?",
                (source_language, project_id),
            )
            await db.commit()

    async def set_project_style(self, project_id: int, style_mode: str) -> None:
        async with self.connect() as db:
            await db.execute(
                "UPDATE projects SET style_mode = ? WHERE id = ?",
                (style_mode, project_id),
            )
            await db.commit()

    async def set_project_mode(self, project_id: int, translation_mode: str) -> None:
        async with self.connect() as db:
            await db.execute(
                "UPDATE projects SET translation_mode = ? WHERE id = ?",
                (translation_mode, project_id),
            )
            await db.commit()

    async def set_project_provider(self, project_id: int, llm_provider: str) -> None:
        async with self.connect() as db:
            await db.execute(
                "UPDATE projects SET llm_provider = ? WHERE id = ?",
                (llm_provider, project_id),
            )
            await db.commit()

    async def update_context_summary(self, project_id: int, context_summary: str) -> None:
        async with self.connect() as db:
            await db.execute(
                "UPDATE projects SET context_summary = ? WHERE id = ?",
                (context_summary[:6000], project_id),
            )
            await db.commit()

    async def add_glossary_term(self, project_id: int, source_term: str, target_term: str, note: str = "") -> None:
        async with self.connect() as db:
            await db.execute(
                """
                INSERT INTO glossary_terms (project_id, source_term, target_term, note)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(project_id, source_term)
                DO UPDATE SET target_term = excluded.target_term, note = excluded.note
                """,
                (project_id, source_term.strip(), target_term.strip(), note.strip()),
            )
            await db.commit()

    async def list_glossary(self, project_id: int, limit: int = 80) -> list[dict[str, Any]]:
        async with self.connect() as db:
            rows = await db.execute_fetchall(
                """
                SELECT source_term, target_term, note FROM glossary_terms
                WHERE project_id = ?
                ORDER BY source_term COLLATE NOCASE
                LIMIT ?
                """,
                (project_id, limit),
            )
            return [dict(row) for row in rows]

    async def create_job(self, project_id: int, telegram_id: int, file_name: str) -> int:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                INSERT INTO translation_jobs (project_id, telegram_id, file_name, status)
                VALUES (?, ?, ?, 'queued')
                """,
                (project_id, telegram_id, file_name),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def update_job(
        self,
        job_id: int,
        *,
        status: str | None = None,
        progress_done: int | None = None,
        progress_total: int | None = None,
        error_message: str | None = None,
        output_path: str | None = None,
    ) -> None:
        fields: list[str] = ["updated_at = CURRENT_TIMESTAMP"]
        values: list[Any] = []
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if progress_done is not None:
            fields.append("progress_done = ?")
            values.append(progress_done)
        if progress_total is not None:
            fields.append("progress_total = ?")
            values.append(progress_total)
        if error_message is not None:
            fields.append("error_message = ?")
            values.append(error_message[:2000])
        if output_path is not None:
            fields.append("output_path = ?")
            values.append(output_path)
        values.append(job_id)

        async with self.connect() as db:
            await db.execute(f"UPDATE translation_jobs SET {', '.join(fields)} WHERE id = ?", values)
            await db.commit()

    async def latest_job(self, project_id: int) -> dict[str, Any] | None:
        async with self.connect() as db:
            rows = await db.execute_fetchall(
                """
                SELECT * FROM translation_jobs
                WHERE project_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (project_id,),
            )
            return dict(rows[0]) if rows else None

    async def save_chapter(
        self,
        project_id: int,
        title: str,
        source_language: str,
        original_path: str,
        translated_path: str,
        summary: str,
    ) -> int:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                INSERT INTO chapters (project_id, title, source_language, original_path, translated_path, summary)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (project_id, title, source_language, original_path, translated_path, summary[:6000]),
            )
            await db.commit()
            return int(cursor.lastrowid)

    @staticmethod
    def _project_from_row(row: aiosqlite.Row) -> Project:
        return Project(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            title=str(row["title"]),
            source_language=str(row["source_language"]),
            target_language=str(row["target_language"]),
            style_mode=str(row["style_mode"]),
            translation_mode=str(row["translation_mode"]),
            llm_provider=str(row["llm_provider"]),
            context_summary=str(row["context_summary"]),
        )
