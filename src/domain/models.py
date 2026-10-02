from dataclasses import dataclass, field
from datetime import date, time


@dataclass(slots=True)
class ScheduleLesson:
    weekday: int
    class_course: str
    group: str | None
    lesson_number: int | None
    pair_number: int | None
    start_time: time | None
    end_time: time | None
    pair_start_time: time | None
    pair_end_time: time | None
    subject: str
    subject_raw: str
    teacher: str | None
    room: str | None
    source_sheet: str
    source_row: int
    time_raw: str | None = None
    is_replacement: bool = False


@dataclass(slots=True)
class ScheduleChange:
    date: date
    class_course: str | None
    group: str | None
    time_raw: str | None
    information: str
    teacher: str | None
    room: str | None
    kind: str
    source_row: int


@dataclass(slots=True)
class Schedule:
    date: date
    class_course: str
    group: str | None
    lessons: list[ScheduleLesson] = field(default_factory=list)
    announcements: list[str] = field(default_factory=list)
    unresolved_changes: list[str] = field(default_factory=list)
    stale: bool = False


@dataclass(slots=True)
class WorkbookData:
    lessons: list[ScheduleLesson]
    changes: list[ScheduleChange]
    announcements: list[ScheduleChange]
    available_classes: dict[str, list[str]]
    rooms: dict[date, list[tuple[str, str, int | None, str | None]]]
