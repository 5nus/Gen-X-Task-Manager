import sqlite3
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from task_manager.database import Database
from task_manager.repository import TaskRepository
from task_manager.service import TaskService


class TaskServiceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "tasks.sqlite3"
        self.database = Database(self.path)
        self.addCleanup(self.database.close)
        self.repository = TaskRepository(self.database)
        self.service = TaskService(self.repository)
        self.moment = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)

    def test_create_persists_all_inputs_with_fresh_defaults(self):
        task = self.service.create(
            "Aufgabe", 3, description="Details", due_at=self.moment,
            remind_at=self.moment - timedelta(hours=1),
        )
        self.assertEqual(task.id.version, 4)
        self.assertFalse(task.reminder_sent)
        self.assertEqual(task.created_at.tzinfo, timezone.utc)
        self.assertEqual(task.description, "Details")
        self.assertEqual(task.due_at, self.moment)
        self.assertEqual(task.remind_at, self.moment - timedelta(hours=1))
        with Database(self.path) as reader:
            self.assertEqual(TaskRepository(reader).get(task.id), task)

    def test_invalid_titles_are_rejected_on_create_and_edit(self):
        task = self.service.create("Original", 1)
        for title, error in (("", ValueError), (" \n\t", ValueError),
                             ("ä" * 201, ValueError), (None, TypeError)):
            with self.subTest(title=title):
                with self.assertRaises(error):
                    self.service.create(title, 1)
                with self.assertRaises(error):
                    self.service.update_title(task.id, title)
                self.assertEqual(self.service.list_all(), [task])

    def test_title_boundaries_after_stripping_on_create_and_edit(self):
        task = self.service.create("Original", 1)
        for length in (0, 1, 200, 201):
            for padded in (False, True):
                with self.subTest(length=length, padded=padded):
                    normalized = "ä" * length
                    title = f" \t{normalized}\n " if padded else normalized
                    if length in (0, 201):
                        before = self.service.list_all()
                        with self.assertRaises(ValueError):
                            self.service.create(title, 1)
                        with self.assertRaises(ValueError):
                            self.service.update_title(task.id, title)
                        self.assertEqual(self.service.list_all(), before)
                    else:
                        created = self.service.create(title, 1)
                        self.assertEqual(self.service.get(created.id).title, normalized)
                        self.service.update_title(task.id, title)
                        self.assertEqual(self.service.get(task.id).title, normalized)

    def test_long_content_can_be_stored_in_description(self):
        description = "Details " * 100
        task = self.service.create("Kurzer Titel", 1, description=description)
        self.assertEqual(self.service.get(task.id).description, description)
        self.service.update_description(task.id, description * 2)
        self.assertEqual(self.service.get(task.id).description, description * 2)

    def test_edits_preserve_unrelated_fields_and_clear_optional_values(self):
        task = self.service.create("Alt", 1, remind_at=self.moment)
        self.assertTrue(self.repository.mark_reminder_sent(task.id, expected_remind_at=self.moment))
        expected = replace(task, reminder_sent=True)
        for field, value in (("title", "Neu"), ("description", "Text"),
                             ("priority", 3), ("due_at", self.moment),
                             ("description", None), ("due_at", None)):
            with self.subTest(field=field, value=value):
                getattr(self.service, "update_" + field)(task.id, value)
                expected = replace(expected, **{field: value})
                self.assertEqual(self.service.get(task.id), expected)

    def test_changed_or_removed_reminder_resets_status(self):
        task = self.service.create("Reminder", 1, remind_at=self.moment)
        with Database(self.path) as other_database:
            other = TaskRepository(other_database)
            for new_time in (self.moment + timedelta(hours=1), None):
                with self.subTest(new_time=new_time):
                    current = other.get(task.id)
                    self.assertTrue(other.mark_reminder_sent(task.id, expected_remind_at=current.remind_at))
                    self.service.update_reminder(task.id, new_time)
                    self.assertEqual(other.get(task.id), replace(task, remind_at=new_time))
                    self.assertFalse(other.mark_reminder_sent(task.id, expected_remind_at=current.remind_at))

    def test_adding_reminder_resets_status(self):
        task = self.service.create("Reminder", 1)
        self.repository.update_reminder(task.id, None, reminder_sent=True)
        self.service.update_reminder(task.id, self.moment)
        self.assertEqual(self.service.get(task.id), replace(task, remind_at=self.moment))

    def test_equivalent_reminder_preserves_sent_status_without_writing(self):
        task = self.service.create("Reminder", 1, remind_at=self.moment)
        self.repository.mark_reminder_sent(task.id, expected_remind_at=self.moment)
        equivalent = self.moment.astimezone(timezone(timedelta(hours=2)))
        with patch.object(self.repository, "update_reminder") as update:
            self.service.update_reminder(task.id, equivalent)
            update.assert_not_called()
        self.assertEqual(self.service.get(task.id), replace(task, reminder_sent=True))

    def test_title_edit_preserves_changes_from_other_connection(self):
        task = self.service.create("Original", 1, remind_at=self.moment)
        stale = self.service.get(task.id)
        new_time = self.moment + timedelta(hours=1)
        with Database(self.path) as other_database:
            other = TaskRepository(other_database)
            other.update_reminder(task.id, new_time, reminder_sent=False)
            other.mark_reminder_sent(task.id, expected_remind_at=new_time)
            other.update_description(task.id, "Andere Änderung")
            self.service.update_title(stale.id, "Neuer Titel")
            self.assertEqual(other.get(task.id), replace(
                task, title="Neuer Titel", description="Andere Änderung",
                remind_at=new_time, reminder_sent=True,
            ))

    def test_delete_blocks_subsequent_marking(self):
        task = self.service.create("Löschen", 1, remind_at=self.moment)
        self.service.delete(task.id)
        with Database(self.path) as other_database:
            self.assertFalse(TaskRepository(other_database).mark_reminder_sent(
                task.id, expected_remind_at=self.moment
            ))
        self.assertEqual(self.service.list_all(), [])
        with self.assertRaises(KeyError):
            self.service.get(task.id)

    def test_delete_persists_and_missing_tasks_raise_key_error(self):
        task = self.service.create("Löschen", 1)
        self.service.delete(task.id)
        with Database(self.path) as reader:
            self.assertIsNone(TaskRepository(reader).get(task.id))
        missing = uuid4()
        for method, args in (
            ("get", ()), ("delete", ()),
            ("update_title", ("Neu",)), ("update_description", (None,)),
            ("update_priority", (2,)), ("update_due_at", (None,)),
            ("update_reminder", (None,)),
        ):
            with self.subTest(method=method), self.assertRaises(KeyError) as raised:
                getattr(self.service, method)(missing, *args)
            self.assertEqual(raised.exception.args, (missing,))

    def test_invalid_values_do_not_change_persistence(self):
        task = self.service.create("Valid", 1)
        for method, value, error in (
            ("update_priority", 4, ValueError),
            ("update_description", 5, TypeError),
            ("update_due_at", datetime(2026, 1, 1), ValueError),
            ("update_reminder", datetime(2026, 1, 1), ValueError),
        ):
            with self.subTest(method=method):
                with self.assertRaises(error):
                    getattr(self.service, method)(task.id, value)
                self.assertEqual(self.service.get(task.id), task)
        with self.assertRaises(ValueError):
            self.service.create("Valid", 4)
        self.assertEqual(self.service.list_all(), [task])

    def test_database_write_error_propagates_and_rolls_back(self):
        task = self.service.create("Original", 1)
        self.database.connection.execute("""
            CREATE TRIGGER reject_title BEFORE UPDATE OF title ON tasks
            BEGIN SELECT RAISE(ABORT, 'test write failure'); END
        """)
        with self.assertRaisesRegex(sqlite3.IntegrityError, "test write failure"):
            self.service.update_title(task.id, "Neu")
        self.assertFalse(self.database.connection.in_transaction)
        self.assertEqual(self.service.get(task.id), task)

    def test_database_read_error_is_not_reported_as_missing_task(self):
        self.database.close()
        with self.assertRaises(sqlite3.ProgrammingError):
            self.service.get(uuid4())


if __name__ == "__main__":
    unittest.main()
