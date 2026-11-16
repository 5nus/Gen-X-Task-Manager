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
from task_manager.gui import TaskApp
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
        dialog.priority.set("3")
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
        with patch("task_manager.gui.messagebox.askyesno", return_value=True) as confirm:
            self.app.delete_task(self.service.get(task.id))
        confirm.assert_called_once()
        self.assertEqual(confirm.call_args.kwargs["default"], "no")
        with Database(self.path) as reader:
            repository = TaskRepository(reader)
            self.assertIsNone(repository.get(task.id))
            self.assertFalse(repository.mark_reminder_sent(task.id, expected_remind_at=task.remind_at))
        self.assertEqual(self.app.status.get(), "0 Aufgaben")

    def test_cancelled_delete_keeps_task(self):
        task = self.service.create("Behalten", 1)
        with patch("task_manager.gui.messagebox.askyesno", return_value=False):
            self.app.delete_task(task)
        self.assertEqual(self.service.get(task.id), task)

    def test_invalid_title_displays_error_and_keeps_form(self):
        dialog = self.app.new_task()
        dialog.title_input.insert("1.0", "a" * 201)
        with patch("task_manager.gui.messagebox.showerror") as error:
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
        with patch("task_manager.gui.messagebox.showerror") as error:
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
        with patch("task_manager.gui.messagebox.showerror") as error:
            dialog.save_button.invoke()
        error.assert_called_once()
        self.assertEqual(self.service.list_all(), [])

    def test_database_error_is_reported_without_closing_form(self):
        dialog = self.app.new_task()
        dialog.title_input.insert("1.0", "Aufgabe")
        with patch.object(self.service, "create", side_effect=sqlite3.OperationalError("locked")):
            with patch("task_manager.gui.messagebox.showerror") as error:
                dialog.save_button.invoke()
        error.assert_called_once()
        self.assertTrue(dialog.winfo_exists())

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
