"""Parameterized SQL operations for task persistence."""

import sqlite3
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from .database import Database
from .models import Task


def _timestamp(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError("timestamp must be a datetime or None")
    if value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _create_values(task: Task) -> tuple:
    return (
        task.title,
        task.description,
        task.priority,
        _timestamp(task.created_at),
        _timestamp(task.due_at),
        _timestamp(task.remind_at),
        int(task.reminder_sent),
        str(task.id),
    )


def _from_row(row: sqlite3.Row) -> Task:
    return Task(
        id=UUID(row["id"]),
        title=row["title"],
        description=row["description"],
        priority=row["priority"],
        created_at=datetime.fromisoformat(row["created_at"]),
        due_at=datetime.fromisoformat(row["due_at"]) if row["due_at"] else None,
        remind_at=datetime.fromisoformat(row["remind_at"]) if row["remind_at"] else None,
        reminder_sent=bool(row["reminder_sent"]),
    )


class TaskRepository:
    def __init__(self, database: Database) -> None:
        self._connection = database.connection

    def create(self, task: Task) -> Task:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO tasks (
                    title, description, priority, created_at,
                    due_at, remind_at, reminder_sent, id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _create_values(task),
            )
        return task

    def get(self, task_id: UUID) -> Optional[Task]:
        row = self._connection.execute(
            "SELECT * FROM tasks WHERE id = ?", (str(task_id),)
        ).fetchone()
        return _from_row(row) if row is not None else None

    def list_all(self) -> List[Task]:
        rows = self._connection.execute(
            "SELECT * FROM tasks ORDER BY priority DESC, created_at, id"
        ).fetchall()
        return [_from_row(row) for row in rows]

    def _write(self, sql: str, parameters: tuple) -> bool:
        with self._connection:
            cursor = self._connection.execute(sql, parameters)
        return cursor.rowcount == 1

    def update_title(self, task_id: UUID, title: str) -> bool:
        if not isinstance(title, str):
            raise TypeError("title must be a string")
        return self._write(
            "UPDATE tasks SET title = ? WHERE id = ?", (title, str(task_id))
        )

    def update_description(self, task_id: UUID, description: Optional[str]) -> bool:
        if description is not None and not isinstance(description, str):
            raise TypeError("description must be a string or None")
        return self._write(
            "UPDATE tasks SET description = ? WHERE id = ?", (description, str(task_id))
        )

    def update_priority(self, task_id: UUID, priority: int) -> bool:
        if type(priority) is not int or priority not in (1, 2, 3):
            raise ValueError("priority must be an integer from 1 to 3")
        return self._write(
            "UPDATE tasks SET priority = ? WHERE id = ?", (priority, str(task_id))
        )

    def update_due_at(self, task_id: UUID, due_at: Optional[datetime]) -> bool:
        return self._write(
            "UPDATE tasks SET due_at = ? WHERE id = ?", (_timestamp(due_at), str(task_id))
        )

    def update_reminder(
        self, task_id: UUID, remind_at: Optional[datetime], *, reminder_sent: bool
    ) -> bool:
        """Persist both values atomically; the caller decides whether to reset."""
        if type(reminder_sent) is not bool:
            raise TypeError("reminder_sent must be a boolean")
        return self._write(
            "UPDATE tasks SET remind_at = ?, reminder_sent = ? WHERE id = ?",
            (_timestamp(remind_at), int(reminder_sent), str(task_id)),
        )

    def mark_reminder_sent(self, task_id: UUID, *, expected_remind_at: datetime) -> bool:
        """Mark only the current, unsent reminder of an existing task."""
        if not isinstance(expected_remind_at, datetime):
            raise TypeError("expected_remind_at must be a datetime")
        return self._write(
            """
            UPDATE tasks SET reminder_sent = 1
            WHERE id = ? AND remind_at = ? AND reminder_sent = 0
            """,
            (str(task_id), _timestamp(expected_remind_at)),
        )

    def delete(self, task_id: UUID) -> bool:
        return self._write("DELETE FROM tasks WHERE id = ?", (str(task_id),))
