from dotenv import load_dotenv ; load_dotenv()
import os
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # 1. APP 설정
    APP_NAME: str = "Redfin Label & Recommendation API"
    APP_VERSION: str = "0.2.0"
    APP_DESCRIPTION: str = "API for label & recommendation"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8010
    APP_DEBUG: bool = True
    APP_API_V1_STR: str = "/api/v1"
    APP_LOG_LEVEL: str = "INFO"

    # 2. 카테고리 스키마 설정
    CATALOG_SCHEME: str = "redfin-minds-2025"
    CATALOG_CATEGORIES: List[str] = []
    CATALOG_TAGS: List[str] = []

    # 3. MongoDB 설정
    MONGO_DB: str = "redfin"
    MONGO_COLLECTION: str = "entries_with_body"
    
    MONGO_BASE_URI: str = os.getenv("MONGO_BASE_URI", "mongodb://admin:Redfin7620!@localhost:27017/redfin?authSource=admin")
    MONGO_LOCAL_URI: str = os.getenv("MONGO_LOCAL_URI", "mongodb://admin:Redfin7620!@localhost:27017/redfin?authSource=admin")
    MONGO_REMOTE_URI: str = os.getenv("MONGO_REMOTE_URI", "mongodb://100.97.183.123:27017/redfin?authSource=admin")
    MONGO_SERVERS: dict = {
        "local": {
            "base_url": os.getenv("MONGO_SERVERS_LOCAL_BASE_URL", "mongodb://admin:Redfin7620!@localhost:27017/redfin?authSource=admin"),
        },
        "remote": {
            "base_url": os.getenv("MONGO_SERVERS_REMOTE_BASE_URL", "mongodb://100.97.183.123:27017/redfin?authSource=admin"),
        }
    }

    # 4. Elasticsearch 설정
    ES_HOST: str = os.getenv("ES_HOST", "http://localhost:9200")
    ES_AUTH: tuple = (os.getenv("ES_USER", "elastic"), os.getenv("ES_PASSWORD", "elastic"))
    ES_INDEX_NAME: str = os.getenv("ES_INDEX_NAME", "article_recommender")
    ES_USER: str = os.getenv("ES_USER", "elastic")
    ES_PASSWORD: str = os.getenv("ES_PASSWORD", "elastic")
    INDEX_NAME: str = os.getenv("INDEX_NAME", "article_recommender")

    # 5. Ollama 설정
    OLLAMA_MODEL: str = "ollama:gemma3:4b"
    OLLAMA_BASE_URI: str = os.getenv("OLLAMA_BASE_URI", "http://localhost:11434")
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    # 다중 Ollama 서버 및 모델 설정
    OLLAMA_SERVERS: dict = {
        "local": {
            "base_url": os.getenv("OLLAMA_SERVERS_LOCAL_BASE_URL", "http://localhost:11434"),
            "models": {
                "gemma3:4b": "ollama:gemma3:4b"
            }
        },
        "remote": {
            "base_url": os.getenv("OLLAMA_SERVERS_REMOTE_BASE_URL", "http://100.97.183.123:11434"),
            "models": {
                "qwen2.5:3b-instruct-q4_K_M": "qwen2.5:3b-instruct-q4_K_M",
                "llama3.2:3b-instruct-q5_K_M": "llama3.2:3b-instruct-q5_K_M", 
                "qwen2.5:3b-instruct": "qwen2.5:3b-instruct",
                "phi3.5:latest": "phi3.5:latest",
                "gemma3:4b": "gemma3:4b"
            }
        }
    }
    OLLAMA_SERVERS_LOCAL_BASE_URL: str = os.getenv("OLLAMA_SERVERS_LOCAL_BASE_URL", "http://localhost:11434")
    OLLAMA_SERVERS_REMOTE_BASE_URL: str = os.getenv("OLLAMA_SERVERS_REMOTE_BASE_URL", "http://100.97.183.123:11434")

    # 기본 서버 및 모델 선택
    DEFAULT_OLLAMA_SERVER: str = "remote"
    DEFAULT_OLLAMA_MODEL: str = "qwen2.5:3b-instruct-q4_K_M"

settings = Settings()
