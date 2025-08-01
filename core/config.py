from pydantic import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # API 설정
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Intent Analysis API"
    
    # 데이터베이스 설정
    DATABASE_URL: str = "intents.db"
    
    # OpenAI 설정
    OPENAI_API_KEY: Optional[str] = None
    
    # 로깅 설정
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "server.log"
    
    class Config:
        env_file = ".env"

settings = Settings() 