from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://dp_user:dp_password@db:5432/dataproducts"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-8"
    db_connect_retries: int = 20
    db_connect_delay_seconds: float = 1.5

    class Config:
        env_file = ".env"
        env_prefix = ""


settings = Settings()
