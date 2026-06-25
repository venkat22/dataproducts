from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://dp_user:dp_password@db:5432/dataproducts"
    # Direct Anthropic API
    anthropic_api_key: str = ""
    anthropic_model: str = "us.anthropic.claude-sonnet-4-6"
    # AWS Bedrock — IAM key/secret
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_default_region: str = ""
    aws_region: str = "us-east-1"
    # AWS Bedrock — bearer token (used by Claude Code / SSO)
    aws_bearer_token_bedrock: str = ""
    db_connect_retries: int = 20
    db_connect_delay_seconds: float = 1.5

    @property
    def region(self) -> str:
        return self.aws_default_region or self.aws_region or "us-east-1"

    @property
    def use_bedrock(self) -> bool:
        return bool(
            self.aws_bearer_token_bedrock
            or (self.aws_access_key_id and self.aws_secret_access_key)
        )

    @property
    def ai_enabled(self) -> bool:
        return self.use_bedrock or bool(self.anthropic_api_key)

    class Config:
        env_file = ".env"
        env_prefix = ""


settings = Settings()
