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


def _load_dotenv_into_environ(path: Path | None = None) -> None:
    """Populate os.environ from .env so config-file ${VAR} expansion and
    api_key_env lookups work, not just the pydantic Settings object.
    Existing environment variables always win.
    """
    env_path = path or REPO_ROOT / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv_into_environ()


class Settings(BaseSettings):
    """Runtime settings, loaded from environment / .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    vajra_host: str = "127.0.0.1"
    vajra_port: int = 8760
    #: bind to 0.0.0.0 so a phone on the same Wi-Fi can reach the Core.
    #: only enable on a trusted LAN - the pairing token is the only guard.
    vajra_bind_lan: bool = False
    vajra_db_path: str = "./data/vajra.db"
    vajra_log_dir: str = "./logs"
    vajra_pairing_token: str = "change-me-local-only"
    vajra_max_retries: int = 2
    vajra_autonomy_enabled: bool = True

    @property
    def bind_host(self) -> str:
        return "0.0.0.0" if self.vajra_bind_lan else self.vajra_host  # noqa: S104

    nvidia_api_key: str | None = None
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    vajra_nemotron_model: str = "nvidia/nemotron-3-super-120b-a12b"

    vajra_local_model: str = "qwen2.5-coder"
    vajra_local_base_url: str = "http://localhost:11434/v1"

    # RAG embeddings. Empty base_url -> offline lexical fallback (no network).
    # Point at any OpenAI-compatible /embeddings endpoint (NIM, Ollama, ...).
    vajra_embed_model: str = "nvidia/nv-embedqa-e5-v5"
    vajra_embed_base_url: str = ""
    vajra_embed_api_key_env: str = "NVIDIA_API_KEY"

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
