import os
import time
import tkinter as tk
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

from task_manager.date_picker import DateTimeInput, _parse_date


class DateParsingTests(unittest.TestCase):
    def test_american_dates_with_slashes_and_dashes(self):
        for text in ("11/06/2026", "11-06-2026", " 11/6/2026 "):
            with self.subTest(text=text):
                self.assertEqual(_parse_date(text), date(2026, 11, 6))

    def test_leap_day_and_iso_date(self):
        self.assertEqual(_parse_date("02/29/2028"), date(2028, 2, 29))
        self.assertEqual(_parse_date("2026-11-16"), date(2026, 11, 16))

    def test_invalid_dates_are_rejected(self):
        for text in ("02/29/2027", "04-31-2026", "13/01/2026", "11/00/2026",
                     "11/06/26", "11/06-2026", "", "not a date"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                _parse_date(text)


@unittest.skipUnless(os.environ.get("DISPLAY"), "GUI tests require a display or xvfb-run")
class DatePickerTests(unittest.TestCase):
    def setUp(self):
        zone = patch.dict(os.environ, {"TZ": "Europe/Berlin"})
        zone.start()
        time.tzset()

        def restore_timezone():
            zone.stop()
            time.tzset()

        self.addCleanup(restore_timezone)
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)
        self.field = DateTimeInput(self.root)
        self.field.pack()
        self.root.update()

    def test_empty_date_is_none_and_time_can_be_selected(self):
        self.assertIsNone(self.field.get())
        self.field.entry.insert(0, "11/16/2026")
        clock = self.field.grid_slaves(row=1, column=0)[0]
        hour, minute = [child for child in clock.winfo_children() if isinstance(child, tk.Spinbox)]
        hour.invoke("buttonup")
        minute.invoke("buttonup")
        self.assertEqual(self.field.get().astimezone(timezone.utc), datetime(2026, 11, 16, 9, 1, tzinfo=timezone.utc))

    def test_summer_and_winter_offsets_follow_local_timezone(self):
        self.field.hour.set("14")
        self.field.minute.set("30")
        for text, utc_hour in (("01-16-2026", 13), ("07/16/2026", 12)):
            with self.subTest(text=text):
                self.field.entry.delete(0, "end")
                self.field.entry.insert(0, text)
                self.assertEqual(self.field.get().astimezone(timezone.utc).hour, utc_hour)

    def test_invalid_time_and_nonexistent_dst_time_are_rejected(self):
        self.field.entry.insert(0, "03/29/2026")
        for hour, minute in (("24", "00"), ("12", "60"), ("x", "00"), ("02", "30")):
            with self.subTest(hour=hour, minute=minute), self.assertRaises(ValueError):
                self.field.hour.set(hour)
                self.field.minute.set(minute)
                self.field.get()

    def test_full_iso_timestamp_is_still_accepted(self):
        self.field.entry.insert(0, "2026-11-16T14:30:12.123456+01:00")
        expected = datetime(2026, 11, 16, 13, 30, 12, 123456, timezone.utc)
        self.assertEqual(self.field.get(), expected)

    def test_pasted_iso_expands_into_editable_local_date_and_time(self):
        self.field.entry.insert(0, "2026-11-16T14:30:12.123456+01:00")
        self.field._expand_iso()
        self.assertEqual(self.field.entry.get(), "11/16/2026")
        self.assertEqual(self.field.hour.get(), "14")
        self.assertEqual(self.field.get().microsecond, 123456)
        self.field.minute.set("45")
        self.assertEqual(self.field.get().astimezone(timezone.utc),
                         datetime(2026, 11, 16, 13, 45, tzinfo=timezone.utc))

    def test_unchanged_fields_preserve_original_precision(self):
        value = datetime(2026, 11, 16, 13, 30, 12, 123456, timezone.utc)
        field = DateTimeInput(self.root, value)
        self.assertEqual(field.entry.get(), "11/16/2026")
        self.assertEqual(field.hour.get(), "14")
        self.assertEqual(field.get(), value)
        field.entry.delete(0, "end")
        self.assertIsNone(field.get())

    def test_calendar_leap_day_navigation_selection_and_singleton(self):
        self.field.entry.insert(0, "12/31/2027")
        self.field.calendar_button.invoke()
        popup = self.field.calendar
        self.assertIs(self.field.open_calendar(), popup)
        popup.move(1)
        self.assertEqual((popup.year, popup.month), (2028, 1))
        popup.move(1)
        popup.day_buttons[29].invoke()
        self.assertEqual(self.field.entry.get(), "02/29/2028")
        self.assertIsNone(self.field.calendar)
        self.assertEqual(self.field.hour.get(), "09")

    def test_cancel_restores_previous_grab_and_keeps_fields(self):
        self.root.grab_set()
        self.field.entry.insert(0, "11/16/2026")
        popup = self.field.open_calendar()
        popup.update()
        popup.focus_force()
        popup.event_generate("<Escape>")
        self.root.update()
        self.assertEqual(self.field.entry.get(), "11/16/2026")
        self.assertIsNone(self.field.calendar)
        self.assertIs(self.root.grab_current(), self.root)

    def test_today_button_uses_current_date(self):
        popup = self.field.open_calendar()
        buttons = next(child for child in popup.winfo_children()
                       if isinstance(child, tk.Frame) and
                       any(isinstance(button, tk.Button) and button.cget("text") == "Today"
                           for button in child.winfo_children()))
        today = next(button for button in buttons.winfo_children() if button.cget("text") == "Today")
        today.invoke()
        self.assertEqual(_parse_date(self.field.entry.get()), date.today())


if __name__ == "__main__":
    unittest.main()
