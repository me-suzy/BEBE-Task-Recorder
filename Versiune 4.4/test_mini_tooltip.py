#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tkinter as tk
from tkinter import ttk

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
        print(f"DEBUG: show_tooltip called for '{self.text}'")
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

def test_mini_tooltip():
    # Fereastra principală
    root = tk.Tk()
    root.title("Main Window")
    root.geometry("400x300+100+100")

    # Buton pentru a deschide mini window
    open_btn = ttk.Button(root, text="Open Mini Window", command=lambda: create_mini_window(root))
    open_btn.pack(pady=20)

    def create_mini_window(parent):
        # Creează mini window similar cu cea din BEBE
        mini_window = tk.Toplevel(parent)
        mini_window.title("BEBE Mini Test")
        mini_window.geometry("290x85")
        mini_window.resizable(False, False)
        mini_window.attributes('-topmost', True)

        # Position in bottom-right
        screen_width = mini_window.winfo_screenwidth()
        screen_height = mini_window.winfo_screenheight()
        x = screen_width - 310
        y = screen_height - 125
        mini_window.geometry(f"290x85+{x}+{y}")

        # Main frame
        main_frame = ttk.Frame(mini_window, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Single row of icon-only buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X)

        # Play button
        play_btn = ttk.Button(
            btn_frame, text="▶", width=5,
            command=lambda: print("Play clicked")
        )
        play_btn.pack(side=tk.LEFT, padx=3)

        # Creează tooltip imediat (nu cu after)
        print("DEBUG: Creating tooltip immediately")
        Tooltip(play_btn, "Play (Space)")

        print("Mini window created. Move mouse over the play button.")

    root.mainloop()

if __name__ == "__main__":
    test_mini_tooltip()
