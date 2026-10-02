from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str
    telegram_user_ids: str = ""
    schedule_source_url: str = "https://docs.google.com/spreadsheets/d/1vBwhdKBSBHbiLkCc_-en9z1hGP9AfDg_hxBX5msbIIA/export?format=xlsx"
    schedule_timezone: str = "Europe/Moscow"
    xlsx_cache_ttl: int = 180
    openrouter_api_key: str = ""
    openrouter_model: str = ""
    allow_stale_cache: bool = False
    data_dir: str = "data"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def allowed_user_ids(self) -> set[int]:
        return {int(item.strip()) for item in self.telegram_user_ids.split(",") if item.strip().isdigit()}
