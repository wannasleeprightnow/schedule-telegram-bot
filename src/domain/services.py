from copy import copy
from datetime import date, time

from src.domain.constants import PAIR_TIMES
from src.domain.models import Schedule, ScheduleChange, ScheduleLesson


def build_schedule(
    requested_date: date,
    class_course: str,
    group: str | None,
    weekly_lessons: list[ScheduleLesson],
    changes: list[ScheduleChange],
    announcements: list[ScheduleChange],
) -> Schedule:
    lessons = [
        copy(lesson) for lesson in weekly_lessons
        if lesson.weekday == requested_date.weekday()
        and lesson.class_course.casefold() == class_course.casefold()
        and (group is None or lesson.group is None or _same_group(lesson.group, group))
    ]
    unresolved: list[str] = []
    for change in (item for item in changes if item.date == requested_date):
        change_classes = _split_classes(change.class_course or "")
        if not any(_same_class(item, class_course) for item in change_classes):
            continue
        if change.group and group and not _same_group(change.group, group):
            continue
        text = change.information.strip()
        lowered = text.casefold()
        cancellation = "отмен" in lowered
        match_indexes = [
            index for index, lesson in enumerate(lessons)
            if _change_matches(lesson, change)
            and (not change.group or not lesson.group or _same_group(change.group, lesson.group))
        ]
        replacement = _is_replacement(text)
        pair_match = __import__("re").search(r"(\d+)\s*пара", change.time_raw or "", __import__("re").IGNORECASE)
        slot_indexes = []
        if pair_match:
            pair_number = int(pair_match.group(1))
            slot_indexes = [
                index for index, lesson in enumerate(lessons)
                if lesson.pair_number == pair_number
                and (not change.group or not lesson.group or _same_group(change.group, lesson.group))
            ]
            if slot_indexes and "перенос" not in lowered:
                match_indexes = slot_indexes
        if not match_indexes and change.kind == "additional" and change.time_raw:
            pair_match = __import__("re").search(r"(\d+)\s*пара", change.time_raw, __import__("re").IGNORECASE)
            start, end = _parse_time_range(change.time_raw)
            pair_number = int(pair_match.group(1)) if pair_match else None
            lessons.append(ScheduleLesson(
                weekday=requested_date.weekday(),
                class_course=class_course,
                group=change.group,
                lesson_number=None,
                pair_number=pair_number,
                start_time=start,
                end_time=end,
                pair_start_time=PAIR_TIMES.get(pair_number, (None, None))[0],
                pair_end_time=PAIR_TIMES.get(pair_number, (None, None))[1],
                subject=text,
                subject_raw=text,
                teacher=change.teacher,
                room=change.room,
                source_sheet="ИНФОРМАЦИЯ 2026",
                source_row=change.source_row,
                time_raw=change.time_raw,
            ))
            continue
        if cancellation and "вместо" in lowered:
            if len(match_indexes) == 1:
                lesson = lessons[match_indexes[0]]
                lesson.subject = _subject_from_change(text) or lesson.subject
                lesson.subject_raw = text
                lesson.teacher = _replacement_teacher(text) or lesson.teacher
                lesson.room = change.room or _replacement_room(text) or lesson.room
                lesson.is_replacement = True
            else:
                unresolved.append(text)
            continue
        if cancellation:
            if len(match_indexes) == 1:
                lessons.pop(match_indexes[0])
            elif match_indexes and _same_canceled_block([lessons[index] for index in match_indexes]):
                for index in reversed(match_indexes):
                    lessons.pop(index)
            else:
                unresolved.append(text)
            continue
        if "перенос" in lowered:
            import re
            source_match = re.search(r"перенос\s+со?\s*(\d+)\s*пары", lowered)
            destination_match = re.search(r"(\d+)\s*пара", change.time_raw or "", re.IGNORECASE)
            transfer_indexes = match_indexes
            if source_match:
                transfer_indexes = [index for index in match_indexes if lessons[index].pair_number == int(source_match.group(1))]
            if len(transfer_indexes) == 1:
                lesson = lessons[transfer_indexes[0]]
                if destination_match:
                    target_pair = int(destination_match.group(1))
                    target_times = [item for item in lessons if item.pair_number == target_pair and item is not lesson]
                    if any(not item.group or not lesson.group or _same_group(item.group, lesson.group) for item in target_times):
                        unresolved.append(text)
                        continue
                    lesson.pair_number = target_pair
                    lesson.pair_start_time, lesson.pair_end_time = PAIR_TIMES.get(target_pair, (None, None))
                    lesson.start_time = None
                    lesson.end_time = None
                    lesson.lesson_number = None
                else:
                    lesson.start_time, lesson.end_time = _parse_time_range(change.time_raw or "")
                    lesson.pair_number = None
                lesson.subject_raw = text
                lesson.room = change.room or lesson.room
            else:
                unresolved.append(text)
            continue
        if "вместо" in lowered or "перенос" in lowered or "замен" in lowered:
            if len(match_indexes) == 1:
                lesson = lessons[match_indexes[0]]
                subject = _subject_from_change(text)
                subject_changed = bool(subject and _normalized(lesson.subject) != _normalized(subject))
                lesson.subject = subject or text
                lesson.subject_raw = text
                lesson.teacher = change.teacher or lesson.teacher
                lesson.room = change.room or lesson.room
                lesson.is_replacement = replacement or (
                    change.kind not in {"merged", "additional"}
                    and subject_changed
                )
            else:
                unresolved.append(text)
            continue
        if "объедин" in lowered and change.time_raw:
            slot = _find_slot(lessons, change.time_raw)
            if len(slot) == 1:
                lesson = slot[0]
                lesson.subject = text
                lesson.subject_raw = text
                lesson.teacher = change.teacher or lesson.teacher
                lesson.room = change.room or lesson.room
            else:
                unresolved.append(text)
            continue
        if len(match_indexes) == 1:
            lesson = lessons[match_indexes[0]]
            subject_changed = _normalized(lesson.subject) != _normalized(text)
            lesson.subject = text
            lesson.subject_raw = text
            lesson.teacher = change.teacher or lesson.teacher
            lesson.room = change.room or lesson.room
            lesson.is_replacement = replacement or (
                change.kind not in {"merged", "additional"}
                and subject_changed
            )
        else:
            unresolved.append(text)

    notes = [change.information.strip() for change in announcements if change.date == requested_date]
    lessons.sort(key=lambda item: (item.start_time or item.pair_start_time or time.min, item.lesson_number or 0))
    return Schedule(requested_date, class_course, group, lessons, notes, unresolved)


def _change_matches(lesson: ScheduleLesson, change: ScheduleChange) -> bool:
    text = change.information.casefold()
    import re
    words = re.findall(r"[а-яёa-z0-9]+", lesson.subject.casefold())
    phrase = r"[\W_]+".join(re.escape(word) for word in words)
    if phrase and re.search(rf"(?<![\w-]){phrase}(?![\w-])", text, re.IGNORECASE):
        return True
    return bool(lesson.teacher and lesson.teacher.casefold() in text and (lesson.pair_number is not None and f"{lesson.pair_number} пара" in text))


def _is_replacement(text: str) -> bool:
    import re
    lowered = text.casefold()
    return "вместо" in lowered or bool(re.search(r"\b(?:замен\w*|замещ\w*)", lowered))


def _subject_from_change(text: str) -> str | None:
    import re
    before_cancellation = re.split(r"отмена", text, flags=re.IGNORECASE)[0].strip()
    if "вместо" in before_cancellation.casefold():
        clean = before_cancellation.split("(", 1)[0].strip()
    elif "отмена" in text.casefold() and "вместо" in text.casefold():
        clean = re.split(r"вместо\s+(?:дуэта\s+)?", text, flags=re.IGNORECASE)[-1]
    else:
        clean = before_cancellation
    if "перенос" in clean.casefold():
        clean = clean.split("(", 1)[0].strip()
    clean = re.split(r"\s+(?:каб(?:инет)?\.?\s*|зал\s*№?)", clean, maxsplit=1, flags=re.IGNORECASE)[0]
    clean = re.sub(r"\s*\([^)]*\)\s*$", "", clean).strip()
    return clean or None


def _replacement_teacher(text: str) -> str | None:
    import re
    names = re.findall(r"[А-ЯЁ][а-яё-]+\s+[А-ЯЁ]\.\s*[А-ЯЁ]?\.?", text)
    return names[-1] if names else None


def _replacement_room(text: str) -> str | None:
    import re
    match = re.search(r"(?:каб(?:инет)?\.?\s*|зал\s*№?\s*)([\w.-]+)", text, re.IGNORECASE)
    return match.group(1) if match else None


def _split_classes(raw: str) -> list[str]:
    import re
    without_groups = re.sub(r"\s+(?:Д\s*[12]?|М)(?:\s*[+/,]\s*(?:Д\s*[12]?|М))*\s*$", "", raw, flags=re.IGNORECASE)
    return [part.strip() for part in re.split(r"\s*[+,;]\s*|,\s*", without_groups) if part.strip()]


def _same_class(left: str, right: str) -> bool:
    import re
    translate = str.maketrans({"c": "с", "o": "о"})
    def clean(value: str) -> str:
        value = re.sub(r"\bкурс\b", "", value.strip(), flags=re.IGNORECASE).casefold().translate(translate)
        value = re.sub(r"^1(?=\s+[а-яёa-z]{2,})", "i", value)
        return re.sub(r"\s+", "", value)
    return clean(left) == clean(right)


def _same_group(left: str, right: str) -> bool:
    import re
    clean = lambda value: re.sub(r"[^а-яёa-z0-9]+", "", value.casefold().replace("ё", "е"))
    aliases = {"девочки1": "д1", "девочки2": "д2", "мальчики": "м", "девушки": "д", "юноши": "м"}
    left_groups = {aliases.get(clean(part), clean(part)) for part in re.split(r"\s*[+/,]\s*", left)}
    right_groups = {aliases.get(clean(part), clean(part)) for part in re.split(r"\s*[+/,]\s*", right)}
    return bool(left_groups & right_groups)


def _same_canceled_block(lessons: list[ScheduleLesson]) -> bool:
    if not lessons:
        return False
    first = lessons[0]
    return all(
        lesson.pair_number == first.pair_number
        and _normalized(lesson.subject) == _normalized(first.subject)
        and lesson.group is not None
        and first.group is not None
        and _same_group(lesson.group, first.group)
        for lesson in lessons
    )


def _normalized(value: str) -> str:
    import re
    return re.sub(r"[^a-zа-яё0-9]+", "", value.casefold().replace("ё", "е"))


def _parse_time_range(value: str) -> tuple[time | None, time | None]:
    import re
    matches = re.findall(r"(?<!\d)([01]?\d|2[0-3])[:.](\d{2})(?!\d)", value)
    if not matches:
        return None, None
    try:
        if len(matches) == 1:
            return time(int(matches[0][0]), int(matches[0][1])), None
        return time(int(matches[0][0]), int(matches[0][1])), time(int(matches[1][0]), int(matches[1][1]))
    except ValueError:
        return None, None


def _find_slot(lessons: list[ScheduleLesson], time_raw: str) -> list[ScheduleLesson]:
    import re
    pair_match = re.search(r"(\d+)\s*пара", time_raw, re.IGNORECASE)
    if pair_match:
        return [lesson for lesson in lessons if lesson.pair_number == int(pair_match.group(1))]
    return []
