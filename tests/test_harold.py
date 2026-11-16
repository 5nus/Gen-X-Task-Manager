import os
import tkinter as tk
import unittest
from unittest.mock import patch

from task_manager.harold import AWAY_NOTICE, HaroldMessenger, MAX_MESSAGES, MESSAGES


@unittest.skipUnless(os.environ.get("DISPLAY"), "GUI tests require a display or xvfb-run")
class HaroldTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)
        self.messenger = HaroldMessenger(self.root)
        self.addCleanup(self.messenger.shutdown)

    def fire_timer(self):
        # Execute the actual registered after callback without waiting minutes.
        timer = self.messenger._timer
        script, _ = self.root.tk.call("after", "info", timer)
        self.root.tk.call("after", "cancel", timer)
        self.root.tk.call(script)

    def notices(self):
        return [child for child in self.root.winfo_children()
                if isinstance(child, tk.Toplevel) and child.title() == "Messenger Service"]

    def test_schedule_uses_three_to_ten_minutes_and_stops_after_three_messages(self):
        with patch.object(self.messenger._random, "randint", return_value=180_000) as interval:
            for _ in range(MAX_MESSAGES):
                self.fire_timer()
        self.assertEqual(len(self.messenger.history), 3)
        self.assertTrue(all(sender == "Harold" and text in MESSAGES
                            for sender, text, timestamp in self.messenger.history))
        interval.assert_called_with(180_000, 600_000)
        self.assertEqual(interval.call_count, MAX_MESSAGES - 1)
        self.assertIsNone(self.messenger._timer)
        self.assertIsNone(self.messenger.window)
        self.assertEqual(self.notices(), [])

    def test_single_window_and_nonmodal_behavior(self):
        first = self.messenger.open()
        self.assertIs(self.messenger.open(), first)
        self.assertIsNone(self.root.grab_current())
        self.assertEqual((self.messenger.avatar.width(), self.messenger.avatar.height()), (63, 63))

    def test_history_and_timer_survive_closing_and_reopening(self):
        window = self.messenger.open()
        self.fire_timer()
        self.messenger.entry.insert(0, "hello")
        self.messenger.send_button.invoke()
        expected = list(self.messenger.history)
        timer = self.messenger._timer
        window.destroy()
        self.assertIsNone(self.messenger.window)
        self.assertEqual(self.messenger._timer, timer)
        self.fire_timer()
        self.messenger.open()
        self.assertEqual(self.messenger.history[:2], expected)
        self.assertEqual(len(self.messenger.history), 3)
        transcript = self.messenger.transcript.get("1.0", "end")
        self.assertIn("You — ", transcript)
        self.assertIn("hello", transcript)
        self.assertRegex(transcript, r"Harold — \d{2}:\d{2}\n")
        self.assertRegex(transcript, r"You — \d{2}:\d{2}\nhello")
        self.assertNotIn(AWAY_NOTICE, transcript)
        self.assertEqual(self.messenger.transcript.cget("state"), "disabled")

    def test_reopened_chat_keeps_original_message_timestamps(self):
        self.messenger.open()
        self.fire_timer()
        before = self.messenger.transcript.get("1.0", "end")
        self.messenger.window.destroy()
        self.messenger.open()
        self.assertEqual(self.messenger.transcript.get("1.0", "end"), before)
        self.assertIsNotNone(self.messenger.history[0][2].utcoffset())

    def test_each_send_attempt_has_separate_notice_and_no_direct_reply(self):
        self.messenger.open()
        timer = self.messenger._timer
        for text in ("hello", "", "   ", "are you there"):
            self.messenger.entry.insert(0, text)
            self.messenger.send_button.invoke()
        self.assertEqual([(sender, text) for sender, text, timestamp in self.messenger.history],
                         [("You", "hello"), ("You", "are you there")])
        self.assertEqual(len(self.notices()), 4)
        self.assertEqual(self.messenger._timer, timer)
        self.assertEqual(self.messenger._sent, 0)
        for notice in self.notices():
            labels = [child.cget("text") for child in notice.winfo_children() if isinstance(child, tk.Label)]
            self.assertIn(AWAY_NOTICE, labels)
            buttons = [child for child in notice.winfo_children() if isinstance(child, tk.Button)]
            self.assertEqual([button.cget("text") for button in buttons], ["OK"])
            buttons[0].invoke()
        self.assertEqual(self.notices(), [])
        self.assertNotIn(AWAY_NOTICE, self.messenger.transcript.get("1.0", "end"))

    def test_reply_immediately_after_harold_message_still_gets_notice(self):
        self.messenger.open()
        self.fire_timer()
        timer = self.messenger._timer
        self.messenger.entry.insert(0, "what do you mean")
        self.messenger.send()
        self.assertEqual([sender for sender, text, timestamp in self.messenger.history], ["Harold", "You"])
        self.assertEqual(len(self.notices()), 1)
        self.assertEqual(self.messenger._timer, timer)
        self.fire_timer()
        self.assertEqual([sender for sender, text, timestamp in self.messenger.history], ["Harold", "You", "Harold"])

    def test_notice_survives_chat_close_and_supports_escape_and_close_cross(self):
        window = self.messenger.open()
        self.messenger.send()
        notice, = self.notices()
        window.destroy()
        self.assertTrue(notice.winfo_exists())
        notice.update()
        notice.focus_force()
        notice.event_generate("<Escape>")
        self.root.update()
        self.assertEqual(self.notices(), [])
        self.messenger.open()
        self.messenger.send()
        notice, = self.notices()
        notice.tk.call(notice.protocol("WM_DELETE_WINDOW"))
        self.assertEqual(self.notices(), [])
        self.assertEqual(self.messenger.history, [])

    def test_shutdown_cancels_timer_and_does_not_restart(self):
        timer = self.messenger._timer
        self.messenger.shutdown()
        self.messenger.shutdown()
        self.assertNotIn(timer, self.root.tk.call("after", "info"))
        self.assertIsNone(self.messenger._timer)
        self.assertIsNone(self.messenger.open())

    def test_root_destruction_cancels_timer(self):
        root = tk.Tk()
        messenger = HaroldMessenger(root)
        timer = messenger._timer
        root.destroy()
        self.assertTrue(messenger._stopped)
        self.assertIsNone(messenger._timer)
        self.assertNotIn(timer, root.tk.call("after", "info"))

    def test_new_session_starts_without_previous_history(self):
        self.fire_timer()
        root = tk.Tk()
        messenger = HaroldMessenger(root)
        try:
            self.assertEqual(messenger.history, [])
            self.assertEqual(messenger._sent, 0)
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
