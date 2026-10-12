from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    host: str = "0.0.0.0"
    port: int = 8000
    database_path: str = "./data/shop.db"
    database_url: str = (
        "mysql+pymysql://shiwu:shiwu_local@127.0.0.1:3306/shiwu?charset=utf8mb4"
    )
    ai_mode: Literal["demo", "llm"] = "demo"
    session_hours: int = 24
    seed_demo: bool = True
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
