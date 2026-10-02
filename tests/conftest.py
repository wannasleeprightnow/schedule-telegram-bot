from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "Расписание 2026-2027 (1 полугодие).xlsx"


@pytest.fixture(scope="session")
def workbook_path():
    return FIXTURE

