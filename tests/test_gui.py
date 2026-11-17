import os
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import tkinter as tk

from task_manager.database import Database
from task_manager.gui import TaskApp, _notice, _error
from task_manager.repository import TaskRepository
from task_manager.service import TaskService


@unittest.skipUnless(os.environ.get("DISPLAY"), "GUI tests require a display or xvfb-run")
class GuiTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "tasks.sqlite3"
        self.database = Database(self.path)
        self.addCleanup(self.database.close)
        self.service = TaskService(TaskRepository(self.database))
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)
        self.app = TaskApp(self.root, self.service)
        self.root.update()

    def test_create_edit_and_confirmed_delete_persist(self):
        dialog = self.app.new_task()
        dialog.title_input.insert("1.0", "  Einkaufen  ")
        dialog.description_input.insert("1.0", "Längere Beschreibung")
        dialog.priority.set("High")
        dialog.reminder_input.insert(0, "2026-11-16T14:30+01:00")
        dialog.save_button.invoke()
        task, = self.service.list_all()
        self.assertEqual(task.title, "Einkaufen")
        self.assertEqual(task.description, "Längere Beschreibung")
        self.assertEqual(task.priority, 3)
        self.assertEqual(task.remind_at, datetime(2026, 11, 16, 13, 30, tzinfo=timezone.utc))

        dialog = self.app.edit_task(task)
        dialog.title_input.delete("1.0", "end")
        dialog.title_input.insert("1.0", "Neuer Titel")
        dialog.save_button.invoke()
        with Database(self.path) as reader:
            self.assertEqual(TaskRepository(reader).get(task.id), replace(task, title="Neuer Titel"))
        with patch("task_manager.gui._notice", return_value=True) as confirm:
            self.app.delete_task(self.service.get(task.id))
        confirm.assert_called_once()
        self.assertTrue(confirm.call_args.kwargs["confirm"])
        self.assertEqual(confirm.call_args.args[1], "Delete task")
        with Database(self.path) as reader:
            repository = TaskRepository(reader)
            self.assertIsNone(repository.get(task.id))
            self.assertFalse(repository.mark_reminder_sent(task.id, expected_remind_at=task.remind_at))
        self.assertEqual(self.service.list_all(), [])

    def test_cancelled_delete_keeps_task(self):
        task = self.service.create("Behalten", 1)
        with patch("task_manager.gui._notice", return_value=False):
            self.app.delete_task(task)
        self.assertEqual(self.service.get(task.id), task)

    def test_calendar_and_american_dates_save_through_service(self):
        dialog = self.app.new_task()
        dialog.title_input.insert("1.0", "Calendar test")
        dialog.due_input.insert(0, "02/01/2028")
        dialog.due_picker.calendar_button.invoke()
        dialog.due_picker.calendar.day_buttons[29].invoke()
        dialog.due_picker.hour.set("14")
        dialog.due_picker.minute.set("30")
        dialog.reminder_input.insert(0, "02-28-2028")
        dialog.reminder_picker.hour.set("09")
        dialog.save_button.invoke()
        task, = self.service.list_all()
        self.assertEqual(task.due_at, datetime(2028, 2, 29, 14, 30).astimezone())
        self.assertEqual(task.remind_at, datetime(2028, 2, 28, 9).astimezone())

    def test_open_and_save_preserves_reminder_precision_and_status(self):
        moment = datetime(2026, 11, 16, 12, 30, 45, 123456, timezone.utc)
        task = self.service.create("Unchanged", 1, due_at=moment, remind_at=moment)
        repository = TaskRepository(self.database)
        repository.mark_reminder_sent(task.id, expected_remind_at=moment)
        dialog = self.app.edit_task(self.service.get(task.id))
        dialog.save_button.invoke()
        self.assertEqual(self.service.get(task.id), replace(task, reminder_sent=True))

    def test_simple_menus_and_form_priorities(self):
        labels = [self.app.menu.entrycget(index, "label")
                  for index in range(self.app.menu.index("end") + 1)]
        self.assertEqual(labels, ["File", "Tasks", "Help"])
        self.assertEqual(self.root.cget("background"), "#C0C0C0")
        dialog = self.app.new_task()
        self.assertEqual(dialog.title(), "New task")
        menu = dialog.priority_menu["menu"]
        self.assertEqual([menu.entrycget(index, "label") for index in range(3)],
                         ["High", "Normal", "Low"])

    def test_messenger_button_opens_single_nonmodal_window(self):
        toolbar = self.root.grid_slaves(row=1, column=0)[0]
        button = next(child for child in toolbar.winfo_children()
                      if child.cget("text") == "Harold Messenger")
        button.invoke()
        window = self.app.messenger.window
        button.invoke()
        self.assertIs(self.app.messenger.window, window)
        self.assertIsNone(self.root.grab_current())

    def test_each_priority_label_preserves_numeric_priority(self):
        for name, number in (("Low", 1), ("Normal", 2), ("High", 3)):
            with self.subTest(name=name):
                dialog = self.app.new_task()
                dialog.title_input.insert("1.0", name)
                dialog.priority.set(name)
                dialog.save_button.invoke()
                self.assertEqual(next(task.priority for task in self.service.list_all()
                                      if task.title == name), number)

    def test_real_authorization_dialog_and_modal_grab_restoration(self):
        form = self.app.new_task()

        def respond():
            dialog = next(child for child in form.winfo_children() if isinstance(child, tk.Toplevel))
            buttons = next(child for child in dialog.winfo_children() if isinstance(child, tk.Frame))
            choices = {button.cget("text"): button for button in buttons.winfo_children()}
            self.assertEqual(set(choices), {"Delete", "Cancel"})
            choices[response].invoke()

        for response, expected in (("Cancel", False), ("Delete", True)):
            with self.subTest(response=response):
                self.root.after(20, respond)
                self.assertEqual(_notice(form, "Delete task", "Notice", confirm=True), expected)
                self.assertEqual(self.root.grab_current(), form)

    def test_dismissed_authorization_does_not_delete(self):
        task = self.service.create("Keep this case", 1)

        def dismiss():
            dialog = next(child for child in self.root.winfo_children() if isinstance(child, tk.Toplevel))
            dialog.tk.call(dialog.protocol("WM_DELETE_WINDOW"))

        self.root.after(20, dismiss)
        self.app.delete_task(task)
        self.assertEqual(self.service.get(task.id), task)

    def test_failed_termination_does_not_report_success(self):
        task = self.service.create("Missing case", 1)
        self.service.delete(task.id)
        with patch("task_manager.gui._notice", return_value=True) as notice:
            self.app.delete_task(task)
        self.assertEqual(notice.call_count, 2)
        self.assertEqual(notice.call_args.args[1], "Error")

    def test_error_and_help_notices_are_english(self):
        with patch("task_manager.gui._notice") as notice:
            _error(self.root, KeyError("missing"))
            self.assertIn("no longer exists", notice.call_args.args[2])
            _error(self.root, sqlite3.OperationalError("non-English driver detail"))
            self.assertIn("Could not save changes", notice.call_args.args[2])
            self.assertNotIn("non-English driver detail", notice.call_args.args[2])
            self.app.show_help()
            self.assertIn("genxtask", notice.call_args.args[2])

    def test_invalid_title_displays_error_and_keeps_form(self):
        dialog = self.app.new_task()
        dialog.title_input.insert("1.0", "a" * 201)
        with patch("task_manager.gui._notice") as error:
            dialog.save_button.invoke()
        error.assert_called_once()
        self.assertTrue(dialog.winfo_exists())
        self.assertEqual(self.service.list_all(), [])

    def test_invalid_timestamp_does_not_partially_save_title(self):
        task = self.service.create("Original", 1)
        dialog = self.app.edit_task(task)
        dialog.title_input.delete("1.0", "end")
        dialog.title_input.insert("1.0", "Geändert")
        dialog.due_input.insert(0, "2026-11-16T14:30")
        with patch("task_manager.gui._notice") as error:
            dialog.save_button.invoke()
        error.assert_called_once()
        self.assertEqual(self.service.get(task.id), task)

    def test_title_only_edit_preserves_concurrent_reminder_changes(self):
        moment = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
        task = self.service.create("Original", 1, remind_at=moment)
        dialog = self.app.edit_task(task)
        new_time = moment + timedelta(hours=1)
        with Database(self.path) as other_database:
            other = TaskRepository(other_database)
            other.update_reminder(task.id, new_time, reminder_sent=False)
            other.mark_reminder_sent(task.id, expected_remind_at=new_time)
            dialog.title_input.delete("1.0", "end")
            dialog.title_input.insert("1.0", "Geändert")
            dialog.save_button.invoke()
            self.assertEqual(other.get(task.id), replace(
                task, title="Geändert", remind_at=new_time, reminder_sent=True
            ))

    def test_missing_task_during_edit_is_reported(self):
        task = self.service.create("Original", 1)
        dialog = self.app.edit_task(task)
        self.service.delete(task.id)
        dialog.title_input.insert("end", " geändert")
        with patch("task_manager.gui._notice") as error:
            dialog.save_button.invoke()
        error.assert_called_once()
        self.assertEqual(self.service.list_all(), [])

    def test_database_error_is_reported_without_closing_form(self):
        dialog = self.app.new_task()
        dialog.title_input.insert("1.0", "Aufgabe")
        with patch.object(self.service, "create", side_effect=sqlite3.OperationalError("locked")):
            with patch("task_manager.gui._notice") as error:
                dialog.save_button.invoke()
        error.assert_called_once()
        self.assertTrue(dialog.winfo_exists())

    def test_multiple_form_edits_roll_back_together_on_database_error(self):
        task = self.service.create("Original", 1, description="Before")
        dialog = self.app.edit_task(task)
        dialog.title_input.delete("1.0", "end")
        dialog.title_input.insert("1.0", "Edited")
        dialog.description_input.delete("1.0", "end")
        dialog.description_input.insert("1.0", "After")
        dialog.priority.set("High")
        self.database.connection.executescript("""
            CREATE TRIGGER reject_edit AFTER UPDATE ON tasks
            BEGIN SELECT RAISE(ABORT, 'test edit failure'); END;
        """)
        with patch("task_manager.gui._notice") as error:
            dialog.save_button.invoke()
        error.assert_called_once()
        self.assertIn("No changes were saved", error.call_args.args[2])
        self.assertTrue(dialog.winfo_exists())
        self.assertEqual(self.service.get(task.id), task)

    def test_form_submits_only_changed_fields_in_one_service_call(self):
        task = self.service.create("Original", 1, description="Before")
        dialog = self.app.edit_task(task)
        dialog.title_input.delete("1.0", "end")
        dialog.title_input.insert("1.0", "Edited")
        dialog.priority.set("High")
        with patch.object(self.service, "update", wraps=self.service.update) as update:
            dialog.save_button.invoke()
        update.assert_called_once_with(task.id, title="Edited", priority=3)
        self.assertEqual(self.service.get(task.id), replace(task, title="Edited", priority=3))

    def test_long_title_wraps_inside_narrow_window(self):
        task = self.service.create("W" * 200, 3)
        self.app.refresh()
        self.root.geometry("480x400")
        self.root.update()
        row = self.app.rows.winfo_children()[0]
        title = row.grid_slaves(row=0, column=0)[0]
        self.assertEqual(title.cget("text"), task.title)
        self.assertGreater(title.winfo_height(), 30)
        self.assertLessEqual(title.winfo_width(), self.app.canvas.winfo_width())
        self.assertLessEqual(row.winfo_width(), self.app.canvas.winfo_width())

    def test_application_entry_point_runs_with_persistent_database(self):
        from task_manager.__main__ import main

        def start(root, service):
            TaskApp(root, service)
            service.create("Starttest", 1)
            root.after(10, root.quit)

        with patch("sys.argv", ["task_manager", "--database", str(self.path)]):
            with patch("task_manager.__main__.TaskApp", side_effect=start):
                self.assertEqual(main(), 0)
        self.assertEqual(self.service.list_all()[0].title, "Starttest")


if __name__ == "__main__":
    unittest.main()
