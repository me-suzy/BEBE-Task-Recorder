#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tkinter as tk
from tkinter import ttk
import time

class Tooltip:
    """Tooltip class pentru butoane - versiune îmbunătățită"""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip = None
        self.widget.bind("<Enter>", self.show_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)
        # Binding pentru motion pentru a actualiza poziția
        self.widget.bind("<Motion>", self.on_motion)
        print(f"DEBUG: Tooltip bound to widget for '{text}'")  # DEBUG

    def on_motion(self, event=None):
        """Actualizează poziția tooltip-ului la mișcarea mouse-ului"""
        if self.tooltip:
            try:
                # Recalculează poziția
                x = self.widget.winfo_rootx() + 25
                y = self.widget.winfo_rooty() + 25
                self.tooltip.wm_geometry(f"+{x}+{y}")
            except:
                pass

    def show_tooltip(self, event=None):
        """Arată tooltip-ul"""
        print(f"DEBUG: show_tooltip called for '{self.text}'")  # DEBUG
        # Ascunde tooltip existent
        if self.tooltip:
            self.hide_tooltip()

        # Așteaptă puțin pentru ca widget-ul să fie complet rendered
        self.widget.after(50, self._create_tooltip)

    def _create_tooltip(self):
        """Creează tooltip window"""
        try:
            # Verifică dacă widget-ul există încă
            if not self.widget.winfo_exists():
                return

            # Obține poziția absolută a widget-ului
            x = self.widget.winfo_rootx() + 25
            y = self.widget.winfo_rooty() + 25
            print(f"DEBUG: Creating tooltip at x={x}, y={y} for '{self.text}'")

            # Creează tooltip window
            self.tooltip = tk.Toplevel(self.widget)
            self.tooltip.wm_overrideredirect(True)

            # Important: Setează tooltip ca transient pentru mini window
            try:
                self.tooltip.wm_transient(self.widget.winfo_toplevel())
            except:
                pass

            self.tooltip.wm_geometry(f"+{x}+{y}")

            # Setează always on top pentru tooltip
            try:
                self.tooltip.attributes('-topmost', True)
            except:
                pass

            # Creează label cu text
            label = tk.Label(
                self.tooltip,
                text=self.text,
                background="#ffffe0",
                relief="solid",
                borderwidth=1,
                font=("Segoe UI", 9),
                padx=8,
                pady=4
            )
            label.pack()

            # Force update pentru a vedea tooltip-ul imediat
            self.tooltip.update_idletasks()
            print(f"DEBUG: Tooltip window created and visible for '{self.text}'")

        except Exception as e:
            # Log error dar nu crash
            print(f"Tooltip error: {e}")
            if self.tooltip:
                try:
                    self.tooltip.destroy()
                except:
                    pass
                self.tooltip = None

    def hide_tooltip(self, event=None):
        """Ascunde tooltip-ul"""
        if self.tooltip:
            try:
                self.tooltip.destroy()
            except:
                pass
            finally:
                self.tooltip = None

# Test simplu
def test_tooltip():
    root = tk.Tk()
    root.title("Tooltip Test")
    root.geometry("300x200+100+100")

    frame = ttk.Frame(root, padding="20")
    frame.pack(fill=tk.BOTH, expand=True)

    # Creează buton de test
    test_btn = ttk.Button(frame, text="Test Button", width=15)
    test_btn.pack(pady=20)

    # Adaugă tooltip
    Tooltip(test_btn, "Test Tooltip (F1)")

    print("Test window created. Move mouse over the button to test tooltip.")
    root.mainloop()

if __name__ == "__main__":
    test_tooltip()
