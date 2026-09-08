"""Настройки сервиса из окружения."""
import os
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TYPST_DECK_", env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    template_dir: Path = Path("template")
    typst_bin: str = "typst"
    public_base_url: str = ""
    llm_api_base: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_max_tokens: int = 16384  # рассуждающим моделям 4096 не хватает даже на рассуждение
    llm_tool_mode: Literal["tools", "json"] = "tools"
    max_upload_mb: int = 20


def get_settings() -> Settings:
    """Собирает настройки; DEEPSEEK_* из стека принимаются как синонимы LLM_*."""
    s = Settings()
    if not s.llm_api_key:
        s.llm_api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not s.llm_api_base:
        s.llm_api_base = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    if not s.llm_model:
        s.llm_model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    return s
