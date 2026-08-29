"""Central configuration. Local-first: everything is driven by env / config files."""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


class Settings(BaseSettings):
    """Runtime settings, loaded from environment / .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    vajra_host: str = "127.0.0.1"
    vajra_port: int = 8760
    vajra_db_path: str = "./data/vajra.db"
    vajra_log_dir: str = "./logs"
    vajra_pairing_token: str = "change-me-local-only"
    vajra_max_retries: int = 2
    vajra_autonomy_enabled: bool = True

    nvidia_api_key: str | None = None
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    vajra_nemotron_model: str = "nvidia/nemotron-4-340b-instruct"

    vajra_local_model: str = "qwen2.5-coder"
    vajra_local_base_url: str = "http://localhost:11434/v1"

    @property
    def db_path(self) -> Path:
        p = (REPO_ROOT / self.vajra_db_path).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def log_dir(self) -> Path:
        p = (REPO_ROOT / self.vajra_log_dir).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p


class ModelEndpoint(BaseModel):
    provider: str
    model: str
    base_url: str | None = None
    api_key_env: str | None = None
    timeout_seconds: int = 120
    max_context_tokens: int = 128000

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env) if self.api_key_env else None


class ModelConfig(BaseModel):
    primary: ModelEndpoint
    fallback: ModelEndpoint
    retry: dict[str, Any] = {}


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        return _ENV_PATTERN.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_model_config(path: str | None = None) -> ModelConfig:
    cfg_path = Path(path) if path else REPO_ROOT / "config" / "models.yaml"
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    cfg = ModelConfig.model_validate(_expand_env(raw))
    s = get_settings()
    # Fall back to Settings defaults when env vars are unset, so the Core is
    # always describable even before .env is filled in.
    cfg.primary.model = cfg.primary.model or s.vajra_nemotron_model
    cfg.primary.base_url = cfg.primary.base_url or s.nvidia_base_url
    cfg.fallback.model = cfg.fallback.model or s.vajra_local_model
    cfg.fallback.base_url = cfg.fallback.base_url or s.vajra_local_base_url
    return cfg
