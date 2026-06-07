from __future__ import annotations

import httpx

from app.config import Settings


class LibreTranslateError(RuntimeError):
    pass


class LibreTranslateClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.libretranslate_url.rstrip("/")
        self.timeout = httpx.Timeout(settings.libretranslate_timeout_seconds)

    async def translate(self, text: str, source_language: str, target_language: str = "ru") -> str:
        if not text.strip():
            return ""

        payload: dict[str, str] = {
            "q": text,
            "source": source_language,
            "target": target_language,
            "format": "text",
        }
        if self.settings.libretranslate_api_key:
            payload["api_key"] = self.settings.libretranslate_api_key

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/translate", json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.ConnectError as exc:
            raise LibreTranslateError(
                "Не удалось подключиться к LibreTranslate. Проверь, что сервис запущен и LIBRETRANSLATE_URL указан правильно."
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise LibreTranslateError(f"LibreTranslate вернул HTTP {exc.response.status_code}: {exc.response.text[:500]}") from exc
        except Exception as exc:
            raise LibreTranslateError(f"Ошибка LibreTranslate: {exc}") from exc

        translated = data.get("translatedText")
        if not isinstance(translated, str):
            raise LibreTranslateError(f"LibreTranslate вернул неожиданный ответ: {data}")
        return translated.strip()
