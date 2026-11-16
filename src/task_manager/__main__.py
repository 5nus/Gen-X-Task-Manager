"""Launch the desktop application with a persistent SQLite database."""

import argparse
import os
import sqlite3
import sys
import tkinter as tk
from pathlib import Path

from .database import Database
from .gui import TaskApp
from .repository import TaskRepository
from .service import TaskService


def main() -> int:
    data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    parser = argparse.ArgumentParser(description="Task Manager für Linux")
    parser.add_argument("--database", type=Path, default=data_home / "task-manager" / "tasks.sqlite3")
    args = parser.parse_args()
    root = None
    try:
        root = tk.Tk()
        args.database.parent.mkdir(parents=True, exist_ok=True)
        with Database(args.database) as database:
            TaskApp(root, TaskService(TaskRepository(database)))
            root.mainloop()
    except (OSError, sqlite3.Error, tk.TclError) as error:
        print(f"Task Manager konnte nicht gestartet werden: {error}", file=sys.stderr)
        return 1
    finally:
        if root is not None:
            try:
                root.destroy()
            except tk.TclError:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
