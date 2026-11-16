"""One-shot Linux desktop reminder process, suitable for a systemd user timer."""

import argparse
import html
import logging
import os
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .database import Database, default_database_path
from .repository import TaskRepository


LOGGER = logging.getLogger(__name__)


def send_notification(title: str) -> None:
    """Success means the notification service accepted the request, not seen."""
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        raise OSError("No graphical session in the reminder environment")
    if not os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        raise OSError("DBUS_SESSION_BUS_ADDRESS is missing from the reminder environment")
    subprocess.run(
        ["notify-send", "--app-name=Gen X Task Manager", "--",
         "Task Reminder", html.escape(title, quote=False)],
        check=True, timeout=5, capture_output=True, text=True,
    )


def run_once(database: Database, *, now=None, notify=None) -> int:
    """Process due reminders; return the number of failed notification attempts.

    A writer lock protects the recheck, bounded notification call and status
    write. GUI edits and other reminder processes serialize at this point.
    A crash after delivery but before commit may cause another delivery.
    """
    now = now if now is not None else datetime.now(timezone.utc)
    notify = notify if notify is not None else send_notification
    repository = TaskRepository(database)
    failures = 0
    for candidate in repository.list_due_reminders(now):
        try:
            with database.transaction():
                current = repository.get(candidate.id)
                if (current is None or current.reminder_sent or
                        current.remind_at != candidate.remind_at or current.remind_at > now):
                    continue
                notify(current.title)
                if not repository.mark_reminder_sent(current.id, expected_remind_at=current.remind_at):
                    raise sqlite3.IntegrityError("Reminder status changed during delivery")
            LOGGER.info("Reminder accepted for task %s", candidate.id)
        except (OSError, subprocess.SubprocessError) as error:
            failures += 1
            if isinstance(error, subprocess.CalledProcessError):
                reason = f"notify-send exited with status {error.returncode}"
            elif isinstance(error, subprocess.TimeoutExpired):
                reason = "notify-send timed out after 5 seconds"
            else:
                reason = str(error)
            LOGGER.error("Notification failed for task %s: %s; will retry", candidate.id, reason)
    return failures


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Send due Gen X Task Manager reminders once")
    parser.add_argument("--database", type=Path, default=default_database_path())
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    path = args.database.expanduser().resolve()
    LOGGER.info("Reminder database: %s", path)
    if not path.is_file():
        LOGGER.info("No task database yet; nothing to process")
        return 0
    try:
        with Database(path) as database:
            return 1 if run_once(database) else 0
    except (OSError, sqlite3.Error) as error:
        LOGGER.error("Reminder run failed (%s): %s", type(error).__name__, error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
