from datetime import date

import pytest

import src.application.schedule_service as schedule_module
from src.application.schedule_service import ScheduleService, render_schedule
from src.infrastructure.cache.workbook_cache import CachedWorkbook
from src.infrastructure.google_sheets.workbook_parser import parse_workbook


class FixtureCache:
    def __init__(self, path):
        self.path = path
        self.calls = 0

    async def get(self):
        self.calls += 1
        return CachedWorkbook(self.path, False, "fixture-hash")


@pytest.mark.asyncio
async def test_schedule_service_builds_schedule_and_uses_one_parsed_workbook(workbook_path, monkeypatch):
    cache = FixtureCache(workbook_path)
    service = ScheduleService(cache)
    parse_calls = 0
    parse_original = schedule_module.parse_workbook

    def count_parses(path):
        nonlocal parse_calls
        parse_calls += 1
        return parse_original(path)

    monkeypatch.setattr(schedule_module, "parse_workbook", count_parses)
    schedules = await __import__("asyncio").gather(*[
        service.get_schedule(date(2026, 10, 2), "5 (9) Б") for _ in range(3)
    ])
    assert all(any("объединенный урок" in lesson.subject.casefold() for lesson in item.lessons) for item in schedules)
    assert cache.calls == 3
    assert parse_calls == 1
    joined = next(lesson for lesson in schedules[0].lessons if "объединенный урок" in lesson.subject.casefold())
    assert joined.room == "Зал № 15"


@pytest.mark.asyncio
async def test_rendered_schedule_shows_bell_interval_for_each_pair(workbook_path):
    schedule = await ScheduleService(FixtureCache(workbook_path)).get_schedule(date(2026, 10, 2), "III (8) курс")
    rendered = render_schedule(schedule)
    assert "10:55–12:25" in rendered
    assert "13:00–14:30" in rendered
    assert "15:00–16:30" in rendered
    assert "10:55–11:40" not in rendered
    assert "Психология общения (замена)" in rendered
    assert "Дуэтно-классический танец" not in rendered


@pytest.mark.asyncio
async def test_course_room_mapping_uses_group_shorthand_from_rooms_sheet(workbook_path):
    date_requested = date(2026, 10, 2)
    service = ScheduleService(FixtureCache(workbook_path))
    girls = await service.get_schedule(date_requested, "III (8) курс", gender="female")
    boys = await service.get_schedule(date_requested, "III (8) курс", gender="male")
    unspecified = await service.get_schedule(date_requested, "III (8) курс")

    girls_lesson = next(lesson for lesson in girls.lessons if lesson.pair_number == 2)
    boys_lesson = next(lesson for lesson in boys.lessons if lesson.pair_number == 2)
    unspecified_lesson = next(lesson for lesson in unspecified.lessons if lesson.pair_number == 2)
    assert girls_lesson.room == "Реп зал"
    assert boys_lesson.room == "Сцена"
    assert unspecified_lesson.room is None


@pytest.mark.asyncio
async def test_explicit_information_replacement_is_marked_in_user_message(workbook_path):
    schedule = await ScheduleService(FixtureCache(workbook_path)).get_schedule(date(2026, 9, 11), "III (8) курс")
    rendered = render_schedule(schedule)
    assert "Охрана труда (замена)" in rendered
