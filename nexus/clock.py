"""Injectable clock for deterministic tests."""

import time
from typing import Callable


class Clock:
    def __init__(self, now_fn: Callable[[], float] | None = None) -> None:
        self._now_fn = now_fn or time.time

    def now(self) -> float:
        return self._now_fn()

    def iso_now(self) -> str:
        from datetime import datetime, timezone

        return datetime.fromtimestamp(self.now(), tz=timezone.utc).isoformat()


clock = Clock()
