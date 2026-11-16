"""Session-only messenger with unsolicited messages and no direct replies."""

import random
import tkinter as tk
from datetime import datetime
from pathlib import Path


GRAY = "#C0C0C0"
NAVY = "#000080"
FONT = ("Helvetica", 9)
AWAY_NOTICE = "The user you are trying to contact has not been at their desk for some time."
MAX_MESSAGES = 3
MESSAGES = (
    "my coffee is too hot", "is this the internet", "i can't find my mouse",
    "the printer is making a noise", "i think i deleted the internet",
    "how do i close this window", "someone moved my chair", "i clicked something",
    "there is a bird outside", "nevermind", "who is admin",
)


def _button(parent, text, command):
    return tk.Button(parent, text=text, command=command, font=FONT, bg=GRAY, fg="black",
                     activebackground=GRAY, activeforeground="black", relief="raised",
                     borderwidth=2, padx=10, pady=3, highlightbackground="black")


def _avatar(parent):
    return tk.PhotoImage(master=parent, file=str(Path(__file__).parent / "assets" / "harold.png"))


class HaroldMessenger:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.window = None
        self.history = []
        self._random = random.Random()
        self._sent = 0
        self._timer = None
        self._stopped = False
        root.bind("<Destroy>", self._on_destroy, add="+")
        self._schedule()

    def _schedule(self) -> None:
        if not self._stopped and self._sent < MAX_MESSAGES:
            self._timer = self.root.after(self._random.randint(180_000, 600_000), self._receive)

    def _receive(self) -> None:
        self._timer = None
        if self._stopped or self._sent >= MAX_MESSAGES:
            return
        self._append("Harold", self._random.choice(MESSAGES))
        self._sent += 1
        self._schedule()

    def _on_destroy(self, event) -> None:
        if event.widget is self.root:
            self.shutdown()

    def shutdown(self) -> None:
        self._stopped = True
        if self._timer is not None:
            self.root.after_cancel(self._timer)
            self._timer = None

    def open(self):
        if self._stopped:
            return None
        if self.window is not None:
            self.window.lift()
            self.entry.focus_set()
            return self.window
        window = self.window = tk.Toplevel(self.root, bg=GRAY, borderwidth=2, relief="raised")
        window.title("Harold P. Wiggins — Office Messenger")
        window.geometry("680x400")
        window.minsize(480, 320)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(2, weight=1)
        titlebar = tk.Frame(window, bg=NAVY)
        titlebar.grid(row=0, sticky="ew", padx=3, pady=3)
        tk.Label(titlebar, text="Harold P. Wiggins — Office Messenger", bg=NAVY,
                 fg="white", font=FONT, anchor="w", padx=6, pady=5).pack(side="left")
        tk.Button(titlebar, text="×", command=window.destroy, bg=NAVY, fg="white",
                  activebackground=NAVY, activeforeground="white", relief="flat",
                  borderwidth=0, highlightthickness=0, font=FONT, width=3).pack(side="right")
        header = tk.Frame(window, bg=GRAY)
        header.grid(row=1, sticky="ew", padx=10, pady=(10, 12))
        self.avatar = _avatar(window)
        tk.Label(header, image=self.avatar, bg="white", borderwidth=0).pack(side="left", padx=(0, 12))
        contact = tk.Frame(header, bg=GRAY)
        contact.pack(side="left")
        tk.Label(contact, text="Harold P. Wiggins", bg=GRAY, fg="black", font=FONT).pack(anchor="w")
        tk.Label(contact, text="Status: Away", bg=GRAY, fg="#606060",
                 font=("Helvetica", 8)).pack(anchor="w", pady=(3, 0))
        tk.Label(contact, text="Last seen: Unknown", bg=GRAY, fg="#606060",
                 font=("Helvetica", 8)).pack(anchor="w")
        chat = tk.Frame(window, bg=GRAY)
        chat.grid(row=2, sticky="nsew", padx=6, pady=4)
        chat.columnconfigure(0, weight=1)
        chat.rowconfigure(0, weight=1)
        self.transcript = tk.Text(chat, bg="white", fg="black", font=("Helvetica", 10), wrap="word",
                                  width=40, height=10, relief="sunken", borderwidth=2,
                                  state="disabled", padx=9, pady=5,
                                  selectbackground=NAVY, selectforeground="white")
        self.transcript.tag_configure("metadata", foreground="#808080", font=("Helvetica", 8), spacing3=3)
        self.transcript.grid(sticky="nsew")
        scroll = tk.Scrollbar(chat, command=self.transcript.yview, bg=GRAY,
                              troughcolor=GRAY, relief="raised", borderwidth=2)
        scroll.grid(row=0, column=1, sticky="ns")
        self.transcript.configure(yscrollcommand=scroll.set)
        inputs = tk.Frame(window, bg=GRAY)
        inputs.grid(row=3, sticky="ew", padx=6, pady=6)
        inputs.columnconfigure(0, weight=1)
        self.entry = tk.Entry(inputs, bg="white", fg="black", font=FONT,
                               insertbackground="black", relief="sunken", borderwidth=2)
        self.entry.grid(sticky="ew", padx=(0, 6))
        self.send_button = _button(inputs, "Send", self.send)
        self.send_button.grid(row=0, column=1)
        self.entry.bind("<Return>", lambda event: self.send() or "break")
        window.protocol("WM_DELETE_WINDOW", window.destroy)
        window.bind("<Destroy>", self._on_window_destroy, add="+")
        for sender, text, timestamp in self.history:
            self._display(sender, text, timestamp)
        self.entry.focus_set()
        return window

    def _on_window_destroy(self, event) -> None:
        if event.widget is self.window:
            self.window = None

    def _display(self, sender: str, text: str, timestamp: datetime) -> None:
        self.transcript.configure(state="normal")
        self.transcript.insert("end", f"{sender} — {timestamp:%H:%M}\n", "metadata")
        self.transcript.insert("end", f"{text}\n\n")
        self.transcript.configure(state="disabled")
        self.transcript.see("end")

    def _append(self, sender: str, text: str) -> None:
        timestamp = datetime.now().astimezone()
        self.history.append((sender, text, timestamp))
        if self.window is not None:
            self._display(sender, text, timestamp)

    def send(self) -> None:
        if self.window is None or self._stopped:
            return
        text = self.entry.get().strip()
        self.entry.delete(0, "end")
        if text:
            self._append("You", text)
        # Even an empty send attempt gets the same independent system notice.
        self._show_unavailable()

    def _show_unavailable(self):
        dialog = tk.Toplevel(self.root, bg=GRAY, borderwidth=2, relief="raised")
        dialog.title("Messenger Service")
        dialog.resizable(False, False)
        dialog.geometry("680x136")
        dialog.columnconfigure(1, weight=1)
        dialog.rowconfigure(1, weight=1)
        titlebar = tk.Frame(dialog, bg=NAVY)
        titlebar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=5, pady=5)
        tk.Label(titlebar, text="Messenger Service", bg=NAVY, fg="white", font=FONT,
                 anchor="w", padx=6, pady=5).pack(side="left")
        tk.Button(titlebar, text="×", command=dialog.destroy, bg=NAVY, fg="white",
                  activebackground=NAVY, activeforeground="white", relief="flat",
                  borderwidth=0, highlightthickness=0, font=FONT, width=3).pack(side="right")
        tk.Label(dialog, text="ⓘ", bg=GRAY, fg=NAVY, font=("Helvetica", 16)).grid(
            row=1, column=0, padx=(14, 4), sticky="w")
        tk.Label(dialog, text=AWAY_NOTICE, bg=GRAY, fg="black", font=FONT,
                 justify="left", wraplength=560, padx=4, pady=14).grid(row=1, column=1, sticky="w")
        button = _button(dialog, "OK", dialog.destroy)
        button.grid(row=2, column=1, sticky="e", padx=8, pady=(0, 8))
        dialog.bind("<Escape>", lambda event: dialog.destroy())
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        button.focus_set()
        return dialog
