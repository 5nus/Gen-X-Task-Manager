"""SQLite connection ownership and initial schema."""

import sqlite3
from pathlib import Path
from typing import Union


class Database:
    """Own one connection; close it explicitly or use a context manager."""

    def __init__(self, path: Union[str, Path]) -> None:
        self.connection = sqlite3.connect(str(path))
        self.connection.row_factory = sqlite3.Row
        try:
            self.initialize_schema()
        except Exception:
            self.close()
            raise

    def initialize_schema(self) -> None:
        with self.connection:
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    priority INTEGER NOT NULL
                        CHECK (typeof(priority) = 'integer' AND priority BETWEEN 1 AND 3),
                    created_at TEXT NOT NULL,
                    due_at TEXT,
                    remind_at TEXT,
                    reminder_sent INTEGER NOT NULL DEFAULT 0
                        CHECK (reminder_sent IN (0, 1))
                )
                """
            )

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
