"""Настройки сервиса из окружения."""
import os
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TYPST_DECK_", env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    template_dir: Path = Path("template")      # шаблон по умолчанию (id "default")
    templates_dir: str = "templates"           # корни дополнительных шаблонов <корень>/<id>/deck.typ; несколько — через ":" как PATH
    template_aliases: str = ""                 # старые id шаблонов: "старый:новый,старый2:новый2"
    typst_bin: str = "typst"
    check_templates_on_start: bool = True      # фоновая проверка шаблонов при старте
    public_base_url: str = ""
    llm_api_base: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_max_tokens: int = 16384  # рассуждающим моделям 4096 не хватает даже на рассуждение
    llm_tool_mode: Literal["tools", "json"] = "tools"
    max_upload_mb: int = 20
    log_level: str = "INFO"
    log_format: Literal["text", "json"] = "text"

    @property
    def templates_dirs(self) -> list[Path]:
        return [Path(p) for p in self.templates_dir.split(os.pathsep) if p]

    @property
    def template_alias_map(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for pair in self.template_aliases.split(","):
            pair = pair.strip()
            if not pair:
                continue
            old, sep, new = pair.partition(":")
            if not sep or not old.strip() or not new.strip():
                raise ValueError(f"TYPST_DECK_TEMPLATE_ALIASES: «{pair}» — ожидается старый:новый")
            out[old.strip()] = new.strip()
        return out


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
