from src.infrastructure.config.user_config import UserConfig


class UserService:
    def __init__(self, config: UserConfig):
        self.config = config

    def get(self, user_id: int):
        return self.config.get(user_id)

    def save_profile(self, user_id: int, profile: dict) -> None:
        self.config.save(user_id, profile)

