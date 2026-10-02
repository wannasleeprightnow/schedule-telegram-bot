from datetime import date
import re

from openpyxl.worksheet.worksheet import Worksheet

from src.domain.models import ScheduleChange
from src.infrastructure.google_sheets.parsing import parse_date, text


def parse_changes(sheet: Worksheet) -> tuple[list[ScheduleChange], list[ScheduleChange]]:
    current_date: date | None = None
    changes: list[ScheduleChange] = []
    announcements: list[ScheduleChange] = []
    for row in range(2, sheet.max_row + 1):
        values = [sheet.cell(row, column).value for column in range(1, 9)]
        first_value = values[0]
        parsed = parse_date(first_value) if _is_date_label(first_value) else None
        if parsed:
            current_date = parsed
        info = text(values[4])
        if not info:
            # Some rows have no explicit date but only a public announcement.
            if text(first_value) and not _is_date_label(first_value) and len(text(first_value)) > 20:
                info = text(first_value)
            else:
                info = next((text(value) for value in values if text(value) and len(text(value)) > 35), "")
        if not info or not current_date:
            continue
        effective_date = _explicit_date(info) or current_date
        class_course = text(values[1]) or None
        group = text(values[2]) or None
        time_raw = text(values[3]) or None
        teacher = text(values[5]) or None
        room = text(values[6]) or None
        kind_text = info.casefold()
        kind = (
            "cancellation" if "отмен" in kind_text else
            "merged" if "объедин" in kind_text else
            "replacement" if "вместо" in kind_text or "перенос" in kind_text or re.search(r"\bзамен\w*|замещ\w*", kind_text) else
            "additional" if any(key in kind_text for key in ("дополнительн", "консультац", "экзамен")) else
            "event" if class_course else "announcement"
        )
        change = ScheduleChange(effective_date, class_course, group, time_raw, info, teacher, room, kind, row)
        (changes if class_course else announcements).append(change)
    return changes, announcements


def _is_date_label(value) -> bool:
    if isinstance(value, date):
        return True
    raw = text(value).lower().replace("ё", "е")
    return bool(re.match(r"^(?:с\s*)?\d{1,2}(?:[./-]|\s+[а-яa-z])", raw))


def _explicit_date(value: str) -> date | None:
    raw = text(value).lower()
    if re.search(r"\b\d{1,2}\s*(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\b", raw):
        return parse_date(raw)
    if re.search(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b", raw):
        return parse_date(raw)
    return None
