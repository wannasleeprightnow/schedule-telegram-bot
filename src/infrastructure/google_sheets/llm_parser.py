import json
import logging
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from src.infrastructure.google_sheets.parsing import normalized

logger = logging.getLogger(__name__)


class ParsedAmbiguousRow(BaseModel):
    class_course: str | None = None
    group: str | None = None
    subject: str | None = None
    teacher: str | None = None
    additional_teacher: str | None = None


class LLMParser:
    def __init__(self, api_key: str | None, model: str | None):
        self.api_key = api_key
        self.model = model

    async def parse(self, source_text: str, known_classes: set[str]) -> ParsedAmbiguousRow | None:
        if not self.api_key or not self.model:
            return None
        prompt = (
            "Extract fields explicitly present in this schedule cell. Do not infer or invent missing values. "
            "Return JSON keys class_course, group, subject, teacher, additional_teacher; use null when uncertain. "
            f"Known classes: {sorted(known_classes)}. Cell: {source_text}"
        )
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json={"model": self.model, "messages": [{"role": "user", "content": prompt}], "response_format": {"type": "json_object"}},
                )
                response.raise_for_status()
                raw: Any = response.json()["choices"][0]["message"]["content"]
            logger.debug("LLM input=%r output=%r", source_text, raw)
            data = ParsedAmbiguousRow.model_validate_json(raw)
            source = normalized(source_text)
            if data.class_course and (data.class_course not in known_classes or normalized(data.class_course) not in source):
                data.class_course = None
            for field in ("group", "subject", "teacher", "additional_teacher"):
                value = getattr(data, field)
                if value and normalized(value) not in source:
                    setattr(data, field, None)
            return data
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValidationError, ValueError) as exc:
            logger.warning("LLM-парсер недоступен или вернул неверные данные: %s; исходный текст=%r", exc, source_text)
            return None
