from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./adrobot.db"
    keitaro_base_url: str = ""
    keitaro_api_key: str = ""
    keitaro_timeout: float = 20
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
