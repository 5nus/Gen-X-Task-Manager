"""Classic Tkinter calendar and local date/time inputs."""

import calendar
import re
import tkinter as tk
from datetime import date, datetime
from typing import Optional


GRAY = "#C0C0C0"
NAVY = "#000080"
FONT = ("Helvetica", 9)
MONTHS = ("January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December")


def _button(parent, text, command):
    return tk.Button(parent, text=text, command=command, bg=GRAY, fg="black",
                     activebackground=GRAY, activeforeground="black", font=FONT,
                     relief="raised", borderwidth=2, padx=6, pady=2)


def _parse_date(text: str) -> date:
    match = re.fullmatch(r"(\d{1,2})([/\-])(\d{1,2})\2(\d{4})", text.strip())
    try:
        if match:
            month, _, day, year = match.groups()
            return date(int(year), int(month), int(day))
        return date.fromisoformat(text.strip())
    except ValueError:
        raise ValueError("Enter a valid date as MM/DD/YYYY or MM-DD-YYYY.") from None


class DateTimeInput(tk.Frame):
    def __init__(self, parent, value: Optional[datetime] = None) -> None:
        super().__init__(parent, bg=GRAY)
        self.original = value
        self.calendar = None
        self.columnconfigure(0, weight=1)
        self.entry = tk.Entry(self, bg="white", fg="black", insertbackground="black",
                              relief="sunken", borderwidth=2, font=FONT)
        self.entry.grid(row=0, column=0, sticky="ew")
        self.entry.bind("<FocusOut>", self._expand_iso)
        self.calendar_button = _button(self, "Calendar...", self.open_calendar)
        self.calendar_button.grid(row=0, column=1, padx=4)
        _button(self, "Clear", lambda: self.entry.delete(0, "end")).grid(row=0, column=2)
        clock = tk.Frame(self, bg=GRAY)
        clock.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 2))
        local = value.astimezone() if value else None
        self.hour = tk.StringVar(self, f"{local.hour:02d}" if local else "09")
        self.minute = tk.StringVar(self, f"{local.minute:02d}" if local else "00")
        tk.Label(clock, text="Time", bg=GRAY, fg="black", font=FONT).pack(side="left", padx=(0, 5))
        for variable, maximum in ((self.hour, 23), (self.minute, 59)):
            spinbox = tk.Spinbox(clock, from_=0, to=maximum, format="%02.0f", wrap=True,
                                 textvariable=variable, width=3, font=FONT,
                                 bg="white", fg="black", insertbackground="black",
                                 buttonbackground=GRAY, relief="sunken", borderwidth=2)
            spinbox.pack(side="left")
            if variable is self.hour:
                tk.Label(clock, text=":", bg=GRAY, fg="black", font=FONT).pack(side="left")
        tk.Label(clock, text="Local time (24h)", bg=GRAY, fg="black", font=FONT).pack(side="left", padx=6)
        if local:
            self.entry.insert(0, f"{local.month:02d}/{local.day:02d}/{local.year:04d}")
        self._initial = self._fields()

    def _fields(self):
        return self.entry.get().strip(), self.hour.get(), self.minute.get()

    def _expand_iso(self, event=None) -> None:
        text = self.entry.get().strip()
        if ":" not in text:
            return
        try:
            value = datetime.fromisoformat(text)
            if value.utcoffset() is None:
                return
        except ValueError:
            return
        local = value.astimezone()
        self.entry.delete(0, "end")
        self.entry.insert(0, f"{local.month:02d}/{local.day:02d}/{local.year:04d}")
        self.hour.set(f"{local.hour:02d}")
        self.minute.set(f"{local.minute:02d}")
        self.original = value
        self._initial = self._fields()

    def get(self) -> Optional[datetime]:
        text, hour, minute = self._fields()
        if not text:
            return None
        if self.original is not None and self._fields() == self._initial:
            return self.original
        # Continue accepting complete, timezone-aware ISO timestamps pasted by users.
        if "T" in text or ":" in text:
            try:
                value = datetime.fromisoformat(text)
            except ValueError:
                raise ValueError("Enter a valid ISO timestamp with a UTC offset.") from None
            if value.utcoffset() is None:
                raise ValueError("An ISO timestamp requires a UTC offset, for example +01:00.")
            return value
        day = _parse_date(text)
        try:
            if not (re.fullmatch(r"\d{1,2}", hour) and re.fullmatch(r"\d{1,2}", minute)):
                raise ValueError
            value = datetime(day.year, day.month, day.day, int(hour), int(minute))
        except ValueError:
            raise ValueError("Enter a time from 00:00 to 23:59.") from None
        local = value.astimezone()
        if local.replace(tzinfo=None) != value:
            raise ValueError("This local time does not exist due to a clock change. Choose another time.")
        return local

    def open_calendar(self):
        if self.calendar is not None:
            self.calendar.lift()
            return self.calendar
        try:
            text = self.entry.get().strip()
            selected = datetime.fromisoformat(text).date() if ":" in text else _parse_date(text)
        except ValueError:
            selected = date.today()
        self.calendar = CalendarPopup(self, selected)
        return self.calendar


class CalendarPopup(tk.Toplevel):
    def __init__(self, field: DateTimeInput, selected: date) -> None:
        super().__init__(field, bg=GRAY, relief="raised", borderwidth=2)
        self.field = field
        self.selected = selected
        self.year, self.month = selected.year, selected.month
        self.previous_grab = self.grab_current()
        self.title("Select date")
        self.transient(field.winfo_toplevel())
        self.resizable(False, False)
        tk.Label(self, text="Select date", bg=NAVY, fg="white", font=FONT,
                 anchor="w", padx=5, pady=4).pack(fill="x", padx=3, pady=3)
        navigation = tk.Frame(self, bg=GRAY)
        navigation.pack(fill="x", padx=5, pady=3)
        _button(navigation, "<", lambda: self.move(-1)).pack(side="left")
        self.heading = tk.Label(navigation, bg=GRAY, fg="black", font=FONT, width=21)
        self.heading.pack(side="left")
        _button(navigation, ">", lambda: self.move(1)).pack(side="right")
        self.days = tk.Frame(self, bg=GRAY, relief="sunken", borderwidth=2)
        self.days.pack(padx=5, pady=3)
        buttons = tk.Frame(self, bg=GRAY)
        buttons.pack(fill="x", padx=5, pady=5)
        _button(buttons, "Today", lambda: self.choose(date.today())).pack(side="left")
        _button(buttons, "Cancel", self.destroy).pack(side="right")
        self.render()
        self.bind("<Escape>", self._escape)
        self.bind("<Destroy>", self._closed, add="+")
        self.geometry(f"+{field.winfo_rootx()}+{field.winfo_rooty() + field.winfo_height()}")
        self.grab_set()

    def _escape(self, event):
        self.destroy()
        return "break"

    def _closed(self, event):
        if event.widget is self:
            self.field.calendar = None
            if self.previous_grab is not None and self.previous_grab.winfo_exists():
                self.previous_grab.grab_set()

    def move(self, change: int) -> None:
        month_index = self.year * 12 + self.month - 1 + change
        year, month = divmod(month_index, 12)
        if 1 <= year <= 9999:
            self.year, self.month = year, month + 1
            self.render()

    def render(self) -> None:
        self.heading.configure(text=f"{MONTHS[self.month - 1]} {self.year}")
        for child in self.days.winfo_children():
            child.destroy()
        for column, name in enumerate(("Su", "Mo", "Tu", "We", "Th", "Fr", "Sa")):
            tk.Label(self.days, text=name, bg=NAVY, fg="white", font=FONT, width=3).grid(row=0, column=column, sticky="ew")
        self.day_buttons = {}
        for row, week in enumerate(calendar.Calendar(firstweekday=6).monthdayscalendar(self.year, self.month), 1):
            for column, number in enumerate(week):
                if not number:
                    continue
                value = date(self.year, self.month, number)
                button = _button(self.days, str(number), lambda value=value: self.choose(value))
                button.configure(width=2)
                if value == self.selected:
                    button.configure(bg=NAVY, fg="white")
                button.grid(row=row, column=column, sticky="ew")
                self.day_buttons[number] = button

    def choose(self, value: date) -> None:
        self.field.entry.delete(0, "end")
        self.field.entry.insert(0, f"{value.month:02d}/{value.day:02d}/{value.year:04d}")
        self.destroy()
