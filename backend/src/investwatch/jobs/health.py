"""Container healthchecks for Celery processes: `python -m investwatch.jobs.health worker|beat`."""

from __future__ import annotations

import socket
import sys
import time
from pathlib import Path

BEAT_SCHEDULE_FILE = Path("/tmp/celerybeat-schedule")
BEAT_MAX_AGE_S = 300


def worker_ok() -> bool:
    """Ping this host's worker through the broker."""
    from investwatch.jobs.celery_app import celery_app

    replies = celery_app.control.ping(destination=[f"celery@{socket.gethostname()}"], timeout=5)
    return bool(replies)


def beat_ok() -> bool:
    """Beat rewrites its schedule file after every tick."""
    files = list(BEAT_SCHEDULE_FILE.parent.glob(BEAT_SCHEDULE_FILE.name + "*"))
    return any(time.time() - f.stat().st_mtime < BEAT_MAX_AGE_S for f in files)


if __name__ == "__main__":
    role = sys.argv[1] if len(sys.argv) > 1 else "worker"
    sys.exit(0 if (beat_ok() if role == "beat" else worker_ok()) else 1)
