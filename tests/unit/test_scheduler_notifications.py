import pytest

from src.presentation.telegram.handlers.notifications import send_daily_notification


class FakeUsers:
    def get(self, user_id):
        return {"notification_enabled": True, "class_course": "I (6) курс", "group": None}


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, user_id, text):
        self.sent.append((user_id, text))


class FailedSchedules:
    async def get_schedule(self, *args):
        raise RuntimeError("source offline")


@pytest.mark.asyncio
async def test_scheduler_notifies_user_when_schedule_retrieval_fails():
    bot = FakeBot()
    await send_daily_notification(bot, FailedSchedules(), FakeUsers(), 123, "Europe/Moscow")
    assert bot.sent[0][0] == 123
    assert "не удалось" in bot.sent[0][1].casefold()

