import multiprocessing
import os
import queue
import sqlite3
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from task_manager.database import Database, default_database_path
from task_manager.models import Task
from task_manager.reminder import main, run_once, send_notification
from task_manager.repository import TaskRepository


def _parallel_reminder(path, now, barrier, results):
    """Both processes collect the same candidate before trying to deliver it."""
    original = TaskRepository.list_due_reminders

    def collect(repository, moment):
        tasks = original(repository, moment)
        barrier.wait(timeout=10)
        return tasks

    notify = Mock(side_effect=lambda title: results.put(("notification", title)))
    with Database(path) as database:
        with patch.object(TaskRepository, "list_due_reminders", collect):
            results.put(("result", run_once(database, now=now, notify=notify)))


class ReminderTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "tasks.sqlite3"
        self.database = Database(self.path)
        self.addCleanup(self.database.close)
        self.repository = TaskRepository(self.database)
        self.now = datetime.now(timezone.utc)
        self.notify = Mock()

    def task(self, **values):
        return self.repository.create(Task(**({
            "title": "Submit tax documents", "priority": 2,
            "remind_at": self.now - timedelta(seconds=1),
        } | values)))

    def test_only_due_unsent_tasks_are_selected_in_utc(self):
        due = self.task()
        self.task(title="Future", remind_at=self.now + timedelta(days=1))
        self.task(title="No reminder", remind_at=None)
        self.task(title="Already sent", reminder_sent=True)
        local = self.now.astimezone(timezone(timedelta(hours=5)))
        self.assertEqual(self.repository.list_due_reminders(local), [due])
        with self.assertRaises(ValueError):
            self.repository.list_due_reminders(datetime(2026, 1, 1))

    def test_future_or_missing_reminder_does_not_notify(self):
        self.task(remind_at=self.now + timedelta(seconds=1))
        self.task(remind_at=None)
        self.assertEqual(run_once(self.database, now=self.now, notify=self.notify), 0)
        self.notify.assert_not_called()

    def test_due_reminder_is_marked_only_after_success(self):
        task = self.task()

        def notify(title):
            self.assertFalse(self.repository.get(task.id).reminder_sent)

        self.notify.side_effect = notify
        self.assertEqual(run_once(self.database, now=self.now, notify=self.notify), 0)
        self.notify.assert_called_once_with(task.title)
        self.assertTrue(self.repository.get(task.id).reminder_sent)
        self.assertFalse(self.database.connection.in_transaction)

    def test_failures_leave_reminder_open_for_retry(self):
        task = self.task()
        errors = (FileNotFoundError("notify-send not found"),
                  subprocess.CalledProcessError(1, ["notify-send"]),
                  subprocess.TimeoutExpired(["notify-send"], 5))
        for error in errors:
            with self.subTest(error=error):
                self.notify.side_effect = error
                with self.assertLogs("task_manager.reminder", level="ERROR"):
                    self.assertEqual(run_once(self.database, now=self.now, notify=self.notify), 1)
                self.assertFalse(self.repository.get(task.id).reminder_sent)
                self.assertFalse(self.database.connection.in_transaction)
        self.notify.side_effect = None
        self.assertEqual(run_once(self.database, now=self.now, notify=self.notify), 0)
        self.assertTrue(self.repository.get(task.id).reminder_sent)

    def test_restart_does_not_repeat_successful_reminders(self):
        self.task()
        run_once(self.database, now=self.now, notify=self.notify)
        with Database(self.path) as restarted:
            run_once(restarted, now=self.now, notify=self.notify)
        self.notify.assert_called_once()

    def test_missing_session_keeps_due_reminder_open_without_external_call(self):
        task = self.task()
        with patch.dict(os.environ, {}, clear=True):
            with patch("task_manager.reminder.subprocess.run") as run:
                with self.assertLogs("task_manager.reminder", level="ERROR"):
                    self.assertEqual(run_once(self.database, now=self.now), 1)
                run.assert_not_called()
        self.assertFalse(self.repository.get(task.id).reminder_sent)

    def test_overdue_reminder_is_caught_up(self):
        self.task(remind_at=self.now - timedelta(days=90))
        run_once(self.database, now=self.now, notify=self.notify)
        self.notify.assert_called_once()

    def test_deletion_after_query_is_rechecked_before_notification(self):
        task = self.task()
        original = TaskRepository.list_due_reminders

        def collect(repository, now):
            tasks = original(repository, now)
            with Database(self.path) as other:
                TaskRepository(other).delete(task.id)
            return tasks

        with patch.object(TaskRepository, "list_due_reminders", collect):
            run_once(self.database, now=self.now, notify=self.notify)
        self.notify.assert_not_called()
        self.assertIsNone(self.repository.get(task.id))

    def test_rescheduled_reminder_is_not_sent_or_marked_for_old_time(self):
        task = self.task()
        original = TaskRepository.list_due_reminders
        new_time = self.now + timedelta(days=1)

        def collect(repository, now):
            tasks = original(repository, now)
            with Database(self.path) as other:
                TaskRepository(other).update_reminder(task.id, new_time, reminder_sent=False)
            return tasks

        with patch.object(TaskRepository, "list_due_reminders", collect):
            run_once(self.database, now=self.now, notify=self.notify)
        self.notify.assert_not_called()
        self.assertFalse(self.repository.mark_reminder_sent(task.id, expected_remind_at=task.remind_at))
        self.assertEqual(self.repository.get(task.id).remind_at, new_time)
        self.assertFalse(self.repository.get(task.id).reminder_sent)

    def test_title_is_refreshed_before_notification(self):
        task = self.task()
        original = TaskRepository.list_due_reminders

        def collect(repository, now):
            tasks = original(repository, now)
            with Database(self.path) as other:
                TaskRepository(other).update_title(task.id, "Latest title")
            return tasks

        with patch.object(TaskRepository, "list_due_reminders", collect):
            run_once(self.database, now=self.now, notify=self.notify)
        self.notify.assert_called_once_with("Latest title")

    def test_database_failure_after_notification_keeps_status_open(self):
        task = self.task()
        self.database.connection.executescript("""
            CREATE TRIGGER reject_mark BEFORE UPDATE OF reminder_sent ON tasks
            BEGIN SELECT RAISE(ABORT, 'mark failed'); END;
        """)
        with self.assertRaisesRegex(sqlite3.IntegrityError, "mark failed"):
            run_once(self.database, now=self.now, notify=self.notify)
        self.notify.assert_called_once()
        self.assertFalse(self.database.connection.in_transaction)
        self.assertFalse(self.repository.get(task.id).reminder_sent)

    def test_two_real_processes_serialize_delivery_and_keep_database_valid(self):
        task = self.task()
        context = multiprocessing.get_context("spawn")
        barrier = context.Barrier(2)
        results = context.Queue()
        processes = [context.Process(target=_parallel_reminder,
                     args=(str(self.path), self.now, barrier, results)) for _ in range(2)]
        try:
            for process in processes:
                process.start()
            for process in processes:
                process.join(timeout=15)
                self.assertEqual(process.exitcode, 0)
            messages = [results.get(timeout=5) for _ in range(3)]
            self.assertEqual(messages.count(("notification", task.title)), 1)
            self.assertEqual(messages.count(("result", 0)), 2)
            with self.assertRaises(queue.Empty):
                results.get(timeout=0.1)
            self.assertTrue(self.repository.get(task.id).reminder_sent)
            self.assertEqual(self.database.connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        finally:
            for process in processes:
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)
            results.close()
            results.join_thread()

    def test_command_uses_custom_database_without_touching_default(self):
        task = self.task()
        other_path = self.path.parent / "other.sqlite3"
        with Database(other_path) as other:
            other_task = TaskRepository(other).create(Task(
                title="Other database", priority=1, remind_at=self.now - timedelta(days=1),
            ))
        with patch.dict(os.environ, {"TASK_MANAGER_DATABASE": str(self.path)}):
            with patch("task_manager.reminder.send_notification", self.notify):
                self.assertEqual(main(["--database", str(other_path)]), 0)
        self.notify.assert_called_once_with(other_task.title)
        self.assertFalse(self.repository.get(task.id).reminder_sent)
        with Database(other_path) as other:
            self.assertTrue(TaskRepository(other).get(other_task.id).reminder_sent)

    def test_missing_database_is_not_created(self):
        path = self.path.parent / "missing" / "tasks.sqlite3"
        self.assertEqual(main(["--database", str(path)]), 0)
        self.assertFalse(path.exists())

    def test_command_reports_notification_failure_with_nonzero_exit(self):
        task = self.task()
        with patch("task_manager.reminder.send_notification", side_effect=OSError("No notification service")):
            with self.assertLogs("task_manager.reminder", level="ERROR"):
                self.assertEqual(main(["--database", str(self.path)]), 1)
        self.assertFalse(self.repository.get(task.id).reminder_sent)

    def test_gui_and_reminder_share_default_database_configuration(self):
        with patch.dict(os.environ, {"TASK_MANAGER_DATABASE": str(self.path)}):
            self.assertEqual(default_database_path(), self.path)
        with patch.dict(os.environ, {"XDG_DATA_HOME": str(self.path.parent)}, clear=True):
            self.assertEqual(default_database_path(), self.path.parent / "task-manager" / "tasks.sqlite3")


class NotificationTests(unittest.TestCase):
    def test_safe_argument_list_and_escaped_markup(self):
        environment = {"DISPLAY": ":0", "DBUS_SESSION_BUS_ADDRESS": "unix:path=/test/bus"}
        with patch.dict(os.environ, environment, clear=True):
            with patch("task_manager.reminder.subprocess.run") as run:
                send_notification("<b>--urgency=critical; $(touch /tmp/not-run)</b>")
        args = run.call_args.args[0]
        self.assertEqual(args[:4], ["notify-send", "--app-name=Gen X Task Manager", "--", "Task Reminder"])
        self.assertEqual(args[4], "&lt;b&gt;--urgency=critical; $(touch /tmp/not-run)&lt;/b&gt;")
        self.assertTrue(run.call_args.kwargs["check"])
        self.assertEqual(run.call_args.kwargs["timeout"], 5)
        self.assertNotIn("shell", run.call_args.kwargs)

    def test_missing_graphical_session_or_bus_never_calls_notify_send(self):
        for environment in ({}, {"DISPLAY": ":0"}, {"DBUS_SESSION_BUS_ADDRESS": "unix:path=/test/bus"}):
            with self.subTest(environment=environment):
                with patch.dict(os.environ, environment, clear=True):
                    with patch("task_manager.reminder.subprocess.run") as run:
                        with self.assertRaises(OSError):
                            send_notification("Task")
                        run.assert_not_called()

    def test_wayland_session_is_supported(self):
        with patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0", "DBUS_SESSION_BUS_ADDRESS": "unix:path=/test/bus"}, clear=True):
            with patch("task_manager.reminder.subprocess.run") as run:
                send_notification("Task")
                run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
