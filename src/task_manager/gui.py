"""Small Tkinter desktop interface; all task changes go through TaskService."""

import sqlite3
import tkinter as tk
from dataclasses import replace
from datetime import datetime
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Optional

from .models import Task
from .service import TaskService


def _parse_time(text: str) -> Optional[datetime]:
    if not text.strip():
        return None
    try:
        value = datetime.fromisoformat(text.strip())
    except ValueError:
        raise ValueError("Zeitpunkt als Datum und Uhrzeit mit Zeitzone eingeben.") from None
    if value.utcoffset() is None:
        raise ValueError("Die Zeitzone fehlt, z. B. +01:00 oder +00:00.")
    return value


def _error(parent, error: Exception) -> None:
    if isinstance(error, KeyError):
        text = "Diese Aufgabe existiert nicht mehr. Bitte die Liste aktualisieren."
    elif isinstance(error, sqlite3.Error):
        text = f"Datenbankfehler: {error}\nDie Änderung konnte nicht vollständig gespeichert werden."
    else:
        text = str(error)
    messagebox.showerror("Änderung nicht möglich", text, parent=parent)


class TaskDialog(tk.Toplevel):
    def __init__(self, app: "TaskApp", task: Optional[Task] = None) -> None:
        super().__init__(app.root)
        self.app = app
        self.task = task
        self.title("Aufgabe bearbeiten" if task else "Neue Aufgabe")
        self.transient(app.root)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.minsize(480, 500)
        form = ttk.Frame(self, padding=16)
        form.grid(sticky="nsew")
        form.columnconfigure(0, weight=1)
        form.rowconfigure(5, weight=1)

        ttk.Label(form, text="Titel (1–200 Zeichen)").grid(row=0, sticky="w")
        self.title_input = tk.Text(form, height=3, width=56, wrap="word")
        self.title_input.grid(row=1, sticky="ew", pady=(4, 12))
        ttk.Label(form, text="Priorität (3 = höchste)").grid(row=2, sticky="w")
        self.priority = tk.StringVar(self, str(task.priority if task else 2))
        ttk.Combobox(form, textvariable=self.priority, values=(3, 2, 1),
                     state="readonly", width=5).grid(row=3, sticky="w", pady=(4, 12))
        ttk.Label(form, text="Beschreibung (für längere Inhalte)").grid(row=4, sticky="w")
        self.description_input = ScrolledText(form, height=7, width=56, wrap="word")
        self.description_input.grid(row=5, sticky="nsew", pady=(4, 12))
        ttk.Label(form, text="Fällig am (optional)").grid(row=6, sticky="w")
        self.due_input = ttk.Entry(form)
        self.due_input.grid(row=7, sticky="ew", pady=(4, 12))
        ttk.Label(form, text="Erinnern am (optional)").grid(row=8, sticky="w")
        self.reminder_input = ttk.Entry(form)
        self.reminder_input.grid(row=9, sticky="ew", pady=(4, 4))
        ttk.Label(form, text="Format: 2026-11-16T14:30+01:00; leer = kein Zeitpunkt.\n"
                  "Erinnerungen werden gespeichert; Benachrichtigungen folgen später.",
                  wraplength=440).grid(row=10, sticky="w", pady=(0, 12))
        buttons = ttk.Frame(form)
        buttons.grid(row=11, sticky="e")
        ttk.Button(buttons, text="Abbrechen", command=self.destroy).pack(side="left", padx=8)
        self.save_button = ttk.Button(buttons, text="Speichern", command=self.save)
        self.save_button.pack(side="left")
        if task:
            self.title_input.insert("1.0", task.title)
            self.description_input.insert("1.0", task.description or "")
            if task.due_at:
                self.due_input.insert(0, task.due_at.isoformat())
            if task.remind_at:
                self.reminder_input.insert(0, task.remind_at.isoformat())
        self.bind("<Escape>", lambda event: self.destroy())
        self.title_input.focus_set()
        self.grab_set()

    def save(self) -> None:
        try:
            values = dict(
                title=self.title_input.get("1.0", "end-1c"),
                priority=int(self.priority.get()),
                description=self.description_input.get("1.0", "end-1c") or None,
                due_at=_parse_time(self.due_input.get()),
                remind_at=_parse_time(self.reminder_input.get()),
            )
            if self.task is None:
                self.app.service.create(**values)
            else:
                # Validate all model fields before the first write. Compare with
                # the displayed snapshot so untouched fields are never written.
                candidate = replace(self.task, **values)
                if candidate.title.strip() != self.task.title:
                    self.app.service.update_title(self.task.id, candidate.title)
                for field in ("description", "priority", "due_at", "remind_at"):
                    if getattr(candidate, field) != getattr(self.task, field):
                        method = "update_reminder" if field == "remind_at" else "update_" + field
                        getattr(self.app.service, method)(self.task.id, getattr(candidate, field))
        except (TypeError, ValueError, KeyError, sqlite3.Error) as error:
            _error(self, error)
            return
        self.destroy()
        self.app.refresh()


class TaskApp:
    def __init__(self, root: tk.Tk, service: TaskService) -> None:
        self.root = root
        self.service = service
        root.title("Aufgaben")
        root.geometry("760x600")
        root.minsize(480, 320)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)
        toolbar = ttk.Frame(root, padding=12)
        toolbar.grid(row=0, sticky="ew")
        ttk.Label(toolbar, text="Aufgaben · Priorität 3 zuerst").pack(side="left")
        ttk.Button(toolbar, text="Neue Aufgabe", command=self.new_task).pack(side="right")
        ttk.Button(toolbar, text="Aktualisieren", command=self.refresh).pack(side="right", padx=8)
        area = ttk.Frame(root)
        area.grid(row=1, sticky="nsew", padx=12)
        area.columnconfigure(0, weight=1)
        area.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(area, highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(area, orient="vertical", command=self.canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.rows = ttk.Frame(self.canvas)
        self.rows.columnconfigure(0, weight=1)
        self.window = self.canvas.create_window(0, 0, anchor="nw", window=self.rows)
        self.rows.bind("<Configure>", self._resize_content)
        self.canvas.bind("<Configure>", self._resize_canvas)
        self.canvas.bind("<Button-4>", lambda event: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind("<Button-5>", lambda event: self.canvas.yview_scroll(1, "units"))
        self.status = tk.StringVar(root)
        ttk.Label(root, textvariable=self.status, padding=12).grid(row=2, sticky="w")
        self.refresh()

    def _resize_content(self, event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _resize_canvas(self, event) -> None:
        self.canvas.itemconfigure(self.window, width=event.width)

    def new_task(self) -> TaskDialog:
        return TaskDialog(self)

    def edit_task(self, task: Task) -> TaskDialog:
        return TaskDialog(self, task)

    def delete_task(self, task: Task) -> None:
        if not messagebox.askyesno(
            "Aufgabe dauerhaft löschen?",
            f'„{task.title}“\n\nErledigen bedeutet dauerhaft löschen. Fortfahren?',
            parent=self.root, icon="warning", default=messagebox.NO,
        ):
            return
        try:
            self.service.delete(task.id)
        except (KeyError, sqlite3.Error) as error:
            _error(self.root, error)
        self.refresh()

    def refresh(self) -> None:
        try:
            tasks = self.service.list_all()
        except sqlite3.Error as error:
            _error(self.root, error)
            return
        for child in self.rows.winfo_children():
            child.destroy()
        for index, task in enumerate(tasks):
            row = ttk.Frame(self.rows, padding=12, relief="groove")
            row.grid(row=index, column=0, sticky="ew", pady=(0, 8))
            row.columnconfigure(0, weight=1)
            label = ttk.Label(row, text=task.title, anchor="w", justify="left", wraplength=400)
            label.grid(row=0, column=0, sticky="ew")
            row.bind("<Configure>", lambda event, title=label: title.configure(
                wraplength=max(120, event.width - 32)
            ))
            detail = f"Priorität {task.priority}"
            if task.due_at:
                detail += f" · Fällig: {task.due_at.isoformat()}"
            if task.remind_at:
                detail += " · Erinnerung gespeichert"
            ttk.Label(row, text=detail, wraplength=400).grid(row=1, column=0, sticky="w", pady=6)
            buttons = ttk.Frame(row)
            buttons.grid(row=2, column=0, sticky="w")
            ttk.Button(buttons, text="Bearbeiten", command=lambda task=task: self.edit_task(task)).pack(side="left")
            ttk.Button(buttons, text="Erledigen / Löschen…",
                       command=lambda task=task: self.delete_task(task)).pack(side="left", padx=8)
        if not tasks:
            ttk.Label(self.rows, text="Keine Aufgaben. Lege eine neue Aufgabe an.",
                      padding=16).grid(sticky="w")
        self.status.set(f"{len(tasks)} Aufgaben")
