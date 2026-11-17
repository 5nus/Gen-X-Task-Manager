"""Classic desktop interface; task rules remain in TaskService."""

import sqlite3
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from typing import Optional

from .harold import HaroldMessenger
from . import __version__
from .date_picker import DateTimeInput
from .models import Task
from .service import TaskService


GRAY = "#C0C0C0"
NAVY = "#000080"
WHITE = "#FFFFFF"
BLACK = "#000000"
FONT = ("Helvetica", 9)
PRIORITIES = {1: "Low", 2: "Normal", 3: "High"}
FORM_TITLE = "New task"


def _button(parent, text, command):
    return tk.Button(
        parent, text=text, command=command, bg=GRAY, fg=BLACK,
        activebackground=GRAY, activeforeground=BLACK, font=FONT,
        relief="raised", borderwidth=2, padx=8, pady=3, highlightthickness=1,
        highlightbackground=BLACK, highlightcolor=BLACK,
    )


def _notice(parent, title: str, text: str, *, confirm: bool = False) -> bool:
    """Use our own modal so button language and styling do not depend on the OS."""
    previous_grab = parent.grab_current()
    dialog = tk.Toplevel(parent, bg=GRAY, borderwidth=2, relief="raised")
    dialog.title(title)
    dialog.transient(parent)
    dialog.resizable(False, False)
    tk.Label(dialog, text=title, bg=NAVY, fg=WHITE, font=FONT,
             anchor="w", padx=6, pady=4).pack(fill="x", padx=3, pady=3)
    tk.Label(dialog, text=text, bg=GRAY, fg=BLACK, font=FONT, justify="left",
             wraplength=440, padx=16, pady=16).pack(fill="x")
    buttons = tk.Frame(dialog, bg=GRAY)
    buttons.pack(fill="x", padx=12, pady=(0, 12))
    result = False

    def close(authorized=False):
        nonlocal result
        result = authorized
        dialog.destroy()

    if confirm:
        _button(buttons, "Delete", lambda: close(True)).pack(side="left", padx=4)
        cancel = _button(buttons, "Cancel", close)
    else:
        cancel = _button(buttons, "OK", close)
    cancel.pack(side="right", padx=4)
    dialog.bind("<Escape>", lambda event: close())
    dialog.protocol("WM_DELETE_WINDOW", close)
    dialog.grab_set()
    cancel.focus_set()
    parent.wait_window(dialog)
    if previous_grab is not None and previous_grab.winfo_exists():
        previous_grab.grab_set()
    return result


def _error(parent, error: Exception) -> None:
    if isinstance(error, KeyError):
        text = "This task no longer exists. Refresh the list."
    elif isinstance(error, sqlite3.Error):
        text = "Could not save changes. No changes were saved. Please try again."
    else:
        text = str(error)
    _notice(parent, "Error", text)


class TaskDialog(tk.Toplevel):
    def __init__(self, app: "TaskApp", task: Optional[Task] = None) -> None:
        super().__init__(app.root, bg=GRAY, borderwidth=2, relief="raised")
        self.app = app
        self.task = task
        self.title("Edit task" if task else FORM_TITLE)
        self.transient(app.root)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.minsize(520, 530)
        tk.Label(self, text="Edit task" if task else FORM_TITLE,
                 bg=NAVY, fg=WHITE, anchor="w", padx=6, pady=5).grid(
                     row=0, sticky="ew", padx=3, pady=3)
        form = tk.LabelFrame(self, text="Task details",
                             bg=GRAY, fg=BLACK, relief="groove", borderwidth=2, padx=8, pady=6)
        form.grid(row=1, sticky="nsew", padx=6, pady=4)
        form.columnconfigure(0, weight=1)
        form.rowconfigure(5, weight=1)

        tk.Label(form, text="Title (1–200 characters)").grid(row=0, sticky="w")
        self.title_input = tk.Text(form, height=3, width=58, wrap="word", bg=WHITE,
                                   fg=BLACK, insertbackground=BLACK, relief="sunken", borderwidth=2)
        self.title_input.grid(row=1, sticky="ew", pady=(2, 6))
        tk.Label(form, text="Priority").grid(row=2, sticky="w")
        self.priority = tk.StringVar(self, PRIORITIES[task.priority if task else 2])
        self.priority_menu = tk.OptionMenu(form, self.priority, "High", "Normal", "Low")
        self.priority_menu.configure(bg=GRAY, fg=BLACK, relief="raised", borderwidth=2,
                                     highlightthickness=0, activebackground=GRAY, font=FONT)
        self.priority_menu["menu"].configure(bg=GRAY, fg=BLACK, activebackground=NAVY,
                                             activeforeground=WHITE, font=FONT)
        self.priority_menu.grid(row=3, sticky="w", pady=(2, 6))
        tk.Label(form, text="Description").grid(row=4, sticky="w")
        statement = tk.Frame(form, bg=GRAY)
        statement.grid(row=5, sticky="nsew", pady=(2, 6))
        statement.columnconfigure(0, weight=1)
        statement.rowconfigure(0, weight=1)
        self.description_input = tk.Text(statement, height=6, width=58, wrap="word", bg=WHITE,
                                         fg=BLACK, insertbackground=BLACK, relief="sunken", borderwidth=2)
        self.description_input.grid(sticky="nsew")
        scrollbar = tk.Scrollbar(statement, command=self.description_input.yview,
                                 bg=GRAY, troughcolor=GRAY, relief="raised", borderwidth=2)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.description_input.configure(yscrollcommand=scrollbar.set)
        tk.Label(form, text="Due (optional)").grid(row=6, sticky="w")
        self.due_picker = DateTimeInput(form, task.due_at if task else None)
        self.due_picker.grid(row=7, sticky="ew", pady=(2, 6))
        self.due_input = self.due_picker.entry
        tk.Label(form, text="Reminder (optional)").grid(row=8, sticky="w")
        self.reminder_picker = DateTimeInput(form, task.remind_at if task else None)
        self.reminder_picker.grid(row=9, sticky="ew", pady=(2, 4))
        self.reminder_input = self.reminder_picker.entry
        tk.Label(form, text="Date: MM/DD/YYYY or MM-DD-YYYY. Time: local, 24-hour.\n"
                 "Desktop reminders require the reminder service.",
                 justify="left", anchor="w").grid(row=10, sticky="w")
        buttons = tk.Frame(self, bg=GRAY, borderwidth=1, relief="sunken")
        buttons.grid(row=2, sticky="ew", padx=6, pady=6)
        _button(buttons, "Cancel", self.destroy).pack(side="left", padx=5, pady=5)
        self.save_button = _button(buttons, "Save", self.save)
        self.save_button.pack(side="right", padx=5, pady=5)
        if task:
            self.title_input.insert("1.0", task.title)
            self.description_input.insert("1.0", task.description or "")
        self.bind("<Escape>", lambda event: self.destroy())
        self.title_input.focus_set()
        self.grab_set()

    def save(self) -> None:
        try:
            classification = self.priority.get()
            priority = next((number for number, name in PRIORITIES.items() if name == classification), None)
            if priority is None:
                raise ValueError("Select Low, Normal or High priority.")
            values = dict(
                title=self.title_input.get("1.0", "end-1c"),
                priority=priority,
                description=self.description_input.get("1.0", "end-1c") or None,
                due_at=self.due_picker.get(),
                remind_at=self.reminder_picker.get(),
            )
            if self.task is None:
                self.app.service.create(**values)
            else:
                # Compare against the displayed snapshot; untouched fields stay untouched.
                candidate = replace(self.task, **values)
                changes = {}
                if candidate.title.strip() != self.task.title:
                    changes["title"] = candidate.title
                for field in ("description", "priority", "due_at", "remind_at"):
                    if getattr(candidate, field) != getattr(self.task, field):
                        changes[field] = getattr(candidate, field)
                self.app.service.update(self.task.id, **changes)
        except (TypeError, ValueError, KeyError, sqlite3.Error) as error:
            _error(self, error)
            return
        self.destroy()
        self.app.refresh()


class TaskApp:
    def __init__(self, root: tk.Tk, service: TaskService) -> None:
        self.root = root
        self.service = service
        root.option_add("*Font", FONT)
        root.option_add("*Background", GRAY)
        root.option_add("*Foreground", BLACK)
        root.option_add("*activeBackground", NAVY)
        root.option_add("*activeForeground", WHITE)
        root.option_add("*selectBackground", NAVY)
        root.option_add("*selectForeground", WHITE)
        root.configure(bg=GRAY, borderwidth=2, relief="raised")
        root.title("genxtask")
        icon_directory = Path(__file__).parent / "assets" / "icons"
        self._icons = [tk.PhotoImage(master=root, file=str(icon_directory / f"genxtask-{size}.png"))
                       for size in (256, 64, 32, 16)]
        root.iconphoto(True, *self._icons)
        root.iconname("genxtask")
        root.geometry("820x620")
        root.minsize(480, 400)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)
        self.messenger = HaroldMessenger(root)
        self._menus()
        header = tk.Frame(root, bg=NAVY, borderwidth=1, relief="solid")
        header.grid(row=0, sticky="ew", padx=4, pady=4)
        tk.Label(header, text="genxtask", bg=NAVY,
                 fg=WHITE, anchor="w", font=("Helvetica", 11, "bold"), wraplength=440,
                 justify="left", padx=6, pady=4).pack(fill="x")
        toolbar = tk.Frame(root, bg=GRAY, borderwidth=2, relief="raised")
        toolbar.grid(row=1, sticky="ew", padx=4, pady=(0, 4))
        _button(toolbar, "Add task", self.new_task).pack(side="left", padx=4, pady=4)
        _button(toolbar, "Refresh", self.refresh).pack(side="left", padx=4, pady=4)
        _button(toolbar, "Harold Messenger", self.messenger.open).pack(side="left", padx=4, pady=4)
        area = tk.LabelFrame(root, text="Tasks",
                             bg=GRAY, fg=BLACK, borderwidth=2, relief="groove", padx=4, pady=4)
        area.grid(row=2, sticky="nsew", padx=4, pady=4)
        area.columnconfigure(0, weight=1)
        area.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(area, bg=WHITE, borderwidth=2, relief="sunken", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = tk.Scrollbar(area, orient="vertical", command=self.canvas.yview,
                                 bg=GRAY, troughcolor=GRAY, relief="raised", borderwidth=2)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.rows = tk.Frame(self.canvas, bg=GRAY)
        self.rows.columnconfigure(0, weight=1)
        self.window = self.canvas.create_window(0, 0, anchor="nw", window=self.rows)
        self.rows.bind("<Configure>", self._resize_content)
        self.canvas.bind("<Configure>", self._resize_canvas)
        self.canvas.bind("<Button-4>", lambda event: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind("<Button-5>", lambda event: self.canvas.yview_scroll(1, "units"))
        self.refresh()

    def _menus(self) -> None:
        self.menu = tk.Menu(self.root, bg=GRAY, fg=BLACK, activebackground=NAVY,
                            activeforeground=WHITE, relief="raised", borderwidth=2, tearoff=False)
        for name in ("File", "Tasks", "Help"):
            menu = tk.Menu(self.menu, tearoff=False, bg=GRAY, fg=BLACK,
                           activebackground=NAVY, activeforeground=WHITE, font=FONT)
            self.menu.add_cascade(label=name, menu=menu)
            if name == "File":
                menu.add_command(label="Add task", command=self.new_task)
                menu.add_separator()
                menu.add_command(label="Exit", command=self.root.destroy)
            elif name == "Tasks":
                menu.add_command(label="Refresh", command=self.refresh)
            else:
                menu.add_command(label="About", command=self.show_help)
        self.root.configure(menu=self.menu)

    def show_help(self) -> None:
        _notice(self.root, "About", f"genxtask v{__version__}\n\n"
                "Priority: High (3), Normal (2), Low (1).\n"
                "Desktop reminders require the reminder service.")

    def _resize_content(self, event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _resize_canvas(self, event) -> None:
        self.canvas.itemconfigure(self.window, width=max(1, event.width - 4))

    def new_task(self) -> TaskDialog:
        return TaskDialog(self)

    def edit_task(self, task: Task) -> TaskDialog:
        return TaskDialog(self, task)

    def delete_task(self, task: Task) -> None:
        if not _notice(self.root, "Delete task", "Permanently delete this task? This cannot be undone.", confirm=True):
            return
        try:
            self.service.delete(task.id)
        except (KeyError, sqlite3.Error) as error:
            _error(self.root, error)
            self.refresh()
            return
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
            row = tk.LabelFrame(self.rows, text="Task", bg=GRAY,
                                fg=BLACK, relief="groove", borderwidth=2, padx=6, pady=4)
            row.grid(row=index, column=0, sticky="ew", padx=3, pady=3)
            row.columnconfigure(0, weight=1)
            label = tk.Label(row, text=task.title, bg=NAVY, fg=WHITE, anchor="w",
                             justify="left", wraplength=400, padx=4, pady=3)
            label.grid(row=0, column=0, sticky="ew")
            detail = f"Priority: {PRIORITIES[task.priority]}"
            if task.due_at:
                detail += f"\nDue: {task.due_at.isoformat()}"
            if task.remind_at:
                detail += f"\nReminder: {task.remind_at.isoformat()}"
            detail_label = tk.Label(row, text=detail, justify="left", anchor="w", wraplength=400)
            detail_label.grid(row=1, column=0, sticky="ew", pady=4)
            row.bind("<Configure>", lambda event, title=label, details=detail_label: (
                title.configure(wraplength=max(100, event.width - 28)),
                details.configure(wraplength=max(100, event.width - 28)),
            ))
            buttons = tk.Frame(row, bg=GRAY, borderwidth=1, relief="sunken")
            buttons.grid(row=2, column=0, sticky="ew")
            _button(buttons, "Edit task", lambda task=task: self.edit_task(task)).pack(side="left", padx=3, pady=3)
            _button(buttons, "Delete", lambda task=task: self.delete_task(task)).pack(side="left", padx=3, pady=3)
        if not tasks:
            tk.Label(self.rows, text="No tasks.\n"
                     "Use Add task to get started.",
                     justify="left", padx=12, pady=12, wraplength=400).grid(sticky="w")
