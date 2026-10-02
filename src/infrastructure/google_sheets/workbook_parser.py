from openpyxl import load_workbook

from src.domain.models import WorkbookData
from src.infrastructure.google_sheets.changes_parser import parse_changes
from src.infrastructure.google_sheets.rooms_parser import parse_rooms
from src.infrastructure.google_sheets.weekly_parser import parse_weekly_sheet

WEEKLY_SHEETS = ("I(6)-III(8)", "Начальная школа", "ОТТ ", "1(5)-5(9) ")


def parse_workbook(path: str) -> WorkbookData:
    workbook = load_workbook(path, data_only=True, read_only=False)
    lessons = []
    classes: dict[str, list[str]] = {"primary": [], "school": [], "course": [], "ott": []}
    for sheet_name in WEEKLY_SHEETS:
        sheet = workbook[sheet_name]
        parsed, available = parse_weekly_sheet(sheet)
        lessons.extend(parsed)
        key = {"Начальная школа": "primary", "1(5)-5(9) ": "school", "I(6)-III(8)": "course", "ОТТ ": "ott"}[sheet_name]
        classes[key] = available
    changes, announcements = parse_changes(workbook["ИНФОРМАЦИЯ 2026"])
    rooms = parse_rooms(workbook["Залы"])
    return WorkbookData(lessons, changes, announcements, classes, rooms)

