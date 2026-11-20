from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    groq_api_key: str
    model: str = "openai/gpt-oss-120b"
    max_steps: int = 6
    log_level: str = "INFO"

    class Config:
        env_file = ".env"

settings = Settings()
