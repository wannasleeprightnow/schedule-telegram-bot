import asyncio
import logging
import re
from datetime import date

from src.domain.models import Schedule, ScheduleLesson, WorkbookData
from src.domain.services import build_schedule
from src.infrastructure.cache.workbook_cache import WorkbookCache
from src.infrastructure.google_sheets.parsing import normalized, parse_time_range
from src.infrastructure.google_sheets.workbook_parser import parse_workbook

logger = logging.getLogger(__name__)


class ScheduleService:
    def __init__(self, cache: WorkbookCache):
        self.cache = cache
        self._parse_lock = asyncio.Lock()
        self._parsed_hash: str | None = None
        self._workbook: WorkbookData | None = None

    async def get_schedule(self, requested_date: date, class_course: str, group: str | None = None, gender: str | None = None) -> Schedule:
        cached = await self.cache.get()
        async with self._parse_lock:
            if self._parsed_hash != cached.sha256 or self._workbook is None:
                try:
                    self._workbook = await asyncio.to_thread(parse_workbook, str(cached.path))
                except Exception:
                    logger.exception("Ошибка разбора книги расписания")
                    raise
                self._parsed_hash = cached.sha256
        if not _known_class(class_course, self._workbook.available_classes):
            raise ValueError(f"Класс/курс «{class_course}» отсутствует в расписании")
        schedule = build_schedule(
            requested_date,
            class_course,
            group,
            self._workbook.lessons,
            self._workbook.changes,
            self._workbook.announcements,
        )
        self._assign_rooms(schedule, self._workbook, gender)
        schedule.stale = cached.stale
        logger.info("Расписание собрано: %s, %s, занятий=%d", requested_date, class_course, len(schedule.lessons))
        return schedule

    async def available_classes(self) -> dict[str, list[str]]:
        cached = await self.cache.get()
        async with self._parse_lock:
            if self._parsed_hash != cached.sha256 or self._workbook is None:
                self._workbook = await asyncio.to_thread(parse_workbook, str(cached.path))
                self._parsed_hash = cached.sha256
            return self._workbook.available_classes

    async def available_groups(self, class_course: str) -> list[str]:
        cached = await self.cache.get()
        async with self._parse_lock:
            if self._parsed_hash != cached.sha256 or self._workbook is None:
                self._workbook = await asyncio.to_thread(parse_workbook, str(cached.path))
                self._parsed_hash = cached.sha256
            values = [
                lesson.group for lesson in self._workbook.lessons
                if lesson.class_course.casefold().strip() == class_course.casefold().strip() and lesson.group
            ]
            values.extend(
                item.group for item in self._workbook.changes
                if item.class_course and item.class_course.casefold().strip() == class_course.casefold().strip() and item.group
            )
            groups = []
            for value in sorted(set(values), key=str.casefold):
                if not any(_same_group_text(value, existing) for existing in groups):
                    groups.append(value)
            return groups

    def _assign_rooms(self, schedule: Schedule, data: WorkbookData, gender: str | None = None) -> None:
        room_rows = data.rooms.get(schedule.date, [])
        for lesson in schedule.lessons:
            if lesson.pair_number is None:
                continue
            subject_token = normalized(lesson.subject)
            teacher_token = normalized(lesson.teacher or "")
            desired_group = lesson.group or schedule.group
            desired_gender = _gender_code(gender)
            matches: list[str] = []
            for room, content, pair_number, slot_text in room_rows:
                content_token = normalized(content)
                if lesson.pair_number is not None:
                    if pair_number != lesson.pair_number:
                        continue
                elif lesson.start_time:
                    slot_start, slot_end = parse_time_range(slot_text)
                    if not slot_start or not slot_end or not (slot_start <= lesson.start_time and (not lesson.end_time or lesson.end_time <= slot_end)):
                        continue
                else:
                    continue
                if not _room_has_class(content, lesson.class_course):
                    continue
                room_groups = _room_group_codes(content)
                desired_groups = _room_group_codes(desired_group or "")
                if desired_gender and room_groups and not _contains_gender(room_groups, desired_gender):
                    continue
                if desired_groups and room_groups and not _contains_group(room_groups, desired_groups):
                    continue
                if subject_token and not _room_subject_matches(lesson.subject, content_token):
                    continue
                if teacher_token and teacher_token not in content_token:
                    continue
                matches.append(room)
            unique = set(matches)
            if len(unique) == 1:
                lesson.room = next(iter(unique))


def _room_subject_matches(subject: str, room_content: str) -> bool:
    import re
    base_subject = re.split(r"\(|объединенный урок", subject, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    token = normalized(base_subject)
    if token in room_content:
        return True
    classic_terms = {"классическийтанец", "классика", "классический"}
    return token in classic_terms and any(term in room_content for term in ("классика", "классическийтанец"))


def _room_group_matches(group: str, room_content: str) -> bool:
    desired_groups = _room_group_codes(group)
    room_groups = _room_group_codes(room_content)
    return bool(desired_groups and room_groups and desired_groups.issubset(room_groups))


def _gender_code(gender: str | None) -> str | None:
    if gender in {"female", "Д", "д", "девушка", "девушки"}:
        return "д"
    if gender in {"male", "М", "м", "юноша", "юноши"}:
        return "м"
    return None


def _contains_gender(room_groups: set[str], gender: str) -> bool:
    return gender in room_groups or (gender == "д" and bool(room_groups & {"д1", "д2"}))


def _contains_group(room_groups: set[str], desired_groups: set[str]) -> bool:
    return all(
        group in room_groups or (group == "д" and bool(room_groups & {"д1", "д2"}))
        for group in desired_groups
    )


def _room_has_class(content: str, class_course: str) -> bool:
    target = _room_class_key(class_course)
    room_prefix = normalized(content.splitlines()[0])
    return bool(target and room_prefix.startswith(target))


def _room_class_key(value: str) -> str:
    import re
    clean = re.sub(r"\bкурс\b", "", value, flags=re.IGNORECASE)
    clean = re.sub(r"\s+(?:Д\s*[12]?|М)(?:\s*[+/,]\s*(?:Д\s*[12]?|М))*\s*$", "", clean, flags=re.IGNORECASE)
    return normalized(clean)


def _room_group_codes(value: str) -> set[str]:
    import re
    if not value.strip():
        return set()
    raw = value.splitlines()[0].casefold().replace("ё", "е")
    codes = set(re.findall(r"(?<!\w)д\s*[12]?(?!\w)|(?<!\w)м(?!\w)", raw))
    codes = {normalized(code) for code in codes}
    if re.search(r"девочк\w*\s*(?:гр\.?\s*)?1", raw):
        codes.add("д1")
    if re.search(r"девочк\w*\s*(?:гр\.?\s*)?2", raw):
        codes.add("д2")
    if "девуш" in raw:
        codes.add("д")
    if "юнош" in raw or "мальчик" in raw:
        codes.add("м")
    return codes


def _same_group_text(left: str, right: str) -> bool:
    aliases = {"девочки1": "д1", "девочки2": "д2", "мальчики": "м", "девушки": "д", "юноши": "м"}
    clean = lambda value: "".join(char for char in value.casefold().replace("ё", "е") if char.isalnum())
    left_key, right_key = clean(left), clean(right)
    return aliases.get(left_key, left_key) == aliases.get(right_key, right_key)


def _known_class(requested: str, available: dict[str, list[str]]) -> bool:
    target = normalized(requested)
    return any(normalized(item) == target for values in available.values() for item in values)


def render_schedule(schedule: Schedule) -> str:
    from src.infrastructure.google_sheets.parsing import WEEKDAYS
    day_names = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")
    date_line = f"📅 {day_names[schedule.date.weekday()].capitalize()}, {schedule.date.day} {schedule.date.strftime('%B')}"
    months = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря")
    date_line = f"📅 {day_names[schedule.date.weekday()].capitalize()}, {schedule.date.day} {months[schedule.date.month - 1]}"
    chunks = [date_line, f"{schedule.class_course}" + (f" · {schedule.group}" if schedule.group else "")]
    if schedule.stale:
        chunks.append("⚠️ Использована сохранённая версия данных; обновить расписание сейчас не удалось.")
    for lesson in schedule.lessons:
        if lesson.pair_number is not None and lesson.pair_start_time and lesson.pair_end_time:
            start, end = lesson.pair_start_time, lesson.pair_end_time
        else:
            start, end = lesson.start_time, lesson.end_time
        if start and end:
            chunks.append(f"{start:%H:%M}–{end:%H:%M}")
        elif lesson.pair_number:
            chunks.append(f"{lesson.pair_number} пара")
        elif lesson.time_raw:
            chunks.append(lesson.time_raw)
        subject = f"{lesson.subject} (замена)" if lesson.is_replacement else lesson.subject
        chunks.append(subject)
        if lesson.teacher:
            chunks.append(f"Преподаватель: {lesson.teacher}")
        if lesson.room:
            chunks.append(f"Зал/кабинет: {lesson.room}")
        chunks.append("")
    if not schedule.lessons:
        chunks.append("Занятий по недельному расписанию нет.")
    if schedule.announcements:
        chunks.extend(["Объявления:", *[f"• {item}" for item in schedule.announcements]])
    if schedule.unresolved_changes:
        chunks.extend(["Изменения, требующие уточнения:", *[f"• {item}" for item in schedule.unresolved_changes]])
    return "\n".join(chunks).strip()
