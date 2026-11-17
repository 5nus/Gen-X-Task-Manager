"""Launch the desktop application with a persistent SQLite database."""

import argparse
import sqlite3
import sys
import tkinter as tk
from pathlib import Path

from . import __version__
from .database import Database, default_database_path
from .gui import TaskApp
from .repository import TaskRepository
from .service import TaskService


def main() -> int:
    parser = argparse.ArgumentParser(description="genxtask")
    parser.add_argument("--version", action="version", version=f"genxtask v{__version__}")
    parser.add_argument("--database", type=Path, default=default_database_path())
    args = parser.parse_args()
    args.database = args.database.expanduser().resolve()
    root = None
    try:
        root = tk.Tk(className="genxtask")
        args.database.parent.mkdir(parents=True, exist_ok=True)
        with Database(args.database) as database:
            TaskApp(root, TaskService(TaskRepository(database)))
            root.mainloop()
    except (OSError, sqlite3.Error, tk.TclError) as error:
        print(f"genxtask could not open the database: {error}", file=sys.stderr)
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
