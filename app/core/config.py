from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    
    APP_NAME: str = "Redfin Recommendation API"
    APP_VERSION: str = "0.1.0"
    APP_DESCRIPTION: str = "API for recommendation"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8010
    APP_DEBUG: bool = True
    APP_API_V1_STR: str = "/api/v1"
    APP_LOG_LEVEL: str = "INFO"
    # Ollama 설정 (기존 설정 유지)
    OLLAMA_MODEL: str = "ollama:gemma3:4b"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    
    # 다중 Ollama 서버 및 모델 설정
    OLLAMA_SERVERS: dict = {
        "local": {
            "base_url": "http://localhost:11434",
            "models": {
                "gemma3:4b": "ollama:gemma3:4b"
            }
        },
        "remote": {
            "base_url": "http://100.97.183.123:11434",
            "models": {
                "qwen2.5:3b-instruct-q4_K_M": "qwen2.5:3b-instruct-q4_K_M",
                "llama3.2:3b-instruct-q5_K_M": "llama3.2:3b-instruct-q5_K_M", 
                "qwen2.5:3b-instruct": "qwen2.5:3b-instruct",
                "phi3.5:latest": "phi3.5:latest",
                "gemma3:4b": "gemma3:4b"
            }
        }
    }
    
    # 기본 서버 및 모델 선택
    DEFAULT_OLLAMA_SERVER: str = "remote"
    DEFAULT_OLLAMA_MODEL: str = "qwen2.5:3b-instruct-q4_K_M"
    
    CATALOG_SCHEME: str = "redfin-minds-2025"
    
    # MongoDB 설정
    MONGODB_URI: str = "mongodb://100.97.183.123:27017"
    MONGODB_DB: str = "redfin"
    MONGODB_COLLECTION: str = "rss_all_entries"
    # TODO: 카테고리 스키마 목록/내용
    CATALOG_CATEGORIES: List[str] = [
        
    ]
    CATALOG_TAGS: List[str] = [

    ]

settings = Settings()
