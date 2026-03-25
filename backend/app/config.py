from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_DIR / ".env", override=False)
load_dotenv(BACKEND_DIR / ".env", override=False)


@dataclass(frozen=True)
class Settings:
    app_name: str = "研策 Yance"
    backend_dir: Path = BACKEND_DIR
    project_dir: Path = PROJECT_DIR
    data_dir: Path = backend_dir / "data"
    workspace_root: Path = data_dir / "workspaces"
    database_path: Path = data_dir / "yance.db"
    profile_dir: Path = Path(__file__).resolve().parent / "data" / "profiles"
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5-mini")
    openai_timeout_seconds: int = int(os.getenv("OPENAI_TIMEOUT_SECONDS", "180"))
    search_timeout_seconds: int = int(os.getenv("YANCE_SEARCH_TIMEOUT", "10"))
    cors_origins: tuple[str, ...] = tuple(
        item.strip()
        for item in os.getenv(
            "YANCE_CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000",
        ).split(",")
        if item.strip()
    )


settings = Settings()

settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.workspace_root.mkdir(parents=True, exist_ok=True)
