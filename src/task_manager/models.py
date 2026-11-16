"""Task values, with timezone-aware timestamps normalized to UTC."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4


@dataclass(frozen=True)
class Task:
    title: str
    priority: int
    id: UUID = field(default_factory=uuid4)
    description: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    due_at: Optional[datetime] = None
    remind_at: Optional[datetime] = None
    reminder_sent: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID) or self.id.version != 4:
            raise ValueError("id must be a UUID4")
        if not isinstance(self.title, str):
            raise TypeError("title must be a string")
        if self.description is not None and not isinstance(self.description, str):
            raise TypeError("description must be a string or None")
        if type(self.priority) is not int or self.priority not in (1, 2, 3):
            raise ValueError("priority must be an integer from 1 to 3")
        if type(self.reminder_sent) is not bool:
            raise TypeError("reminder_sent must be a boolean")
        for name in ("created_at", "due_at", "remind_at"):
            value = getattr(self, name)
            if value is None and name != "created_at":
                continue
            if not isinstance(value, datetime):
                raise TypeError(f"{name} must be a datetime")
            if value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
            object.__setattr__(self, name, value.astimezone(timezone.utc))
