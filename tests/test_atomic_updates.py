import sqlite3
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from task_manager.database import Database
from task_manager.repository import TaskRepository
from task_manager.service import TaskService


class AtomicUpdateTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "tasks.sqlite3"
        self.database = Database(self.path)
        self.addCleanup(self.database.close)
        self.repository = TaskRepository(self.database)
        self.service = TaskService(self.repository)
        self.moment = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
        self.task = self.service.create("Original", 1, description="Before", remind_at=self.moment)

    def test_multiple_fields_persist_together(self):
        new_time = self.moment + timedelta(hours=1)
        self.service.update(self.task.id, title="  Edited  ", description=None,
                            priority=3, due_at=new_time, remind_at=new_time)
        with Database(self.path) as reader:
            self.assertEqual(TaskRepository(reader).get(self.task.id), replace(
                self.task, title="Edited", description=None, priority=3,
                due_at=new_time, remind_at=new_time,
            ))

    def test_database_error_rolls_back_fields_status_and_trigger_writes(self):
        self.repository.mark_reminder_sent(self.task.id, expected_remind_at=self.moment)
        before = self.service.get(self.task.id)
        self.database.connection.executescript("""
            CREATE TABLE edit_log (title TEXT);
            CREATE TRIGGER fail_edit AFTER UPDATE OF title ON tasks
            BEGIN
                INSERT INTO edit_log VALUES (NEW.title);
                UPDATE tasks SET description = 'partial write' WHERE id = NEW.id;
                SELECT RAISE(ABORT, 'edit rejected');
            END;
        """)
        with self.assertRaisesRegex(sqlite3.IntegrityError, "edit rejected"):
            self.service.update(self.task.id, title="Edited", priority=3,
                                remind_at=self.moment + timedelta(hours=1))
        self.assertFalse(self.database.connection.in_transaction)
        with Database(self.path) as reader:
            self.assertEqual(TaskRepository(reader).get(self.task.id), before)
            self.assertEqual(reader.connection.execute("SELECT * FROM edit_log").fetchall(), [])

    def test_all_values_are_validated_before_any_write(self):
        for changes in ({"title": "Edited", "priority": 4},
                        {"title": "Edited", "due_at": datetime(2026, 1, 1)},
                        {"title": " ", "description": "Edited"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.service.update(self.task.id, **changes)
            self.assertEqual(self.service.get(self.task.id), self.task)

    def test_reminder_unchanged_or_not_edited_preserves_current_status(self):
        self.repository.mark_reminder_sent(self.task.id, expected_remind_at=self.moment)
        self.service.update(self.task.id, title="Edited", remind_at=self.moment)
        self.service.update(self.task.id, description="Changed")
        self.assertEqual(self.service.get(self.task.id), replace(
            self.task, title="Edited", description="Changed", reminder_sent=True,
        ))

    def test_changed_and_removed_reminders_reset_status(self):
        self.repository.mark_reminder_sent(self.task.id, expected_remind_at=self.moment)
        new_time = self.moment + timedelta(hours=1)
        self.service.update(self.task.id, title="Edited", remind_at=new_time)
        self.assertFalse(self.service.get(self.task.id).reminder_sent)
        self.repository.mark_reminder_sent(self.task.id, expected_remind_at=new_time)
        self.service.update(self.task.id, remind_at=None, description=None)
        self.assertEqual(self.service.get(self.task.id), replace(
            self.task, title="Edited", description=None, remind_at=None,
        ))

    def test_status_change_after_service_read_is_preserved(self):
        original_get = self.repository.get

        def read_then_mark(task_id):
            stale = original_get(task_id)
            with Database(self.path) as other_database:
                TaskRepository(other_database).mark_reminder_sent(
                    task_id, expected_remind_at=self.moment,
                )
            return stale

        with patch.object(self.repository, "get", side_effect=read_then_mark):
            self.service.update(self.task.id, title="Edited", remind_at=self.moment)
        self.assertEqual(self.service.get(self.task.id), replace(self.task, title="Edited", reminder_sent=True))

    def test_reset_compares_against_current_database_timestamp(self):
        original_get = self.repository.get
        other_time = self.moment + timedelta(hours=1)

        def read_then_reschedule(task_id):
            stale = original_get(task_id)
            with Database(self.path) as other_database:
                other = TaskRepository(other_database)
                other.update_reminder(task_id, other_time, reminder_sent=True)
            return stale

        with patch.object(self.repository, "get", side_effect=read_then_reschedule):
            self.service.update(self.task.id, remind_at=self.moment)
        self.assertEqual(self.service.get(self.task.id), self.task)

    def test_immutable_fields_and_unknown_fields_are_rejected(self):
        for name, value in (("id", self.task.id), ("created_at", self.moment),
                            ("reminder_sent", True), ("title = 'injected' --", "bad")):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    self.service.update(self.task.id, **{name: value})
                with self.assertRaises(ValueError):
                    self.repository.update_fields(self.task.id, {name: value})
        self.assertEqual(self.service.get(self.task.id), self.task)

    def test_deleted_task_between_read_and_write_is_reported(self):
        original_get = self.repository.get

        def read_then_delete(task_id):
            stale = original_get(task_id)
            with Database(self.path) as other_database:
                TaskRepository(other_database).delete(task_id)
            return stale

        with patch.object(self.repository, "get", side_effect=read_then_delete):
            with self.assertRaises(KeyError):
                self.service.update(self.task.id, title="Edited", priority=3)
        self.assertIsNone(self.repository.get(self.task.id))


if __name__ == "__main__":
    unittest.main()
