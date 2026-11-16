"""Business rules for task creation and targeted changes."""

from dataclasses import replace
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from .models import Task
from .repository import TaskRepository


MAX_TITLE_LENGTH = 200


def _normalize_title(title: str) -> str:
    if not isinstance(title, str):
        raise TypeError("title must be a string")
    title = title.strip()
    if not title:
        raise ValueError("title must not be empty or whitespace-only")
    if len(title) > MAX_TITLE_LENGTH:
        raise ValueError(f"title must not exceed {MAX_TITLE_LENGTH} characters")
    return title


def _require_updated(task_id: UUID, updated: bool) -> None:
    if not updated:
        raise KeyError(task_id)


class TaskService:
    """Use targeted repository operations without writing stale task snapshots.

    Missing tasks raise KeyError. SQLite errors propagate to the caller.
    Mutation methods return None; create and get return a Task.
    """

    def __init__(self, repository: TaskRepository) -> None:
        self._repository = repository

    def create(
        self,
        title: str,
        priority: int,
        *,
        description: Optional[str] = None,
        due_at: Optional[datetime] = None,
        remind_at: Optional[datetime] = None,
    ) -> Task:
        title = _normalize_title(title)
        task = Task(
            title=title,
            priority=priority,
            description=description,
            due_at=due_at,
            remind_at=remind_at,
        )
        return self._repository.create(task)

    def get(self, task_id: UUID) -> Task:
        task = self._repository.get(task_id)
        if task is None:
            raise KeyError(task_id)
        return task

    def list_all(self) -> List[Task]:
        return self._repository.list_all()

    def update(self, task_id: UUID, **changes) -> None:
        """Validate an explicit edit and persist all its fields together."""
        allowed = {"title", "description", "priority", "due_at", "remind_at"}
        if set(changes) - allowed:
            raise ValueError("Only editable task fields may be updated")
        current = self.get(task_id)
        if not changes:
            return
        if "title" in changes:
            changes["title"] = _normalize_title(changes["title"])
        validated = replace(current, **changes)
        values = {name: getattr(validated, name) for name in changes}
        _require_updated(task_id, self._repository.update_fields(
            task_id, values, reset_reminder_if_changed="remind_at" in values,
        ))

    def update_title(self, task_id: UUID, title: str) -> None:
        title = _normalize_title(title)
        _require_updated(task_id, self._repository.update_title(task_id, title))

    def update_description(self, task_id: UUID, description: Optional[str]) -> None:
        _require_updated(task_id, self._repository.update_description(task_id, description))

    def update_priority(self, task_id: UUID, priority: int) -> None:
        _require_updated(task_id, self._repository.update_priority(task_id, priority))

    def update_due_at(self, task_id: UUID, due_at: Optional[datetime]) -> None:
        _require_updated(task_id, self._repository.update_due_at(task_id, due_at))

    def update_reminder(self, task_id: UUID, remind_at: Optional[datetime]) -> None:
        self.update(task_id, remind_at=remind_at)

    def delete(self, task_id: UUID) -> None:
        _require_updated(task_id, self._repository.delete(task_id))
