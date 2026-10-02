import json
import os
from pathlib import Path
from typing import Any


class UserConfig:
    def __init__(self, path: Path, allowed_ids: set[int]):
        self.path = path
        self.allowed_ids = allowed_ids

    def all(self) -> dict[str, dict[str, Any]]:
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
            return content.get("users", {})
        except (OSError, json.JSONDecodeError, AttributeError):
            return {}

    def get(self, user_id: int) -> dict[str, Any] | None:
        return self.all().get(str(user_id))

    def save(self, user_id: int, profile: dict[str, Any]) -> None:
        if user_id not in self.allowed_ids:
            raise PermissionError("Пользователь не разрешён")
        users = self.all()
        if str(user_id) not in users and len(users) >= 5:
            raise ValueError("Достигнут лимит в 5 пользователей")
        users[str(user_id)] = {"telegram_id": user_id, **profile}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps({"users": users}, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self.path)

