import re
from datetime import date, datetime, time
from typing import Any

MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5,
    "июня": 6, "июля": 7, "августа": 8, "сентября": 9, "октября": 10,
    "ноября": 11, "декабря": 12,
}
WEEKDAYS = {"понедельник": 0, "вторник": 1, "среда": 2, "четверг": 3, "пятница": 4, "суббота": 5, "воскресенье": 6}
TIME_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3])[:.](\d{2})(?!\d)")
CLASS_RE = re.compile(r"^(?:(?:[1-5]\s*\(\s*\d+\s*\)|[1-5]\s*курс|[IVX]+\s*\(\s*\d+\s*\)\s*курс|[IVX]+\s*курс|\d+\s*А|\d+\s*Б))", re.I)


def text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def parse_time_range(value: Any) -> tuple[time | None, time | None]:
    if isinstance(value, datetime):
        return value.time().replace(second=0, microsecond=0), None
    if isinstance(value, time):
        return value.replace(second=0, microsecond=0), None
    if not isinstance(value, str):
        return None, None
    matches = list(TIME_RE.finditer(value))
    if not matches:
        return None, None
    try:
        if len(matches) == 1:
            return time(int(matches[0].group(1)), int(matches[0].group(2))), None
        return time(int(matches[0].group(1)), int(matches[0].group(2))), time(int(matches[1].group(1)), int(matches[1].group(2)))
    except ValueError:
        return None, None


def parse_date(value: Any, year_hint: int = 2026) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = text(value).lower().replace("ё", "е").translate(str.maketrans({"c": "с", "e": "е", "a": "а", "o": "о", "p": "р"}))
    numeric = re.search(r"\b(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?\b", raw)
    if numeric:
        day, month = int(numeric.group(1)), int(numeric.group(2))
        year = int(numeric.group(3)) if numeric.group(3) else (year_hint + 1 if month < 8 and year_hint == 2026 else year_hint)
        if year < 100:
            year += 2000
        try:
            return date(year, month, day)
        except ValueError:
            return None
    for month_name, month in MONTHS.items():
        match = re.search(rf"\b(\d{{1,2}})\s*(?:-\s*\d{{1,2}}\s*)?{month_name}\b", raw)
        if match:
            try:
                year = year_hint + 1 if month < 8 and year_hint == 2026 else year_hint
                return date(year, month, int(match.group(1)))
            except ValueError:
                return None
    return None


def parse_integer(value: Any) -> int | None:
    if value is None:
        return None
    match = re.search(r"\d+", str(value))
    return int(match.group()) if match else None


def split_subject_teacher(value: Any) -> tuple[str, str | None, str | None]:
    raw = text(value)
    if not raw:
        return "", None, None
    teacher = None
    # Parenthesized final part is the workbook's most common teacher notation.
    match = re.search(r"\(([^()]*(?:[А-ЯЁ][а-яё-]+\s+[А-ЯЁ]\.\s*[А-ЯЁ]?\.?)?[^()]*)\)\s*$", raw)
    if match:
        candidate = text(match.group(1))
        if re.search(r"[А-ЯЁ]\.\s*[А-ЯЁ]?\.?", candidate):
            teacher = candidate
            raw = text(raw[:match.start()])
    if not teacher:
        names = re.findall(r"[А-ЯЁ][а-яё-]+\s+[А-ЯЁ]\.\s*[А-ЯЁ]?\.?", raw)
        if names:
            teacher = ", ".join(dict.fromkeys(names))
            raw = text(re.sub(r"\s*\([^)]*\)\s*$", "", raw))
    room = None
    return raw or text(value), teacher, room


def weekday_number(value: Any) -> int | None:
    raw = text(value).lower().replace("ё", "е")
    return next((day for name, day in WEEKDAYS.items() if name in raw), None)


def is_class_header(value: Any) -> bool:
    raw = text(value)
    return bool(CLASS_RE.match(raw))


def normalized(value: str) -> str:
    return re.sub(r"[^a-zа-яё0-9]+", "", value.casefold().replace("ё", "е"))
