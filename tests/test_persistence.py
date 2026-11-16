import sqlite3
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid1, uuid4

from task_manager.database import Database
from task_manager.models import Task
from task_manager.repository import TaskRepository


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "tasks.sqlite3"
        self.database = Database(self.path)
        self.addCleanup(self.database.close)
        self.repository = TaskRepository(self.database)

    def test_defaults_and_optional_fields_round_trip(self):
        task = Task(title="Einkaufen", priority=2)
        self.assertEqual(task.id.version, 4)
        self.assertEqual(task.created_at.tzinfo, timezone.utc)
        self.assertFalse(task.reminder_sent)
        self.assertIsNone(task.description)
        self.assertIsNone(task.due_at)
        self.assertIsNone(task.remind_at)
        self.assertEqual(self.repository.create(task), task)
        self.assertEqual(self.repository.get(task.id), task)

    def test_all_fields_survive_reopening(self):
        moment = datetime(2026, 11, 16, 15, 30, 20, 123456, timezone.utc)
        task = Task(
            title="Bericht", priority=3, description="Details äöü",
            created_at=moment, due_at=moment + timedelta(days=1),
            remind_at=moment + timedelta(hours=1), reminder_sent=True,
        )
        self.repository.create(task)
        self.database.close()
        with Database(self.path) as reopened:
            self.assertEqual(TaskRepository(reopened).get(task.id), task)

    def test_timestamps_stored_as_utc(self):
        local = datetime(2026, 11, 16, 15, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
        expected = "2026-11-16T10:00:00.000000+00:00"
        task = Task(title="UTC", priority=1, created_at=local, due_at=local, remind_at=local)
        self.repository.create(task)
        row = self.database.connection.execute(
            "SELECT created_at, due_at, remind_at FROM tasks WHERE id = ?",
            (str(task.id),),
        ).fetchone()
        self.assertEqual(tuple(row), (expected, expected, expected))
        self.assertEqual(self.repository.get(task.id), task)

    def test_list_is_complete_and_ordered(self):
        self.assertEqual(self.repository.list_all(), [])
        earlier = Task(title="Früher", priority=1, created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        later = replace(earlier, id=uuid4(), title="Später", created_at=earlier.created_at + timedelta(days=1))
        medium = replace(later, id=uuid4(), title="Mittel", priority=2)
        highest = replace(later, id=uuid4(), title="Höchste", priority=3)
        self.repository.create(later)
        self.repository.create(medium)
        self.repository.create(earlier)
        self.repository.create(highest)
        self.assertEqual(self.repository.list_all(), [highest, medium, earlier, later])

    def test_targeted_updates_preserve_other_fields_and_persist(self):
        task = Task(title="Alt", priority=1, reminder_sent=True)
        self.repository.create(task)
        moment = datetime(2026, 11, 16, tzinfo=timezone.utc)
        for field, value in (
            ("title", "Neu"), ("description", "Text"),
            ("priority", 3), ("due_at", moment), ("description", None),
            ("due_at", None),
        ):
            with self.subTest(field=field, value=value):
                self.assertTrue(getattr(self.repository, "update_" + field)(task.id, value))
                task = replace(task, **{field: value})
                with Database(self.path) as reader:
                    self.assertEqual(TaskRepository(reader).get(task.id), task)

    def test_delete_is_persisted(self):
        task = Task(title="Löschen", priority=2)
        self.repository.create(task)
        self.assertTrue(self.repository.delete(task.id))
        self.assertFalse(self.repository.delete(task.id))
        with Database(self.path) as reader:
            self.assertIsNone(TaskRepository(reader).get(task.id))

    def test_title_edit_preserves_concurrent_reminder_and_other_changes(self):
        moment = datetime(2026, 11, 16, tzinfo=timezone.utc)
        task = Task(title="Original", priority=1, remind_at=moment)
        self.repository.create(task)
        stale = self.repository.get(task.id)
        new_time = moment + timedelta(hours=1)
        with Database(self.path) as other_database:
            other = TaskRepository(other_database)
            self.assertTrue(other.update_reminder(task.id, new_time, reminder_sent=False))
            self.assertTrue(other.mark_reminder_sent(task.id, expected_remind_at=new_time))
            self.assertTrue(other.update_priority(task.id, 3))
            self.assertTrue(self.repository.update_title(stale.id, "Bearbeitet"))
            self.assertEqual(
                other.get(task.id),
                replace(task, title="Bearbeitet", priority=3, remind_at=new_time,
                        reminder_sent=True),
            )

    def test_reminder_change_resets_atomically_and_rejects_stale_mark(self):
        moment = datetime(2026, 11, 16, tzinfo=timezone.utc)
        task = Task(title="Reminder", priority=1, remind_at=moment, reminder_sent=True)
        self.repository.create(task)
        new_time = moment + timedelta(hours=1)
        with Database(self.path) as service_database:
            service = TaskRepository(service_database)
            self.assertTrue(self.repository.update_reminder(task.id, new_time, reminder_sent=False))
            self.assertEqual(service.get(task.id), replace(task, remind_at=new_time, reminder_sent=False))
            self.assertFalse(service.mark_reminder_sent(task.id, expected_remind_at=moment))
            self.assertEqual(service.get(task.id), replace(task, remind_at=new_time, reminder_sent=False))
            self.assertTrue(service.mark_reminder_sent(task.id, expected_remind_at=new_time))
            self.assertEqual(service.get(task.id), replace(task, remind_at=new_time))
            self.assertFalse(service.mark_reminder_sent(task.id, expected_remind_at=new_time))

    def test_deleted_task_cannot_be_marked_or_recreated_by_stale_updates(self):
        moment = datetime(2026, 11, 16, tzinfo=timezone.utc)
        task = Task(title="Reminder", priority=1, remind_at=moment)
        self.repository.create(task)
        with Database(self.path) as service_database:
            service = TaskRepository(service_database)
            stale = service.get(task.id)
            self.assertTrue(self.repository.delete(task.id))
            self.assertFalse(service.mark_reminder_sent(
                stale.id, expected_remind_at=stale.remind_at
            ))
            self.assertFalse(service.update_reminder(stale.id, moment, reminder_sent=False))
            self.assertFalse(service.update_title(stale.id, "Veraltet"))
            self.assertIsNone(service.get(task.id))
            self.assertEqual(service.list_all(), [])

    def test_reminder_change_after_mark_resets_status(self):
        moment = datetime(2026, 11, 16, tzinfo=timezone.utc)
        task = Task(title="Reminder", priority=1, remind_at=moment)
        self.repository.create(task)
        with Database(self.path) as service_database:
            service = TaskRepository(service_database)
            self.assertTrue(service.mark_reminder_sent(task.id, expected_remind_at=moment))
            self.assertEqual(service.get(task.id), replace(task, reminder_sent=True))
            new_time = moment + timedelta(hours=1)
            self.assertTrue(self.repository.update_reminder(task.id, new_time, reminder_sent=False))
            self.assertEqual(service.get(task.id), replace(task, remind_at=new_time))

    def test_reminder_status_is_explicit_and_reminder_can_be_removed(self):
        moment = datetime(2026, 11, 16, tzinfo=timezone.utc)
        task = Task(title="Reminder", priority=1)
        self.repository.create(task)
        self.assertTrue(self.repository.update_reminder(task.id, moment, reminder_sent=True))
        self.assertEqual(self.repository.get(task.id), replace(task, remind_at=moment, reminder_sent=True))
        self.assertTrue(self.repository.update_reminder(task.id, None, reminder_sent=False))
        self.assertEqual(self.repository.get(task.id), task)
        self.assertFalse(self.repository.mark_reminder_sent(task.id, expected_remind_at=moment))

    def test_update_and_mark_normalize_timestamps_to_utc(self):
        local = datetime(2026, 11, 16, 15, 30, tzinfo=timezone(timedelta(hours=2)))
        utc = local.astimezone(timezone.utc)
        task = Task(title="UTC", priority=1)
        self.repository.create(task)
        self.assertTrue(self.repository.update_due_at(task.id, local))
        self.assertTrue(self.repository.update_reminder(task.id, local, reminder_sent=False))
        row = self.database.connection.execute(
            "SELECT due_at, remind_at FROM tasks WHERE id = ?", (str(task.id),)
        ).fetchone()
        self.assertEqual(tuple(row), (utc.isoformat(timespec="microseconds"),) * 2)
        self.assertTrue(self.repository.mark_reminder_sent(task.id, expected_remind_at=utc))
        self.assertEqual(self.repository.get(task.id), replace(task, due_at=utc, remind_at=utc, reminder_sent=True))

    def test_invalid_update_values_leave_task_unchanged(self):
        task = Task(title="Valid", priority=1)
        self.repository.create(task)
        for method, args, kwargs, error in (
            ("update_title", (None,), {}, TypeError),
            ("update_description", (1,), {}, TypeError),
            ("update_priority", (True,), {}, ValueError),
            ("update_priority", (4,), {}, ValueError),
            ("update_due_at", (datetime(2026, 1, 1),), {}, ValueError),
            ("update_due_at", ("invalid",), {}, TypeError),
            ("update_reminder", (datetime(2026, 1, 1),), {"reminder_sent": False}, ValueError),
            ("update_reminder", (None,), {"reminder_sent": 1}, TypeError),
            ("mark_reminder_sent", (), {"expected_remind_at": None}, TypeError),
            ("mark_reminder_sent", (), {"expected_remind_at": datetime(2026, 1, 1)}, ValueError),
        ):
            with self.subTest(method=method, args=args, kwargs=kwargs):
                with self.assertRaises(error):
                    getattr(self.repository, method)(task.id, *args, **kwargs)
                self.assertFalse(self.database.connection.in_transaction)
                self.assertEqual(self.repository.get(task.id), task)

    def test_missing_task(self):
        task = Task(title="Fehlt", priority=1)
        self.assertIsNone(self.repository.get(task.id))
        self.assertFalse(self.repository.update_title(task.id, "Neu"))
        self.assertFalse(self.repository.update_description(task.id, None))
        self.assertFalse(self.repository.update_priority(task.id, 3))
        self.assertFalse(self.repository.update_due_at(task.id, None))
        self.assertFalse(self.repository.update_reminder(task.id, None, reminder_sent=False))
        self.assertFalse(self.repository.mark_reminder_sent(task.id, expected_remind_at=task.created_at))
        self.assertFalse(self.repository.delete(task.id))
        self.assertEqual(self.repository.list_all(), [])

    def test_sql_text_is_stored_as_data(self):
        task = Task(title="'); DROP TABLE tasks; --", priority=1,
                    description="Unicode: Grüße; ' OR 1=1 --")
        self.repository.create(task)
        changed = replace(task, title="UPDATE tasks SET title = 'x'; --")
        self.assertTrue(self.repository.update_title(task.id, changed.title))
        self.assertEqual(self.repository.list_all(), [changed])

    def test_duplicate_id_rolls_back_and_connection_remains_usable(self):
        task = Task(title="Original", priority=1)
        self.repository.create(task)
        with self.assertRaises(sqlite3.IntegrityError):
            self.repository.create(replace(task, title="Duplikat"))
        self.assertFalse(self.database.connection.in_transaction)
        self.assertEqual(self.repository.get(task.id), task)
        another = Task(title="Weitere Aufgabe", priority=2)
        self.repository.create(another)
        with Database(self.path) as reader:
            self.assertEqual(len(TaskRepository(reader).list_all()), 2)

    def test_database_rejects_invalid_priority_and_boolean(self):
        task = Task(title="Valid", priority=1)
        self.repository.create(task)
        for statement, value in (
            ("UPDATE tasks SET priority = ? WHERE id = ?", 4),
            ("UPDATE tasks SET priority = ? WHERE id = ?", 1.5),
            ("UPDATE tasks SET reminder_sent = ? WHERE id = ?", -1),
        ):
            with self.subTest(value=value, statement=statement):
                with self.assertRaises(sqlite3.IntegrityError):
                    with self.database.connection:
                        self.database.connection.execute(statement, (value, str(task.id)))
                self.assertEqual(self.repository.get(task.id), task)

    def test_model_rejects_naive_timestamps(self):
        for field in ("created_at", "due_at", "remind_at"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                Task(title="Invalid", priority=1, **{field: datetime(2026, 1, 1)})

    def test_model_rejects_invalid_values(self):
        for values, error in (
            ({"priority": 0}, ValueError),
            ({"priority": 4}, ValueError),
            ({"priority": True}, ValueError),
            ({"priority": 1.5}, ValueError),
            ({"id": uuid1()}, ValueError),
            ({"title": None}, TypeError),
            ({"description": 1}, TypeError),
            ({"reminder_sent": 0}, TypeError),
            ({"created_at": None}, TypeError),
        ):
            with self.subTest(values=values), self.assertRaises(error):
                Task(**({"title": "Invalid", "priority": 1} | values))


if __name__ == "__main__":
    unittest.main()
