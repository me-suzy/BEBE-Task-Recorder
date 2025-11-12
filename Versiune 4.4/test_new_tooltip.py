#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tkinter as tk
from tkinter import ttk

class ToolTip:
    """Tooltip simplu pentru orice widget Tk/ttk."""
    def __init__(self, widget, text, delay_ms=400, padx=12, pady=8):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self.padx = padx
        self.pady = pady
        self._id_after = None
        self._tip = None

        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        widget.bind("<Motion>", self._on_motion, add="+")

    def _on_enter(self, _):
        self._schedule()

    def _on_leave(self, _):
        self._cancel()
        self._hide()

    def _on_motion(self, event):
        # dacă tooltipul e deja vizibil, îl mutăm
        if self._tip is not None:
            x = event.x_root + self.padx
            y = event.y_root + self.pady
            self._tip.geometry(f"+{x}+{y}")

    def _schedule(self):
        self._cancel()
        self._id_after = self.widget.after(self.delay_ms, self._show)

    def _cancel(self):
        if self._id_after is not None:
            self.widget.after_cancel(self._id_after)
            self._id_after = None

    def _show(self):
        if self._tip or not self.text:
            return
        # fereastră „plutitoare” fără border
        self._tip = tk.Toplevel(self.widget)
        self._tip.wm_overrideredirect(True)  # fără decorații
        self._tip.attributes("-topmost", True)

        label = tk.Label(
            self._tip,
            text=self.text,
            justify="left",
            relief="solid",
            borderwidth=1,
            padx=8, pady=4,
            bg="#ffffe0"  # galben pal tipic pentru tooltip
        )
        label.pack()

        # poziționare inițială lângă cursor
        try:
            x, y = self.widget.winfo_pointerxy()
        except tk.TclError:
            x = self.widget.winfo_rootx()
            y = self.widget.winfo_rooty() + self.widget.winfo_height()
        self._tip.geometry(f"+{x + self.padx}+{y + self.pady}")

    def _hide(self):
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None

def test_new_tooltip():
    root = tk.Tk()
    root.title("Test ToolTip Nou")
    root.geometry("300x200+100+100")

    frame = ttk.Frame(root, padding=20)
    frame.pack(fill=tk.BOTH, expand=True)

    # Creează buton de test
    test_btn = ttk.Button(frame, text="⏺", width=4)
    test_btn.pack(pady=20)

    # Adaugă tooltip
    ToolTip(test_btn, "Înregistrează secvența (F1)", delay_ms=300)

    print("Test window created. Hover over the button for 300ms to see tooltip.")
    root.mainloop()

if __name__ == "__main__":
    test_new_tooltip()
