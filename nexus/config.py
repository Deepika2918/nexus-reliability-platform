"""Application configuration."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_path: Path = Path("data/nexus.db")
    host: str = "127.0.0.1"
    port: int = 8000
    max_work_attempts: int = 5
    max_worker_restarts: int = 5
    lease_seconds: int = 30
    restart_window_seconds: int = 600
    retry_base_seconds: int = 2
    retry_max_seconds: int = 300
    event_retention_hours: int = 72
    recovery_loop_enabled: bool = True
    recovery_loop_interval_seconds: float = 1.0


settings = Settings()
