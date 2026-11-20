"""Runtime configuration for Mnemos.

All values can be overridden with environment variables (prefix ``MNEMOS_``).
No secrets are stored in source code: the optional API key is read from the
environment only.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _env(name: str, default: str) -> str:
    return os.environ.get(f"MNEMOS_{name}", default)


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", str(BACKEND_DIR / "data"))))
    api_key: str | None = field(default_factory=lambda: os.environ.get("MNEMOS_API_KEY") or None)
    cors_origins: list[str] = field(
        default_factory=lambda: _env(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
    )
    # Decision thresholds (tunable at runtime through /api/settings)
    duplicate_threshold: float = float(_env("DUPLICATE_THRESHOLD", "0.90"))
    merge_threshold: float = float(_env("MERGE_THRESHOLD", "0.78"))
    confirmation_threshold: float = float(_env("CONFIRMATION_THRESHOLD", "0.55"))
    min_relevance: float = float(_env("MIN_RELEVANCE", "0.30"))
    abstain_threshold: float = float(_env("ABSTAIN_THRESHOLD", "0.22"))
    default_temporary_hours: float = float(_env("TEMP_HOURS", "24"))
    default_token_budget: int = int(_env("DEFAULT_TOKEN_BUDGET", "1000"))
    retain_discarded_preview: bool = _env("RETAIN_DISCARDED_PREVIEW", "false").lower() == "true"
    embedding_dim: int = int(_env("EMBEDDING_DIM", "512"))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "mnemos.db"

    @property
    def files_dir(self) -> Path:
        return self.data_dir / "files"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.files_dir.mkdir(parents=True, exist_ok=True)

    def public_dict(self) -> dict:
        d = asdict(self)
        d["data_dir"] = str(self.data_dir)
        d["api_key"] = "configured" if self.api_key else "not set (local mode)"
        return d


TUNABLE_KEYS = {
    "duplicate_threshold": float,
    "merge_threshold": float,
    "confirmation_threshold": float,
    "min_relevance": float,
    "abstain_threshold": float,
    "default_temporary_hours": float,
    "default_token_budget": int,
    "retain_discarded_preview": bool,
}
