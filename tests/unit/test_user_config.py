import json

import pytest

from src.infrastructure.config.user_config import UserConfig


def test_user_profiles_are_isolated_and_limit_is_five(tmp_path):
    config = UserConfig(tmp_path / "users.json", {11, 22, 33, 44, 55, 66})
    for user_id in (11, 22, 33, 44, 55):
        config.save(user_id, {"schedule_type": "course", "class_course": str(user_id), "group": None, "gender": "female", "notification_enabled": False, "notification_time": "21:00"})
    with pytest.raises(ValueError):
        config.save(66, {"schedule_type": "school"})
    config.save(11, {"schedule_type": "course", "class_course": "updated"})
    assert config.get(11)["class_course"] == "updated"
    assert config.get(22)["gender"] == "female"
    assert config.get(22)["class_course"] == "22"
    assert len(json.loads((tmp_path / "users.json").read_text())["users"]) == 5


def test_unlisted_users_cannot_be_saved(tmp_path):
    config = UserConfig(tmp_path / "users.json", {1})
    with pytest.raises(PermissionError):
        config.save(2, {})
