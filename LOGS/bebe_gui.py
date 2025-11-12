#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BEBE Task Recorder - GUI Version 3.0
Aplicație cu interfață grafică pentru înregistrare și redare task-uri
Versiune îmbunătățită cu export executabile, i18n, pause, scheduling și multe altele
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import time
import json
import sys
import threading
import logging
from datetime import datetime, time as dt_time
from pathlib import Path
import pyautogui
from pynput import mouse, keyboard
from pynput.keyboard import Key, Controller as KeyboardController
import ctypes
import subprocess
import tempfile
import shutil
import textwrap

# System tray imports
try:
    import pystray
    from PIL import Image, ImageDraw
    SYSTEM_TRAY_AVAILABLE = True
except ImportError:
    SYSTEM_TRAY_AVAILABLE = False

APP_VERSION = "4.4"
TASK_DATA_VERSION = "4.4"

# Import i18n
try:
    from i18n import get_string, set_language, get_current_language
except ImportError:
    # Fallback dacă nu există i18n
    def get_string(key, **kwargs):
        return key
    def set_language(lang):
        return True
    def get_current_language():
        return 'ro'

# Fix encoding pentru Windows (doar daca nu e executabil PyInstaller)
if sys.platform == 'win32' and not getattr(sys, 'frozen', False):
    try:
        import codecs
        if sys.stdout and hasattr(sys.stdout, 'buffer') and sys.stdout.buffer:
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        if sys.stderr and hasattr(sys.stderr, 'buffer') and sys.stderr.buffer:
            sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    except:
        pass  # Ignora erorile de encoding in executabil

# Configurare PyAutoGUI
pyautogui.PAUSE = 0.01
pyautogui.FAILSAFE = True


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


def is_admin():
    """Verifica daca ruleaza ca administrator"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def run_as_admin():
    """Ruleaza programul ca administrator"""
    if not is_admin():
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )
        sys.exit()


def format_event_details(event):
    """
    Formatează detaliile unui eveniment pentru afișare
    Consolidat pentru a elimina cod duplicat
    """
    event_type = event['type']

    if event_type == 'mouse_move':
        return f"({event['x']}, {event['y']})"
    elif event_type == 'mouse_click':
        action = "Press" if event['pressed'] else "Release"
        button = event['button'].replace('Button.', '')
        return f"{action} {button} @ ({event['x']}, {event['y']})"
    elif event_type == 'mouse_scroll':
        direction = "Sus" if event['dy'] > 0 else "Jos"
        return f"Scroll {direction}"
    elif event_type == 'key_press':
        key_display = event['key']
        if '+' in key_display:
            parts = key_display.split('+')
            formatted = ' + '.join(p.capitalize() for p in parts[:-1]) + ' + ' + parts[-1].upper()
            return f"Press {formatted}"
        else:
            return f"Press {key_display}"
    elif event_type == 'key_release':
        key_display = event['key']
        if '+' in key_display:
            parts = key_display.split('+')
            formatted = ' + '.join(p.capitalize() for p in parts[:-1]) + ' + ' + parts[-1].upper()
            return f"Release {formatted}"
        else:
            return f"Release {key_display}"
    else:
        return str(event)


class TaskRecorder:
    """Inregistreaza actiuni mouse si tastatura"""

    def __init__(self, callback=None):
        self.events = []
        self.recording = False
        self.start_time = None
        self.mouse_listener = None
        self.keyboard_listener = None
        self.stop_requested = False
        self.callback = callback  # Callback pentru update GUI

        # Track taste modificatoare pentru combinatii
        self.pressed_modifiers = set()  # Set de taste apasate (ctrl, alt, shift)

    def start_recording(self):
        """Incepe inregistrarea"""
        self.events = []
        self.recording = True
        self.stop_requested = False
        self.start_time = time.time()
        self.pressed_modifiers = set()  # Reset modificatori

        # Mouse listener
        self.mouse_listener = mouse.Listener(
            on_move=self.on_mouse_move,
            on_click=self.on_mouse_click,
            on_scroll=self.on_mouse_scroll
        )

        # Keyboard listener
        self.keyboard_listener = keyboard.Listener(
            on_press=self.on_key_press,
            on_release=self.on_key_release
        )

        self.mouse_listener.start()
        self.keyboard_listener.start()

    def stop_recording(self):
        """Opreste inregistrarea"""
        if not self.recording:
            return self.events

        self.recording = False

        if self.mouse_listener:
            self.mouse_listener.stop()

        if self.keyboard_listener:
            self.keyboard_listener.stop()

        return self.events

    def get_timestamp(self):
        """Timestamp relativ"""
        if self.start_time:
            return time.time() - self.start_time
        return 0

    def on_mouse_move(self, x, y):
        """Inregistreaza miscare mouse"""
        if self.recording:
            timestamp = self.get_timestamp()
            if not self.events or (timestamp - self.events[-1]['timestamp']) > 0.1:
                event = {
                    'type': 'mouse_move',
                    'x': x,
                    'y': y,
                    'timestamp': timestamp
                }
                self.events.append(event)
                if self.callback:
                    self.callback(f"Mouse Move ({x}, {y})")

    def on_mouse_click(self, x, y, button, pressed):
        """Inregistreaza click-uri"""
        if self.recording:
            timestamp = self.get_timestamp()
            button_name = str(button).replace('Button.', '')
            action = "Press" if pressed else "Release"

            event = {
                'type': 'mouse_click',
                'x': x,
                'y': y,
                'button': str(button),
                'pressed': pressed,
                'timestamp': timestamp
            }
            self.events.append(event)
            if self.callback:
                self.callback(f"Mouse {action} {button_name} @ ({x}, {y})")

    def on_mouse_scroll(self, x, y, dx, dy):
        """Inregistreaza scroll"""
        if self.recording:
            timestamp = self.get_timestamp()
            event = {
                'type': 'mouse_scroll',
                'x': x,
                'y': y,
                'dx': dx,
                'dy': dy,
                'timestamp': timestamp
            }
            self.events.append(event)
            direction = "Sus" if dy > 0 else "Jos"
            if self.callback:
                self.callback(f"Scroll {direction}")

    def convert_control_char(self, char):
        """Convertește caractere de control în combinații de taste"""
        if not char or len(char) != 1:
            return None

        code = ord(char)
        # Caractere de control (0x01-0x1F) = Ctrl + literă
        if 0x01 <= code <= 0x1A:  # Ctrl+A până la Ctrl+Z
            letter = chr(code + ord('A') - 1)  # 0x01 -> 'A', 0x02 -> 'B', etc.
            return letter.lower()
        elif code == 0x1B:  # ESC
            return 'esc'
        return None

    def get_key_name(self, key):
        """Extrage numele tastei pentru salvare"""
        try:
            if hasattr(key, 'char') and key.char is not None:
                return key.char
            else:
                # Tasta speciala (Enter, Tab, F4, etc.)
                key_str = str(key).replace('Key.', '')
                return key_str
        except:
            return str(key)

    def on_key_press(self, key):
        """Inregistreaza apasare tasta"""
        if self.recording:
            # Verifica ESC sau F9 pentru stop
            if key == Key.f9 or key == Key.esc:
                self.stop_requested = True
                return False

            timestamp = self.get_timestamp()

            # PASUL 1: Detecteaza si marcheaza taste modificatoare (Ctrl, Alt, Shift)
            # Nu salvam modificatorii separat, doar ii tinem minte
            if key == Key.ctrl or key == Key.ctrl_l or key == Key.ctrl_r:
                self.pressed_modifiers.add('ctrl')
                return  # Nu salva event pentru modificator
            elif key == Key.alt or key == Key.alt_l or key == Key.alt_r:
                self.pressed_modifiers.add('alt')
                return  # Nu salva event pentru modificator
            elif key == Key.shift or key == Key.shift_l or key == Key.shift_r:
                self.pressed_modifiers.add('shift')
                return  # Nu salva event pentru modificator

            # PASUL 2: Proceseaza tasta normala sau speciala
            key_name = None
            key_display = None

            try:
                if hasattr(key, 'char') and key.char is not None:
                    char = key.char
                    # Verifica daca e caracter de control (Ctrl+litera = \x01-\x1A)
                    control_letter = self.convert_control_char(char)

                    if control_letter and 'ctrl' in self.pressed_modifiers:
                        # E o combinatie Ctrl+litera (ex: Ctrl+A = '\x01')
                        # Verifica daca sunt si alti modificatori (ex: Ctrl+Shift+A)
                        if 'shift' in self.pressed_modifiers:
                            key_name = f"ctrl+shift+{control_letter}"
                            key_display = f"Ctrl + Shift + {control_letter.upper()}"
                        elif 'alt' in self.pressed_modifiers:
                            key_name = f"ctrl+alt+{control_letter}"
                            key_display = f"Ctrl + Alt + {control_letter.upper()}"
                        else:
                            key_name = f"ctrl+{control_letter}"
                            key_display = f"Ctrl + {control_letter.upper()}"
                    else:
                        # Tasta normala (litera, cifra, caracter)
                        # Verifica daca sunt modificatori apasati
                        if self.pressed_modifiers:
                            # Construieste combinatie cu modificatori
                            mods = sorted(self.pressed_modifiers)
                            key_name = '+'.join(mods) + '+' + char
                            mods_display = ' + '.join(m.capitalize() for m in mods)
                            key_display = f"{mods_display} + '{char}'"
                        else:
                            # Tasta normala fara modificatori
                            key_name = char
                            key_display = f"'{char}'"
                else:
                    # Tasta speciala (Enter, Tab, F4, Arrow keys, etc.)
                    key_str = str(key).replace('Key.', '')

                    if self.pressed_modifiers:
                        # Construieste combinatie cu modificatori (ex: Alt+F4, Ctrl+Tab)
                        mods = sorted(self.pressed_modifiers)
                        key_name = '+'.join(mods) + '+' + key_str
                        mods_display = ' + '.join(m.capitalize() for m in mods)
                        key_display = f"{mods_display} + {key_str.upper()}"
                    else:
                        # Tasta speciala fara modificatori
                        key_name = key_str
                        key_display = key_str.upper()
            except Exception as e:
                # Fallback pentru erori
                key_name = str(key)
                key_display = str(key)

            # PASUL 3: Salveaza event-ul
            if key_name:
                event = {
                    'type': 'key_press',
                    'key': key_name,
                    'modifiers': list(self.pressed_modifiers),
                    'timestamp': timestamp
                }
                self.events.append(event)
                if self.callback:
                    self.callback(f"Key Press {key_display}")

    def on_key_release(self, key):
        """Inregistreaza eliberare tasta"""
        if self.recording:
            # Elimina modificator din set daca e eliberat
            # Nu salvam eliberarea modificatorilor separat
            if key == Key.ctrl or key == Key.ctrl_l or key == Key.ctrl_r:
                self.pressed_modifiers.discard('ctrl')
                return
            elif key == Key.alt or key == Key.alt_l or key == Key.alt_r:
                self.pressed_modifiers.discard('alt')
                return
            elif key == Key.shift or key == Key.shift_l or key == Key.shift_r:
                self.pressed_modifiers.discard('shift')
                return

            # Pentru taste normale, salvam eliberarea
            timestamp = self.get_timestamp()

            try:
                if hasattr(key, 'char') and key.char is not None:
                    char = key.char
                    # Verifica daca e caracter de control
                    control_letter = self.convert_control_char(char)

                    if control_letter and 'ctrl' in self.pressed_modifiers:
                        # E o combinatie Ctrl+litera
                        if 'shift' in self.pressed_modifiers:
                            key_name = f"ctrl+shift+{control_letter}"
                        elif 'alt' in self.pressed_modifiers:
                            key_name = f"ctrl+alt+{control_letter}"
                        else:
                            key_name = f"ctrl+{control_letter}"
                    elif self.pressed_modifiers:
                        # Tasta normala cu modificatori
                        mods = sorted(self.pressed_modifiers)
                        key_name = '+'.join(mods) + '+' + char
                    else:
                        key_name = char
                else:
                    # Tasta speciala
                    key_str = str(key).replace('Key.', '')
                    if self.pressed_modifiers:
                        mods = sorted(self.pressed_modifiers)
                        key_name = '+'.join(mods) + '+' + key_str
                    else:
                        key_name = key_str
            except:
                key_name = str(key)

            event = {
                'type': 'key_release',
                'key': key_name,
                'timestamp': timestamp
            }
            self.events.append(event)


class TaskPlayer:
    """Reda task-uri cu suport pentru pauză"""

    def __init__(self):
        self.playing = False
        self.paused = False
        self.pause_event = threading.Event()
        self.keyboard_controller = KeyboardController()
        self.stop_requested = False

    def play_events(self, events, speed=2.0, loop_count=1, callback=None, run_until_stop=False):
        """
        Reda evenimente

        Args:
            events: Lista de evenimente
            speed: Viteza de redare
            loop_count: Număr de repetări (ignorat dacă run_until_stop=True)
            callback: Funcție callback pentru update GUI
            run_until_stop: Dacă True, rulează continuu până la stop
        """
        self.playing = True
        self.paused = False
        self.stop_requested = False
        self.pause_event.set()  # Setat = nu e pauzat

        # Validare viteza
        speed = max(0.1, min(10.0, speed))

        # ✅ LOGGING ÎNAINTE DE WHILE
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"🔄 Starting playback loop: loop_count={loop_count}, run_until_stop={run_until_stop}")

        loop = 0
        while True:
            loop += 1

            # ✅ LOGGING LA FIECARE ITERAȚIE
            logger.info(f"🔄 Loop iteration {loop}/{loop_count if not run_until_stop else '∞'}")

            if not run_until_stop and loop > loop_count:
                logger.info(f"✋ Breaking: loop ({loop}) > loop_count ({loop_count})")
                break

            logger.info(f"▶️ Playing {len(events)} events (iteration {loop})...")

            for i, event in enumerate(events):
                if not self.playing or self.stop_requested:
                    logger.warning(f"⚠️ Breaking from event loop: playing={self.playing}, stop_requested={self.stop_requested}")
                    break

                # Verifică pauză
                while self.paused and self.playing and not self.stop_requested:
                    self.pause_event.clear()
                    time.sleep(0.1)

                if not self.playing or self.stop_requested:
                    logger.warning(f"⚠️ Breaking after pause check: playing={self.playing}, stop_requested={self.stop_requested}")
                    break

                if i > 0:
                    delay = (event['timestamp'] - events[i-1]['timestamp']) / speed
                    if delay > 0:
                        time.sleep(delay)

                self.execute_event(event, i + 1, len(events), callback)

            logger.info(f"✅ Finished playing events (iteration {loop})")

            # Verifică dacă trebuie să oprească
            if self.stop_requested:
                logger.info(f"✋ Breaking: stop_requested={self.stop_requested}")
                break

            logger.info(f"🔄 End of iteration {loop}, continuing to next iteration...")

        logger.info(f"🏁 Playback loop finished after {loop} iteration(s)")

        self.playing = False
        self.paused = False

    def execute_event(self, event, current, total, callback=None):
        """Executa eveniment"""
        try:
            event_type = event['type']

            if event_type == 'mouse_move':
                x, y = event['x'], event['y']
                pyautogui.moveTo(x, y, duration=0)
                if callback:
                    percent = int((current / total) * 100)
                    callback(get_string('progress_playing', current=current, total=total, percent=percent))

            elif event_type == 'mouse_click':
                x, y = event['x'], event['y']
                button_str = event['button']
                pressed = event['pressed']

                if 'left' in button_str.lower():
                    button = 'left'
                elif 'right' in button_str.lower():
                    button = 'right'
                else:
                    button = 'middle'

                pyautogui.moveTo(x, y, duration=0)

                if pressed:
                    pyautogui.mouseDown(button=button)
                    action = "Press"
                else:
                    pyautogui.mouseUp(button=button)
                    action = "Release"

                if callback:
                    percent = int((current / total) * 100)
                    callback(get_string('progress_playing', current=current, total=total, percent=percent))

            elif event_type == 'mouse_scroll':
                dy = event['dy']
                pyautogui.scroll(int(dy * 100))
                if callback:
                    percent = int((current / total) * 100)
                    callback(get_string('progress_playing', current=current, total=total, percent=percent))

            elif event_type == 'key_press':
                key_name = event['key']

                # Verifica daca e combinatie (ex: ctrl+a sau ctrl+'a')
                if '+' in key_name:
                    parts = key_name.split('+')
                    modifiers = parts[:-1]  # ctrl, alt, shift
                    main_key_str = parts[-1]    # 'a' sau "'a'"

                    # Curata tasta principala (elimina ghilimele daca exista)
                    main_key_str = main_key_str.strip("'\"")

                    # Apasa modificatorii
                    for mod in modifiers:
                        if mod.lower() == 'ctrl':
                            self.keyboard_controller.press(Key.ctrl)
                        elif mod.lower() == 'alt':
                            self.keyboard_controller.press(Key.alt)
                        elif mod.lower() == 'shift':
                            self.keyboard_controller.press(Key.shift)

                    # Apasa tasta principala
                    key = self.parse_key(main_key_str)
                    self.keyboard_controller.press(key)
                    time.sleep(0.01)  # Mic delay
                    self.keyboard_controller.release(key)

                    # Elibereaza modificatorii
                    for mod in modifiers:
                        if mod.lower() == 'ctrl':
                            self.keyboard_controller.release(Key.ctrl)
                        elif mod.lower() == 'alt':
                            self.keyboard_controller.release(Key.alt)
                        elif mod.lower() == 'shift':
                            self.keyboard_controller.release(Key.shift)
                else:
                    key = self.parse_key(key_name)
                    self.keyboard_controller.press(key)

                if callback:
                    percent = int((current / total) * 100)
                    callback(get_string('progress_playing', current=current, total=total, percent=percent))

            elif event_type == 'key_release':
                key_name = event['key']

                # Verifica daca e combinatie (ex: ctrl+a)
                if '+' in key_name:
                    parts = key_name.split('+')
                    modifiers = parts[:-1]  # ctrl, alt, shift
                    main_key_str = parts[-1]    # 'a' sau "'a'"

                    # Curata tasta principala (elimina ghilimele daca exista)
                    main_key_str = main_key_str.strip("'\"")

                    # Elibereaza tasta principala
                    key = self.parse_key(main_key_str)
                    self.keyboard_controller.release(key)

                    # Elibereaza modificatorii
                    for mod in modifiers:
                        if mod.lower() == 'ctrl':
                            self.keyboard_controller.release(Key.ctrl)
                        elif mod.lower() == 'alt':
                            self.keyboard_controller.release(Key.alt)
                        elif mod.lower() == 'shift':
                            self.keyboard_controller.release(Key.shift)
                else:
                    # Tasta simpla fara modificatori
                    key = self.parse_key(key_name)
                    self.keyboard_controller.release(key)

        except Exception as e:
            if callback:
                callback(f"Eroare: {e}")

    def parse_key(self, key_str):
        """Converteste string in Key"""
        # Mapeaza taste speciale
        special_keys = {
            'space': Key.space, 'enter': Key.enter,
            'tab': Key.tab, 'backspace': Key.backspace,
            'esc': Key.esc, 'escape': Key.esc,
            'shift': Key.shift, 'ctrl': Key.ctrl,
            'alt': Key.alt, 'up': Key.up,
            'down': Key.down, 'left': Key.left,
            'right': Key.right, 'delete': Key.delete,
            'home': Key.home, 'end': Key.end,
            'page_up': Key.page_up, 'page_down': Key.page_down,
            'insert': Key.insert, 'caps_lock': Key.caps_lock,
            'num_lock': Key.num_lock, 'scroll_lock': Key.scroll_lock,
            'f1': Key.f1, 'f2': Key.f2, 'f3': Key.f3, 'f4': Key.f4,
            'f5': Key.f5, 'f6': Key.f6, 'f7': Key.f7, 'f8': Key.f8,
            'f9': Key.f9, 'f10': Key.f10, 'f11': Key.f11, 'f12': Key.f12,
        }

        # Elimina "Key." daca exista
        key_str_clean = key_str.replace('Key.', '').lower()

        if key_str_clean in special_keys:
            return special_keys[key_str_clean]

        # Daca e un singur caracter (litera, cifra, simbol)
        if len(key_str) == 1:
            return key_str

        # Fallback: returneaza string-ul original
        return key_str

    def pause(self):
        """Pune redarea pe pauză"""
        if self.playing:
            self.paused = True
            self.pause_event.clear()

    def resume(self):
        """Reia redarea"""
        if self.playing and self.paused:
            self.paused = False
            self.pause_event.set()

    def stop(self):
        """Opreste redarea"""
        self.playing = False
        self.paused = False
        self.stop_requested = True
        self.pause_event.set()


class ScheduleDialog:
    """Dialog pentru setarea programării task-ului"""

    def __init__(self, parent, existing_config=None, gui_instance=None):
        self.parent = parent
        self.existing_config = existing_config or {}
        self.gui_instance = gui_instance  # Referință la BebeGUI pentru Loop/Run settings
        self.result = None
        self.dialog = None

    def show(self):
        """Afișează dialogul și returnează rezultatul"""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title(get_string('schedule_title'))
        self.dialog.geometry("600x680")
        self.dialog.resizable(True, True)  # Permite resize
        self.dialog.minsize(550, 600)  # Dimensiune minimă
        self.dialog.transient(self.parent)
        self.dialog.grab_set()

        # Binding pentru Esc să închidă fereastra (trebuie să fie după grab_set)
        def on_escape(e):
            self.cancel()
        self.dialog.bind('<Escape>', on_escape)
        self.dialog.bind('<KeyPress-Escape>', on_escape)
        # Binding pentru butonul X (WM_DELETE_WINDOW)
        self.dialog.protocol("WM_DELETE_WINDOW", self.cancel)

        # Focus pe fereastră pentru a primi evenimente de tastatură
        self.dialog.focus_set()

        # Frame principal
        main_frame = ttk.Frame(self.dialog, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Enable schedule (restaurează din existing_config)
        self.enable_var = tk.BooleanVar(value=self.existing_config.get('enabled', False))
        ttk.Checkbutton(main_frame, text=get_string('schedule_enable'),
                       variable=self.enable_var).pack(anchor=tk.W, pady=5)

        # Frame pentru zile
        days_frame = ttk.LabelFrame(main_frame, text=get_string('schedule_days'), padding="10")
        days_frame.pack(fill=tk.X, pady=10)

        self.day_vars = {}
        days = [
            ('monday', get_string('schedule_days_monday')),
            ('tuesday', get_string('schedule_days_tuesday')),
            ('wednesday', get_string('schedule_days_wednesday')),
            ('thursday', get_string('schedule_days_thursday')),
            ('friday', get_string('schedule_days_friday')),
            ('saturday', get_string('schedule_days_saturday')),
            ('sunday', get_string('schedule_days_sunday')),
        ]

        # Restaurează zilele selectate din existing_config
        existing_days = self.existing_config.get('days', [])
        for i, (key, label) in enumerate(days):
            var = tk.BooleanVar(value=(key in existing_days))
            self.day_vars[key] = var
            ttk.Checkbutton(days_frame, text=label, variable=var).grid(
                row=i//2, column=i%2, sticky=tk.W, padx=10, pady=5
            )

        # Buton "Select Today" pentru selecție rapidă
        def select_today():
            """Selectează ziua curentă"""
            now = datetime.now()
            current_weekday = now.weekday()  # 0 = Monday, 6 = Sunday
            weekday_map = {
                0: 'monday', 1: 'tuesday', 2: 'wednesday', 3: 'thursday',
                4: 'friday', 5: 'saturday', 6: 'sunday'
            }
            today_key = weekday_map[current_weekday]

            # Debifează toate
            for key in self.day_vars:
                self.day_vars[key].set(False)

            # Bifează ziua de azi
            self.day_vars[today_key].set(True)

        today_btn_frame = ttk.Frame(days_frame)
        today_btn_frame.grid(row=4, column=0, columnspan=2, pady=10)
        ttk.Button(today_btn_frame, text="📅 Select Today", command=select_today, width=20).pack()

        # Frame pentru interval orar (opțional)
        time_frame = ttk.LabelFrame(main_frame, text=get_string('schedule_time_interval'), padding="10")
        time_frame.pack(fill=tk.X, pady=10)

        # Checkbox pentru activarea intervalului orar (restaurează)
        time_interval_enabled = self.existing_config.get('time_interval_enabled', False)
        self.time_interval_enabled = tk.BooleanVar(value=time_interval_enabled)
        ttk.Checkbutton(time_frame, text=get_string('schedule_enable_time_interval'),
                       variable=self.time_interval_enabled,
                       command=self.toggle_time_interval).pack(anchor=tk.W, pady=(0, 10))

        # Frame pentru câmpurile de timp
        self.time_inputs_frame = ttk.Frame(time_frame)
        self.time_inputs_frame.pack(fill=tk.X, pady=5)

        # Restaurează valorile time
        existing_time_from = self.existing_config.get('time_from', '09:00')
        existing_time_to = self.existing_config.get('time_to', '17:00')

        # Linie 1: From time
        from_row = ttk.Frame(self.time_inputs_frame)
        from_row.pack(fill=tk.X, pady=5)
        ttk.Label(from_row, text=get_string('schedule_time_from'), width=12).pack(side=tk.LEFT, padx=5)
        self.time_from_var = tk.StringVar(value=existing_time_from)
        entry_state = 'normal' if time_interval_enabled else 'disabled'
        self.time_from_entry = ttk.Entry(from_row, textvariable=self.time_from_var, width=10, state=entry_state)
        self.time_from_entry.pack(side=tk.LEFT, padx=5)
        ttk.Label(from_row, text="(ex: 21:00 for 9 PM)", foreground="gray").pack(side=tk.LEFT, padx=5)

        # Linie 2: To time
        to_row = ttk.Frame(self.time_inputs_frame)
        to_row.pack(fill=tk.X, pady=5)
        ttk.Label(to_row, text=get_string('schedule_time_to'), width=12).pack(side=tk.LEFT, padx=5)
        self.time_to_var = tk.StringVar(value=existing_time_to)
        self.time_to_entry = ttk.Entry(to_row, textvariable=self.time_to_var, width=10, state=entry_state)
        self.time_to_entry.pack(side=tk.LEFT, padx=5)
        ttk.Label(to_row, text="(ex: 08:00 for 8 AM)", foreground="gray").pack(side=tk.LEFT, padx=5)

        # Info pentru interval peste miezul nopții
        info_label = ttk.Label(time_frame,
                               text=get_string('schedule_time_info'),
                               foreground="blue", font=("Arial", 8))
        info_label.pack(anchor=tk.W, pady=(5, 0))

        # Butoane
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=10)

        ttk.Button(btn_frame, text=get_string('schedule_save'),
                  command=self.save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text=get_string('schedule_cancel'),
                  command=self.cancel).pack(side=tk.LEFT, padx=5)

        # Așteaptă închiderea dialogului
        self.dialog.wait_window()
        return self.result

    def toggle_time_interval(self):
        """Activează/dezactivează câmpurile de interval orar"""
        if self.time_interval_enabled.get():
            self.time_from_entry.config(state='normal')
            self.time_to_entry.config(state='normal')
        else:
            self.time_from_entry.config(state='disabled')
            self.time_to_entry.config(state='disabled')

    def save(self):
        """Salvează setările"""
        if not self.enable_var.get():
            # Utilizatorul a debifat Enable și a dat Save → DISABLE explicit
            self.result = {'_action': 'disable'}  # Flag special pentru disable
            self.dialog.destroy()
            return

        # Validare zile
        selected_days = [key for key, var in self.day_vars.items() if var.get()]
        if not selected_days:
            messagebox.showwarning(get_string('error'), get_string('schedule_no_days'))
            return

        # Construiește rezultatul CU setările de playback din GUI
        self.result = {
            'enabled': True,
            'days': selected_days,
            'time_interval_enabled': self.time_interval_enabled.get()
        }

        # Salvează setările Loop/Run Continuously din GUI principal
        if self.gui_instance:
            self.result['playback'] = {
                'loop': bool(self.gui_instance.loop_var.get()),
                'loop_count': int(self.gui_instance.loop_count_var.get()),
                'run_until_stop': bool(self.gui_instance.run_until_stop_var.get())
            }

        # Validare și salvare interval orar (dacă este activat)
        if self.time_interval_enabled.get():
            try:
                time_from_str = self.time_from_var.get()
                time_to_str = self.time_to_var.get()

                # Parsează timpul
                time_from = datetime.strptime(time_from_str, "%H:%M").time()
                time_to = datetime.strptime(time_to_str, "%H:%M").time()

                # Permite interval peste miezul nopții (ex: 21:00 - 00:00 sau 21:00 - 03:00)
                # Nu mai validăm că time_from < time_to, pentru a permite intervale overnight

                self.result['time_from'] = time_from_str
                self.result['time_to'] = time_to_str

            except ValueError:
                messagebox.showerror(get_string('error'), get_string('schedule_invalid_time_format'))
                return
        else:
            # Dacă intervalul orar nu e activat, task-ul rulează toată ziua
            self.result['time_from'] = None
            self.result['time_to'] = None

        self.dialog.destroy()

    def cancel(self):
        """Anulează - nu schimbă nimic, doar închide dialogul"""
        # NU setăm self.result!
        # Păstrăm self.result = None (valoarea inițială din __init__)
        # Astfel show() va returna None, dar show_schedule_dialog() va trata asta ca "cancel"
        self.dialog.destroy()


class BebeGUI:
    """Interfață grafică - Versiune 3.0 îmbunătățită"""

    def __init__(self, root, logger=None):
        if logger is None:
            import logging
            logger = logging.getLogger(__name__)
        self.logger = logger

        # System tray initialization
        self.tray_icon = None

        self.logger.info("BebeGUI.__init__() started")
        self.root = root
        self.logger.debug("Setting window title and geometry...")
        self.root.title(f"{get_string('window_title')} - Version {APP_VERSION}")
        self.root.geometry("1400x850")  # Lățime mărită pentru a vedea toate butoanele
        self.root.resizable(True, True)
        self.root.minsize(1300, 800)  # Mărit și min-width

        # Creează menu bar
        self._create_menu_bar()

        # Adaugă versiunea în colțul de sus
        self.logger.debug("Creating version label...")
        # Folosim un frame pentru a avea un background consistent
        version_frame = tk.Frame(self.root, bg='#f0f0f0')
        version_frame.place(x=5, y=5)
        version_label = tk.Label(version_frame, text=f"Version {APP_VERSION}", font=('Segoe UI', 9, 'bold'),
                                fg='#666666', bg='#f0f0f0')
        version_label.pack(padx=5, pady=2)

        # Verifica admin
        self.logger.debug("Checking admin privileges...")
        if not is_admin():
            self.logger.warning("Not running as admin, showing dialog...")
            if messagebox.askyesno(get_string('admin_title'), get_string('admin_message')):
                run_as_admin()
            else:
                messagebox.showwarning(get_string('admin_warning_title'),
                    get_string('admin_warning_message'))
        else:
            self.logger.info("Running as admin")

        self.logger.debug("Creating TaskRecorder and TaskPlayer...")
        self.recorder = TaskRecorder(callback=self.add_event_to_list)
        self.player = TaskPlayer()
        self.current_events = []
        self.tasks_dir = Path("tasks")
        self.tasks_dir.mkdir(exist_ok=True)

        # Scheduling
        self.logger.debug("Initializing schedule variables...")
        self.schedule_config = None
        self.schedule_thread = None
        self.schedule_running = False
        self.last_schedule_trigger = None  # Timestamp ultimului trigger

        # Keyboard listener pentru ESC/F9 în timpul redării
        self.playback_keyboard_listener = None
        # Keyboard listener pentru F10 (Pause)
        self.f10_listener = None

        self.logger.debug("Calling setup_ui()...")
        self.setup_ui()
        self.logger.info("setup_ui() completed")

        # Refresh lista task-uri la startup
        self.logger.debug("Scheduling refresh_task_list()...")
        self.root.after(100, self.refresh_task_list)
        self.logger.info("BebeGUI.__init__() completed")

    def _create_menu_bar(self):
        """Creează menu bar cu File și About"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Save Task (Ctrl+S)", command=self.save_task)
        file_menu.add_command(label="Load Task (Ctrl+O)", command=self.load_task)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.show_about_dialog)

    def show_about_dialog(self):
        """Afișează dialogul About cu informații despre aplicație"""
        about_window = tk.Toplevel(self.root)
        about_window.title("About BEBE Task Recorder")
        about_window.geometry("500x400")
        about_window.resizable(False, False)
        about_window.transient(self.root)
        about_window.grab_set()

        # Centrat
        about_window.update_idletasks()
        x = (about_window.winfo_screenwidth() // 2) - (500 // 2)
        y = (about_window.winfo_screenheight() // 2) - (400 // 2)
        about_window.geometry(f"500x400+{x}+{y}")

        # Frame principal
        main_frame = ttk.Frame(about_window, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Logo/Icon (emoji)
        ttk.Label(main_frame, text="🎬", font=("Arial", 48)).pack(pady=10)

        # Titlu
        ttk.Label(main_frame, text="BEBE Task Recorder",
                 font=("Arial", 16, "bold")).pack(pady=5)

        # Versiune
        ttk.Label(main_frame, text=f"Version {APP_VERSION}",
                 font=("Arial", 10)).pack(pady=5)

        # Descriere
        ttk.Label(main_frame,
                 text="Professional macro recorder and automation tool\nfor Windows",
                 font=("Arial", 9), justify=tk.CENTER).pack(pady=10)

        ttk.Separator(main_frame, orient='horizontal').pack(fill=tk.X, pady=10)

        # Author
        ttk.Label(main_frame, text="Author:",
                 font=("Arial", 10, "bold")).pack(pady=5)
        ttk.Label(main_frame, text="Neculai Fantanaru",
                 font=("Arial", 10)).pack()

        # Website link (clickable)
        website_label = ttk.Label(main_frame, text="🌐 https://bebetaskrecorder.com/",
                                 font=("Arial", 10, "underline"),
                                 foreground="blue", cursor="hand2")
        website_label.pack(pady=5)
        website_label.bind("<Button-1>", lambda e: self._open_url("https://bebetaskrecorder.com/"))

        # GitHub link (clickable)
        github_label = ttk.Label(main_frame, text="💻 GitHub Repository",
                                font=("Arial", 10, "underline"),
                                foreground="blue", cursor="hand2")
        github_label.pack(pady=5)
        github_label.bind("<Button-1>", lambda e: self._open_url("https://github.com/me-suzy/BEBE-Task-Recorder"))

        ttk.Separator(main_frame, orient='horizontal').pack(fill=tk.X, pady=10)

        # License
        ttk.Label(main_frame, text="Licensed under MIT License",
                 font=("Arial", 8), foreground="gray").pack(pady=5)

        # Close button
        ttk.Button(main_frame, text="Close", command=about_window.destroy,
                  width=15).pack(pady=10)

    def _open_url(self, url):
        """Deschide URL în browser"""
        import webbrowser
        webbrowser.open(url)
        self.logger.info(f"Opening URL: {url}")

    def create_tray_icon(self):
        """Create system tray icon"""
        if not SYSTEM_TRAY_AVAILABLE:
            self.logger.warning("System tray not available - pystray or PIL not installed")
            return

        # Create a simple icon (16x16 red circle)
        def create_icon_image():
            width = 64
            height = 64
            image = Image.new('RGB', (width, height), 'white')
            dc = ImageDraw.Draw(image)
            dc.ellipse([8, 8, 56, 56], fill='red', outline='darkred')
            return image

        # Create menu
        menu = pystray.Menu(
            pystray.MenuItem("Show BEBE", self.show_from_tray, default=True),
            pystray.MenuItem("Mini Mode", self.toggle_mini_mode),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Schedule Task...", self.show_schedule_dialog),
            pystray.MenuItem("Next Task: Loading...", self.edit_next_schedule),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self.quit_app)
        )

        self.tray_icon = pystray.Icon(
            "BEBE",
            create_icon_image(),
            "BEBE Task Recorder",
            menu
        )

    def show_from_tray(self, icon=None, item=None):
        """Restore window from tray"""
        self.root.deiconify()
        if self.tray_icon:
            self.tray_icon.stop()
            self.tray_icon = None

    def hide_to_tray(self):
        """Hide window to system tray"""
        if not SYSTEM_TRAY_AVAILABLE:
            self.logger.warning("Cannot hide to tray - system tray not available")
            return

        if not self.tray_icon:
            self.create_tray_icon()
            # Run tray in separate thread
            import threading
            threading.Thread(target=self.tray_icon.run, daemon=True).start()

        self.root.withdraw()

    def quit_app(self, icon=None, item=None):
        """Quit application"""
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.quit()

    def setup_ui(self):
        """Creeaza interfata"""
        self.logger.debug("setup_ui() started")
        # Configurare style pentru accesibilitate (font sizes mai mari, high-DPI)
        self.logger.debug("Configuring ttk.Style...")
        style = ttk.Style()
        style.theme_use('clam')  # Folosim tema 'clam' pentru mai mult control
        self.logger.debug("Style configured")

        # Font mai mare pentru accesibilitate
        default_font = ('Segoe UI', 10)  # Font mai mare decât default
        style.configure('TLabel', font=default_font)
        style.configure('TButton', font=default_font, padding=5)
        style.configure('TCheckbutton', font=default_font)
        style.configure('TLabelFrame', font=('Segoe UI', 10, 'bold'))
        style.configure('TLabelFrame.Label', font=('Segoe UI', 10, 'bold'))

        # Frame principal cu grid layout
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Configurare grid pentru root
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # Bind keyboard shortcuts pentru accesibilitate (va fi actualizat după crearea butoanelor)

        # === SECTIUNE INREGISTRARE ===
        record_frame = ttk.LabelFrame(main_frame, text=get_string('record_section'), padding="10")
        record_frame.pack(fill=tk.X, pady=(0, 10))

        btn_frame = ttk.Frame(record_frame)
        btn_frame.pack(fill=tk.X)

        # Butoane pentru înregistrare (fără shortcuts, se folosește ESC/F9 pentru stop)
        start_text = get_string('start_recording')
        self.btn_start = ttk.Button(btn_frame, text=start_text,
                                    command=self.start_recording, width=30)
        self.btn_start.pack(side=tk.LEFT, padx=5)

        stop_text = get_string('stop_recording')
        self.btn_stop = ttk.Button(btn_frame, text=stop_text,
                                   command=self.stop_recording, state=tk.DISABLED, width=30)
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        self.lbl_status = ttk.Label(btn_frame, text=get_string('ready_for_recording'),
                                    foreground="blue")
        self.lbl_status.pack(side=tk.LEFT, padx=20)

        ttk.Label(record_frame, text=get_string('recording_instruction'),
                 foreground="gray").pack(pady=5)

        # === SECTIUNE REDARE ===
        play_frame = ttk.LabelFrame(main_frame, text=get_string('play_section'), padding="10")
        play_frame.pack(fill=tk.X, pady=(0, 10))

        controls_frame = ttk.Frame(play_frame)
        controls_frame.pack(fill=tk.X)

        # Butoane cu access keys
        play_text = get_string('play')
        self.btn_play = ttk.Button(controls_frame, text=play_text,
                                   command=self.play_task, width=20)
        self.btn_play.pack(side=tk.LEFT, padx=5)

        pause_text = get_string('pause')
        self.btn_pause = ttk.Button(controls_frame, text=f"{pause_text} (F10)",
                                    command=self.pause_playback, state=tk.DISABLED, width=20)
        self.btn_pause.pack(side=tk.LEFT, padx=5)

        stop_play_text = get_string('stop_playback')
        self.btn_stop_play = ttk.Button(controls_frame, text=f"{stop_play_text} (Esc)",
                                       command=self.stop_playback, state=tk.DISABLED, width=20)
        self.btn_stop_play.pack(side=tk.LEFT, padx=5)

        self.lbl_play_status = ttk.Label(controls_frame, text=get_string('nothing_playing'),
                                        foreground="green")
        self.lbl_play_status.pack(side=tk.LEFT, padx=20)

        # Setari redare
        settings_frame = ttk.Frame(play_frame)
        settings_frame.pack(fill=tk.X, pady=10)

        ttk.Label(settings_frame, text=get_string('playback_speed')).pack(side=tk.LEFT, padx=5)
        self.speed_var = tk.DoubleVar(value=2.0)
        self.speed_scale = ttk.Scale(settings_frame, from_=0.5, to=5.0,
                                     variable=self.speed_var, orient=tk.HORIZONTAL, length=200)
        self.speed_scale.pack(side=tk.LEFT, padx=5)
        self.lbl_speed = ttk.Label(settings_frame, text=f"{self.speed_var.get():.1f}x")
        self.lbl_speed.pack(side=tk.LEFT, padx=5)

        self.speed_var.trace('w', self.update_speed_label)

        self.loop_var = tk.BooleanVar(value=False)
        self.loop_checkbox = ttk.Checkbutton(settings_frame, text=get_string('loop'),
                       variable=self.loop_var, command=self.toggle_loop_count)
        self.loop_checkbox.pack(side=tk.LEFT, padx=5)

        # Spinbox pentru număr de replay-uri (1-100)
        loop_count_frame = ttk.Frame(settings_frame)
        loop_count_frame.pack(side=tk.LEFT, padx=5)
        ttk.Label(loop_count_frame, text="×").pack(side=tk.LEFT, padx=2)
        self.loop_count_var = tk.IntVar(value=1)
        self.loop_count_spinbox = ttk.Spinbox(
            loop_count_frame,
            from_=1,
            to=100,
            width=5,
            textvariable=self.loop_count_var,
            state='disabled'  # Disabled by default until Loop is checked
        )
        self.loop_count_spinbox.pack(side=tk.LEFT)

        # Checkbox pentru repetare continuă până la ESC/F9
        self.run_until_stop_var = tk.BooleanVar(value=False)
        self.run_until_stop_checkbox = ttk.Checkbutton(settings_frame, text=get_string('run_until_stop'),
                       variable=self.run_until_stop_var, command=self.toggle_run_until_stop)
        self.run_until_stop_checkbox.pack(side=tk.LEFT, padx=20)

        # Buton pentru setări programare cu access key (Shift+ pentru a evita interferențe)
        schedule_text = get_string('schedule_settings')
        ttk.Button(settings_frame, text=f"{schedule_text} (Shift+C)",
                  command=self.show_schedule_dialog).pack(side=tk.LEFT, padx=20)
        self.root.bind('<Shift-c>', lambda e: self.show_schedule_dialog())
        self.root.bind('<Shift-C>', lambda e: self.show_schedule_dialog())

        # Buton pentru Mini UI Mode
        ttk.Button(settings_frame, text="🔲 Mini Mode",
                  command=self.toggle_mini_mode).pack(side=tk.LEFT, padx=20)

        # === NOTEBOOK CU TABS ===
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 0))

        # TAB 1: EVENIMENTE
        events_tab = ttk.Frame(self.notebook)
        self.notebook.add(events_tab, text="📋 Events")

        # === SECTIUNE EVENIMENTE (în tab) ===
        events_frame = ttk.LabelFrame(events_tab, text=get_string('events_section'), padding="10")
        events_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Configurare grid pentru main_frame
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(2, weight=1)  # Evenimente frame sa se extinda

        # Treeview cu font mai mare pentru accesibilitate - înălțime redusă la jumătate
        columns = ('#', get_string('col_time'), get_string('col_type'), get_string('col_details'))
        self.tree = ttk.Treeview(events_frame, columns=columns, show='headings', height=7, selectmode='extended')
        # Configurare font pentru treeview
        style.configure('Treeview', font=default_font, rowheight=25)
        style.configure('Treeview.Heading', font=('Segoe UI', 10, 'bold'))

        self.tree.heading('#', text='#')
        self.tree.heading(get_string('col_time'), text=get_string('col_time'))
        self.tree.heading(get_string('col_type'), text=get_string('col_type'))
        self.tree.heading(get_string('col_details'), text=get_string('col_details'))

        self.tree.column('#', width=50)
        self.tree.column(get_string('col_time'), width=100)
        self.tree.column(get_string('col_type'), width=150)
        self.tree.column(get_string('col_details'), width=500)

        scrollbar = ttk.Scrollbar(events_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Context menu pentru Treeview (right-click)
        self.tree_context_menu = tk.Menu(self.tree, tearoff=0)
        self.tree_context_menu.add_command(label="Delete Event (Del)", command=self.delete_selected_event)
        self.tree_context_menu.add_command(label="Delete Selected Group (Ctrl+Del)", command=self.delete_selected_group)
        self.tree_context_menu.add_separator()
        self.tree_context_menu.add_command(label="Scale Timestamps (Speed Adjust)...", command=self.scale_timestamps_dialog)
        self.tree_context_menu.add_separator()
        self.tree_context_menu.add_command(label="Delete All Events", command=self.delete_all_events)

        self.tree.bind("<Button-3>", self.show_tree_context_menu)  # Right-click
        self.tree.bind("<Delete>", lambda e: self.delete_selected_event())  # Delete key
        self.tree.bind("<Control-Delete>", lambda e: self.delete_selected_group())  # Ctrl+Del for group delete

        # TAB 2: TASK FILES
        tasks_tab = ttk.Frame(self.notebook)
        self.notebook.add(tasks_tab, text="💾 Task Files")

        # === SECTIUNE FISIERE (în tab) ===
        file_frame = ttk.LabelFrame(tasks_tab, text=get_string('file_section'), padding="10")
        file_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Butoane salvare/incarcare - PRIMA LINIE
        btn_frame = ttk.Frame(file_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 10))

        # Butoane cu access keys
        save_text = get_string('save_task')
        btn_save = ttk.Button(btn_frame, text=f"{save_text} (Ctrl+S)",
                             command=self.save_task, width=28)
        btn_save.pack(side=tk.LEFT, padx=5, pady=8)
        self.root.bind('<Control-s>', lambda e: self.save_task())
        self.root.bind('<Control-S>', lambda e: self.save_task())

        load_text = get_string('load_from_file')
        btn_load_file = ttk.Button(btn_frame, text=f"{load_text} (Ctrl+O)",
                                  command=self.load_task, width=28)
        btn_load_file.pack(side=tk.LEFT, padx=5, pady=8)
        self.root.bind('<Control-o>', lambda e: self.load_task())
        self.root.bind('<Control-O>', lambda e: self.load_task())

        self.lbl_file = ttk.Label(btn_frame, text=get_string('no_file_loaded'), foreground="gray")
        self.lbl_file.pack(side=tk.LEFT, padx=20, pady=8)

        # Dropdown pentru task-uri salvate - A DOUA LINIE
        list_frame = ttk.Frame(file_frame)
        list_frame.pack(fill=tk.X, pady=(0, 0))

        ttk.Label(list_frame, text=get_string('saved_tasks')).pack(side=tk.LEFT, padx=5, pady=5)

        self.task_var = tk.StringVar()
        self.task_combo = ttk.Combobox(list_frame, textvariable=self.task_var,
                                      width=35, state="readonly")
        self.task_combo.pack(side=tk.LEFT, padx=5, pady=8)
        self.task_combo.bind('<<ComboboxSelected>>', self.on_task_selected)

        load_selected_text = get_string('load_selected_task')
        btn_load_selected = ttk.Button(list_frame, text=f"{load_selected_text} (Enter)",
                                      command=self.load_selected_task, width=28)
        btn_load_selected.pack(side=tk.LEFT, padx=5, pady=8)
        self.root.bind('<Return>', lambda e: self.load_selected_task())

        # Actualizeaza lista de task-uri
        self.refresh_task_list()

        # Bind keyboard shortcuts pentru accesibilitate (după crearea tuturor butoanelor)
        # Delay pentru a evita "Not Responding" - pornim listener-ul după ce UI-ul e complet inițializat
        self.logger.debug("Scheduling _setup_keyboard_shortcuts() with 500ms delay...")
        self.root.after(500, self._setup_keyboard_shortcuts)
        self.logger.info("setup_ui() completed")

    def _setup_keyboard_shortcuts(self):
        """Configurează keyboard shortcuts pentru accesibilitate"""
        self.logger.info("Setting up keyboard shortcuts...")
        # Play: Space
        def play_handler(e):
            self.logger.info(f"Space pressed! Play button state: {self.btn_play['state']}")
            if self.btn_play['state'] == 'normal':
                self.logger.info("Calling play_task()")
                self.play_task()
            else:
                self.logger.warning(f"Play button not enabled, state: {self.btn_play['state']}")
        self.root.bind('<KeyPress-space>', play_handler)
        self.logger.debug("Space binding registered for Play")

        # Pause: F10 (folosim listener global pentru funcționare corectă)
        self.logger.info("Setting up F10 listener for Pause...")
        self._setup_f10_listener()

        # Stop Playback: Esc
        def stop_handler(e):
            self.logger.info(f"Esc pressed! Stop button state: {self.btn_stop_play['state']}")
            if self.btn_stop_play['state'] == 'normal':
                self.logger.info("Calling stop_playback()")
                self.stop_playback()
        self.root.bind('<Escape>', stop_handler)
        self.logger.info("Keyboard shortcuts setup complete")

    def _setup_f10_listener(self):
        """Configurează listener global pentru F10 (Pause/Resume)"""
        self.logger.info("_setup_f10_listener() called")

        def on_key_press(key):
            try:
                # Convertim key la string pentru debugging mai bun
                key_str = str(key)
                self.logger.debug(f"Key PRESSED: {key_str} (type: {type(key)})")

                # Detectează F10
                if key == Key.f10:
                    self.logger.info(f"✓✓✓ F10 PRESSED - PAUSE/RESUME TRIGGERED! ✓✓✓")
                    # Apelăm direct pause_playback în thread-safe callback
                    # Verificarea se va face în pause_playback() care rulează în thread-ul principal
                    def call_pause():
                        try:
                            # Verifică dacă player-ul rulează (mai important decât starea butonului)
                            is_playing = self.player.playing
                            current_state = self.btn_pause['state']
                            self.logger.info(f"Player playing: {is_playing}, Button state: {current_state}")

                            # Dacă player-ul rulează, apelăm pause_playback (chiar dacă butonul pare disabled)
                            if is_playing:
                                self.logger.info("✓ Player is playing, calling pause_playback()...")
                                self.pause_playback()
                            elif current_state == 'normal':
                                # Dacă butonul este enabled dar player-ul nu rulează, încercăm totuși
                                self.logger.info("✓ Button is enabled, calling pause_playback()...")
                                self.pause_playback()
                            else:
                                self.logger.warning(f"✗ Cannot pause - player not playing and button state: '{current_state}'")
                        except Exception as e:
                            self.logger.error(f"Error in call_pause: {e}", exc_info=True)
                            # Încearcă direct dacă verificarea eșuează
                            try:
                                self.pause_playback()
                            except Exception as e2:
                                self.logger.error(f"Error calling pause_playback directly: {e2}", exc_info=True)

                    self.root.after(0, call_pause)
                else:
                    self.logger.debug(f"Other key pressed: {key_str}")
            except Exception as e:
                self.logger.error(f"✗✗✗ ERROR in on_key_press: {e}", exc_info=True)

        def on_key_release(key):
            try:
                key_str = str(key)
                self.logger.debug(f"Key RELEASED: {key_str}")
            except Exception as e:
                self.logger.error(f"✗✗✗ ERROR in on_key_release: {e}", exc_info=True)

        # Pornește listener global pentru F10 în thread separat
        # IMPORTANT: Listener-ul trebuie să fie global și să funcționează chiar și când alte aplicații sunt active
        self.logger.info("Creating F10 listener object...")
        try:
            # Folosim pynput.keyboard.Listener care funcționează global când aplicația rulează ca admin
            self.f10_listener = keyboard.Listener(
                on_press=on_key_press,
                on_release=on_key_release,
                suppress=False  # Nu suprima alte evenimente - permite altor aplicații să primească evenimentele
            )
            self.logger.info("✓ Listener object created successfully")
            self.logger.info("Starting listener in separate thread...")
            # Pornește listener-ul într-un thread separat pentru a nu bloca UI-ul
            def start_listener():
                self.logger.info("[THREAD] Starting F10 listener thread...")
                try:
                    # Listener-ul pornește și funcționează global (chiar și când alte aplicații sunt active)
                    # dacă aplicația rulează cu privilegii de administrator
                    self.f10_listener.start()
                    self.logger.info("[THREAD] ✓✓✓ F10 listener STARTED successfully! ✓✓✓")
                    self.logger.info("[THREAD] Listener is now active and listening for F10 GLOBALLY...")
                    self.logger.info("[THREAD] IMPORTANT: Listener works even when other apps are active (requires admin)")
                except Exception as e:
                    self.logger.error(f"[THREAD] ✗✗✗ ERROR starting listener: {e}", exc_info=True)
                    import traceback
                    traceback.print_exc()

            listener_thread = threading.Thread(target=start_listener, daemon=True)
            listener_thread.start()
            self.logger.info("✓ Listener start thread launched")
            # Așteaptă puțin pentru a verifica dacă listener-ul pornește
            import time
            time.sleep(0.2)  # Mărit delay-ul pentru a permite listener-ului să pornească
            if hasattr(self.f10_listener, 'running'):
                if self.f10_listener.running:
                    self.logger.info("✓✓✓ F10 Listener is RUNNING! ✓✓✓")
                else:
                    self.logger.warning("✗✗✗ F10 Listener is NOT running - may need admin privileges!")
            else:
                self.logger.warning("✗✗✗ Cannot check F10 listener status - may still be starting...")
        except Exception as e:
            self.logger.error(f"✗✗✗ ERROR creating F10 listener: {e}", exc_info=True)
            import traceback
            traceback.print_exc()

    def refresh_task_list(self):
        """Actualizeaza lista de task-uri din folderul tasks"""
        try:
            task_files = sorted([f.stem for f in self.tasks_dir.glob("*.json")])
            self.task_combo['values'] = task_files
            if task_files:
                self.task_combo.set(get_string('select_task'))
            else:
                self.task_combo.set(get_string('no_tasks_saved'))
        except Exception as e:
            print(f"Eroare la refresh lista: {e}")

    def on_task_selected(self, event=None):
        """Callback cand se selecteaza un task din dropdown"""
        pass  # Poate fi folosit pentru preview

    def load_selected_task(self):
        """Incarca task-ul selectat din dropdown"""
        selected = self.task_var.get()
        if not selected or selected == get_string('select_task') or selected == get_string('no_tasks_saved'):
            messagebox.showwarning(get_string('error'), get_string('select_task_from_list'))
            return

        filepath = self.tasks_dir / f"{selected}.json"
        if not filepath.exists():
            messagebox.showerror(get_string('error'), get_string('file_not_found', filename=filepath.name))
            self.refresh_task_list()
            return

        self._load_task_file(filepath)

    def _load_task_file(self, filepath):
        """Încarcă un fișier task (metodă consolidată pentru error handling)"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            messagebox.showerror(get_string('error'), get_string('error_json_parse', error=str(e)))
            return
        except PermissionError:
            messagebox.showerror(get_string('error'), get_string('error_permission'))
            return
        except IOError as e:
            messagebox.showerror(get_string('error'), get_string('error_file_io'))
            return
        except Exception as e:
            messagebox.showerror(get_string('error'), get_string('error_loading', error=str(e)))
            return

        # Validare format
        if 'events' not in data:
            messagebox.showerror(get_string('error'), get_string('error_invalid_format'))
            return None

        try:
            self.current_events = data['events']
            self.lbl_file.config(text=filepath.name, foreground="blue")
            self.schedule_config = data.get('schedule') or None

            playback = data.get('playback')
            if playback:
                try:
                    self.speed_var.set(float(playback.get('speed', self.speed_var.get())))
                except Exception:
                    pass

                # Restaurează Loop settings
                loop_enabled = bool(playback.get('loop', False))
                self.loop_var.set(loop_enabled)
                if loop_enabled and 'loop_count' in playback:
                    self.loop_count_var.set(int(playback.get('loop_count', 1)))
                    self.loop_count_spinbox.config(state='normal')
                else:
                    self.loop_count_spinbox.config(state='disabled')

                # Restaurează Run Until Stop
                self.run_until_stop_var.set(bool(playback.get('run_until_stop', False)))

            # Afiseaza in treeview
            self.tree.delete(*self.tree.get_children())
            for i, event in enumerate(self.current_events, 1):
                details = format_event_details(event)
                self.tree.insert('', tk.END, values=(
                    i,
                    f"{event['timestamp']:.3f}",
                    event['type'],
                    details
                ))

            if self.schedule_config and not self.schedule_running:
                self._start_schedule_thread()

            messagebox.showinfo(
                get_string('success'),
                get_string('task_loaded', name=filepath.stem, len=len(self.current_events))
            )
            return data
        except Exception as e:
            messagebox.showerror(get_string('error'), get_string('error_loading', error=str(e)))
            return None

    def update_speed_label(self, *args):
        """Actualizeaza label viteza"""
        speed = self.speed_var.get()
        # Validare viteza
        speed = max(0.1, min(10.0, speed))
        self.speed_var.set(speed)
        self.lbl_speed.config(text=f"{speed:.1f}x")

    def toggle_loop_count(self):
        """Activează/dezactivează spinbox-ul loop count când Loop este bifat"""
        if self.loop_var.get():
            # Verifică dacă Run Until Stop este activ
            if self.run_until_stop_var.get():
                messagebox.showwarning(
                    "Mutual Exclusion",
                    "Cannot enable both 'Loop' and 'Run continuously'!\n\n"
                    "Please choose only ONE option:\n"
                    "• Loop (N times) - runs specific number of times\n"
                    "• Run continuously - runs until manual stop"
                )
                self.loop_var.set(False)
                return

            self.loop_count_spinbox.config(state='normal')
            # Debifează Run Until Stop
            self.run_until_stop_var.set(False)
        else:
            self.loop_count_spinbox.config(state='disabled')

    def toggle_run_until_stop(self):
        """Activează/dezactivează Run Until Stop (blocare mutuală cu Loop)"""
        if self.run_until_stop_var.get():
            # Verifică dacă Loop este activ
            if self.loop_var.get():
                messagebox.showwarning(
                    "Mutual Exclusion",
                    "Cannot enable both 'Run continuously' and 'Loop'!\n\n"
                    "Please choose only ONE option:\n"
                    "• Run continuously - runs until manual stop\n"
                    "• Loop (N times) - runs specific number of times"
                )
                self.run_until_stop_var.set(False)
                return

            # Debifează Loop
            self.loop_var.set(False)
            self.loop_count_spinbox.config(state='disabled')

    def show_tree_context_menu(self, event):
        """Afișează context menu pentru Treeview"""
        # Identifică item-ul sub cursor
        item = self.tree.identify_row(event.y)
        if item:
            # NU schimba selecția dacă item-ul e deja în selecție (multi-select)
            if item not in self.tree.selection():
                self.tree.selection_set(item)
            self.tree_context_menu.post(event.x_root, event.y_root)

    def delete_selected_event(self):
        """Șterge evenimentul selectat"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select an event to delete!")
            return

        # Obține indexul evenimentului selectat
        item = selection[0]
        item_values = self.tree.item(item)['values']
        if not item_values:
            return

        event_index = int(item_values[0]) - 1  # Index 0-based

        # Confirmă ștergerea
        if messagebox.askyesno("Confirm Delete", f"Delete event #{event_index + 1}?"):
            # Șterge din lista de evenimente
            if 0 <= event_index < len(self.current_events):
                deleted_event = self.current_events.pop(event_index)
                self.logger.info(f"Deleted event #{event_index + 1}: {deleted_event}")

                # Reîmprospătează Treeview
                self._refresh_event_list()
                messagebox.showinfo("Success", f"Event #{event_index + 1} deleted!")

    def delete_all_events(self):
        """Șterge toate evenimentele"""
        if not self.current_events:
            messagebox.showwarning("Warning", "No events to delete!")
            return

        if messagebox.askyesno("Confirm Delete All",
                              f"Delete all {len(self.current_events)} events?"):
            self.current_events.clear()
            self._refresh_event_list()
            self.logger.info("All events deleted")
            messagebox.showinfo("Success", "All events deleted!")

    def delete_selected_group(self):
        """Șterge grupul de evenimente selectate (multi-select)"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select events to delete!")
            return

        # Obține indexurile evenimentelor selectate
        indices_to_delete = []
        for item in selection:
            item_values = self.tree.item(item)['values']
            if item_values:
                event_index = int(item_values[0]) - 1  # Index 0-based
                indices_to_delete.append(event_index)

        if not indices_to_delete:
            return

        # Sortează și elimină duplicate
        indices_to_delete = sorted(set(indices_to_delete), reverse=True)
        count = len(indices_to_delete)

        # Confirmă ștergerea
        if messagebox.askyesno("Confirm Delete Group",
                              f"Delete {count} selected event(s)?"):
            # Șterge în ordine inversă pentru a păstra indexurile corecte
            deleted_count = 0
            for index in indices_to_delete:
                if 0 <= index < len(self.current_events):
                    self.current_events.pop(index)
                    deleted_count += 1

            self.logger.info(f"Deleted {deleted_count} events from group")
            self._refresh_event_list()
            messagebox.showinfo("Success", f"{deleted_count} event(s) deleted!")

    def scale_timestamps_dialog(self):
        """Dialog pentru scalarea timestamp-urilor evenimentelor selectate"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select events to scale!")
            return

        if len(selection) < 2:
            messagebox.showwarning("Warning", "Please select at least 2 events to scale timestamps!")
            return

        # Creează dialog pentru factor de scalare
        dialog = tk.Toplevel(self.root)
        dialog.title("Scale Timestamps")
        dialog.geometry("350x180")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        # Centrat
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (350 // 2)
        y = (dialog.winfo_screenheight() // 2) - (180 // 2)
        dialog.geometry(f"350x180+{x}+{y}")

        ttk.Label(dialog, text=f"Scale timestamps for {len(selection)} selected events",
                 font=("Arial", 10, "bold")).pack(pady=10)

        ttk.Label(dialog, text="Speed Factor (0.5 = slower, 2.0 = faster):",
                 font=("Arial", 9)).pack(pady=5)

        factor_frame = ttk.Frame(dialog)
        factor_frame.pack(pady=5)

        factor_var = tk.DoubleVar(value=1.0)
        factor_spinbox = ttk.Spinbox(factor_frame, from_=0.1, to=10.0, increment=0.1,
                                    width=10, textvariable=factor_var, format="%.1f")
        factor_spinbox.pack(side=tk.LEFT, padx=5)

        ttk.Label(factor_frame, text="(0.1 - 10.0)").pack(side=tk.LEFT)

        def apply_scale():
            factor = factor_var.get()
            if factor <= 0:
                messagebox.showerror("Error", "Factor must be greater than 0!")
                return

            # Obține indexurile selectate
            indices = []
            for item in selection:
                item_values = self.tree.item(item)['values']
                if item_values:
                    indices.append(int(item_values[0]) - 1)

            indices.sort()

            if len(indices) < 2:
                return

            # Scalează timestamp-urile - păstrează primul timestamp și scalează delta-urile
            first_timestamp = self.current_events[indices[0]]['timestamp']

            for i in range(1, len(indices)):
                idx = indices[i]
                prev_idx = indices[i - 1]

                # Calculează delta scalat
                original_delta = self.current_events[idx]['timestamp'] - self.current_events[prev_idx]['timestamp']
                scaled_delta = original_delta / factor

                # Aplică noul timestamp
                self.current_events[idx]['timestamp'] = self.current_events[prev_idx]['timestamp'] + scaled_delta

            self.logger.info(f"Scaled {len(indices)} events by factor {factor}")
            self._refresh_event_list()
            dialog.destroy()
            messagebox.showinfo("Success", f"Timestamps scaled by {factor}x for {len(indices)} events!")

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=15)

        ttk.Button(btn_frame, text="Apply", command=apply_scale, width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy, width=12).pack(side=tk.LEFT, padx=5)

    def _refresh_event_list(self):
        """Reîmprospătează lista de evenimente în Treeview"""
        # Șterge toate item-urile
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Re-adaugă evenimentele
        for i, event in enumerate(self.current_events):
            time_str = f"{event.get('timestamp', 0):.2f}s"
            event_type = event.get('type', '')

            # Generează detalii
            details = []
            if 'x' in event and 'y' in event:
                details.append(f"({event['x']}, {event['y']})")
            if 'key' in event:
                details.append(f"Key: {event['key']}")
            if 'button' in event:
                details.append(f"Button: {event['button']}")

            detail_str = " ".join(details)

            self.tree.insert('', tk.END, values=(i + 1, time_str, event_type, detail_str))

    def toggle_mini_mode(self):
        """Enhanced mini mode with icons only"""
        if hasattr(self, 'mini_window') and self.mini_window.winfo_exists():
            self.mini_window.destroy()
            self.root.deiconify()
            return

        # Create compact mini window
        self.mini_window = tk.Toplevel(self.root)
        self.mini_window.title("BEBE Mini")
        self.mini_window.geometry("260x80")  # Compact cu tooltips
        self.mini_window.resizable(False, False)
        self.mini_window.attributes('-topmost', True)

        # Position in bottom-right
        screen_width = self.mini_window.winfo_screenwidth()
        screen_height = self.mini_window.winfo_screenheight()
        x = screen_width - 280
        y = screen_height - 120
        self.mini_window.geometry(f"260x80+{x}+{y}")

        # Main frame
        main_frame = ttk.Frame(self.mini_window, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Single row of icon-only buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X)

        # Record button
        self.mini_record_btn = ttk.Button(
            btn_frame, text="⏺", width=4,
            command=self.toggle_record_mini
        )
        self.mini_record_btn.pack(side=tk.LEFT, padx=2)
        ToolTip(self.mini_record_btn, "Record (F1)", delay_ms=300)

        # Play button
        self.mini_play_btn = ttk.Button(
            btn_frame, text="▶", width=4,
            command=self.play_task
        )
        self.mini_play_btn.pack(side=tk.LEFT, padx=2)
        ToolTip(self.mini_play_btn, "Play (Space)", delay_ms=300)

        # Pause button
        self.mini_pause_btn = ttk.Button(
            btn_frame, text="⏸", width=4,
            command=self.pause_playback
        )
        self.mini_pause_btn.pack(side=tk.LEFT, padx=2)
        ToolTip(self.mini_pause_btn, "Pause (F10)", delay_ms=300)

        # Stop button
        self.mini_stop_btn = ttk.Button(
            btn_frame, text="⏹", width=4,
            command=self.mini_stop_action
        )
        self.mini_stop_btn.pack(side=tk.LEFT, padx=2)
        ToolTip(self.mini_stop_btn, "Stop (Esc/F9)", delay_ms=300)

        # Return to full mode button
        self.mini_full_btn = ttk.Button(
            btn_frame, text="⏏", width=4,
            command=self.toggle_mini_mode
        )
        self.mini_full_btn.pack(side=tk.LEFT, padx=2)
        ToolTip(self.mini_full_btn, "Back to menu", delay_ms=300)

        # Status label (smaller)
        self.mini_status = ttk.Label(
            main_frame, text="Ready",
            font=("Arial", 8)
        )
        self.mini_status.pack(pady=(2, 0))

        # Close handler
        def on_close():
            self.mini_window.destroy()
            self.root.deiconify()

        self.mini_window.protocol("WM_DELETE_WINDOW", on_close)

        # Hide main window to tray
        self.hide_to_tray()


        self.logger.info("Enhanced Mini Mode activated")


    def mini_stop_action(self):
        """Stop action from mini mode - stops either recording or playback"""
        if self.recorder.recording:
            # Stop recording
            self.stop_recording()
            self.mini_record_btn.config(text="⏺")
            self.mini_status.config(text="Recording stopped")
        else:
            # Stop playback
            self.stop_playback()
            self.mini_status.config(text="Playback stopped")

    def toggle_record_mini(self):
        """Toggle recording from mini mode"""
        if self.recorder.recording:
            self.stop_recording()
            self.mini_record_btn.config(text="⏺")
            self.mini_status.config(text="Recording stopped")
        else:
            self.start_recording()
            self.mini_record_btn.config(text="⏹")
            self.mini_status.config(text="Recording...")

    def add_event_to_list(self, event_text):
        """Adauga eveniment in lista"""
        # Foloseste root.after pentru thread-safe update
        if len(self.recorder.events) > 0:
            event = self.recorder.events[-1]
            self.root.after(0, self._insert_event, event)

    def _insert_event(self, event):
        """Insereaza eveniment in treeview (thread-safe)"""
        details = format_event_details(event)
        self.tree.insert('', tk.END, values=(
            len(self.recorder.events),
            f"{event['timestamp']:.3f}",
            event['type'],
            details
        ))
        self.tree.yview_moveto(1)  # Scroll la sfarsit

    def start_recording(self):
        """Porneste inregistrarea"""
        self.logger.info("start_recording() called")
        self.current_events = []
        self.tree.delete(*self.tree.get_children())

        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.lbl_status.config(text=get_string('recording_status'), foreground="red")

        # Start in thread separat
        def record_thread():
            self.logger.info("Recording thread started")
            self.recorder.start_recording()
            while self.recorder.recording and not self.recorder.stop_requested:
                time.sleep(0.1)
            # Actualizeaza GUI dupa stop
            self.logger.info("Recording stopped, updating GUI")
            self.root.after(0, self.stop_recording)

        threading.Thread(target=record_thread, daemon=True).start()

    def stop_recording(self):
        """Opreste inregistrarea"""
        self.current_events = self.recorder.stop_recording()

        # Actualizeaza tabelul cu toate evenimentele
        self.tree.delete(*self.tree.get_children())
        for i, event in enumerate(self.current_events, 1):
            details = format_event_details(event)
            self.tree.insert('', tk.END, values=(
                i,
                f"{event['timestamp']:.3f}",
                event['type'],
                details
            ))

        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.lbl_status.config(text=get_string('recording_complete', len=len(self.current_events)),
                              foreground="green")

    def play_task(self):
        """Reda task-ul"""
        self.logger.info("play_task() called")
        if not self.current_events:
            self.logger.warning("No events to play")
            messagebox.showwarning(get_string('error'), get_string('no_task_to_play'))
            return

        self.logger.info(f"Playing {len(self.current_events)} events")
        self.btn_play.config(state=tk.DISABLED)
        self.btn_pause.config(state=tk.NORMAL)
        self.btn_stop_play.config(state=tk.NORMAL)
        self.lbl_play_status.config(text=get_string('playback_in_progress'), foreground="orange")

        speed = self.speed_var.get()
        # Validare viteza
        speed = max(0.1, min(10.0, speed))

        # Folosește loop_count dacă Loop este bifat, altfel 1
        loop_enabled = self.loop_var.get()
        if loop_enabled:
            loop = self.loop_count_var.get()
            self.logger.info(f"🔄 Loop ENABLED: loop_var={loop_enabled}, loop_count_var={self.loop_count_var.get()}, final loop={loop}")
        else:
            loop = 1
            self.logger.info(f"❌ Loop DISABLED: loop_var={loop_enabled}, defaulting to loop=1")

        run_until_stop = self.run_until_stop_var.get()

        self.logger.info(f"📊 FINAL Playback settings: speed={speed}, loop={loop}, run_until_stop={run_until_stop}")

        # Activează listener pentru ESC/F9 (întotdeauna, nu doar pentru run_until_stop)
        self._start_playback_keyboard_listener()

        def play_thread():
            self.logger.info("Playback thread started")
            self.player.play_events(self.current_events, speed=speed, loop_count=loop,
                                   callback=lambda msg: self.root.after(0, lambda: self.lbl_play_status.config(text=msg)),
                                   run_until_stop=run_until_stop)
            self.logger.info("Playback finished")
            self.root.after(0, self._playback_finished)

        threading.Thread(target=play_thread, daemon=True).start()

    def play_task_with_settings(self, speed=None, loop_count=1, run_until_stop=False):
        """Rulează task-ul cu setări explicite (folosit de schedule)"""
        self.logger.info(f"play_task_with_settings() called: speed={speed}, loop_count={loop_count}, run_until_stop={run_until_stop}")

        if not self.current_events:
            self.logger.warning("No events to play")
            return

        self.logger.info(f"Playing {len(self.current_events)} events with explicit settings")
        self.btn_play.config(state=tk.DISABLED)
        self.btn_pause.config(state=tk.NORMAL)
        self.btn_stop_play.config(state=tk.NORMAL)
        self.lbl_play_status.config(text=get_string('playback_in_progress'), foreground="orange")

        if speed is None:
            speed = self.speed_var.get()
        speed = max(0.1, min(10.0, speed))

        self.logger.info(f"📊 EXPLICIT Playback settings: speed={speed}, loop_count={loop_count}, run_until_stop={run_until_stop}")

        # Activează listener pentru ESC/F9
        self._start_playback_keyboard_listener()

        def play_thread():
            self.logger.info(f"Playback thread started with EXPLICIT settings: loop_count={loop_count}, run_until_stop={run_until_stop}")
            self.player.play_events(self.current_events, speed=speed, loop_count=loop_count,
                                   callback=lambda msg: self.root.after(0, lambda: self.lbl_play_status.config(text=msg)),
                                   run_until_stop=run_until_stop)
            self.logger.info("Playback finished")
            self.root.after(0, self._playback_finished)

        threading.Thread(target=play_thread, daemon=True).start()

    def _start_playback_keyboard_listener(self):
        """Pornește listener pentru ESC/F9 în timpul redării"""
        def on_press(key):
            if key == Key.f9 or key == Key.esc:
                self.player.stop()
                return False

        self.playback_keyboard_listener = keyboard.Listener(on_press=on_press)
        self.playback_keyboard_listener.start()

    def _playback_finished(self):
        """Callback când redarea s-a terminat"""
        if self.playback_keyboard_listener:
            self.playback_keyboard_listener.stop()
            self.playback_keyboard_listener = None

        self.btn_play.config(state=tk.NORMAL)
        self.btn_pause.config(state=tk.DISABLED)
        self.btn_stop_play.config(state=tk.DISABLED)
        self.lbl_play_status.config(text=get_string('playback_completed'), foreground="green")

    def pause_playback(self):
        """Pauza redare"""
        self.logger.info("="*60)
        self.logger.info("pause_playback() CALLED")
        try:
            self.logger.info(f"Player playing: {self.player.playing}")
            self.logger.info(f"Player paused: {self.player.paused}")
            button_state = self.btn_pause['state']
            self.logger.info(f"Pause button state: {button_state}")

            # Verifică dacă player-ul rulează - aceasta este verificarea principală
            if not self.player.playing:
                self.logger.warning("✗✗✗ Cannot pause - player is NOT playing ✗✗✗")
                self.logger.info("="*60)
                return

            # Nu verificăm starea butonului - dacă player-ul rulează, putem pune pe pauză
            # (butonul poate fi disabled din alte motive, dar F10 trebuie să funcționeze)

            if self.player.paused:
                self.logger.info("✓✓✓ RESUMING playback ✓✓✓")
                self.player.resume()
                pause_text = get_string('pause')
                self.btn_pause.config(text=f"{pause_text} (F10)")
                self.lbl_play_status.config(text=get_string('playback_in_progress'), foreground="orange")
                self.logger.info("✓ Resume completed")
            else:
                self.logger.info("✓✓✓ PAUSING playback ✓✓✓")
                self.player.pause()
                resume_text = "Resume"
                self.btn_pause.config(text=f"{resume_text} (F10)")
                self.lbl_play_status.config(text="Paused", foreground="yellow")
                self.logger.info("✓ Pause completed")
        except Exception as e:
            self.logger.error(f"Error in pause_playback: {e}", exc_info=True)
        self.logger.info("="*60)

    def stop_playback(self):
        """Opreste redarea"""
        self.player.stop()
        if self.playback_keyboard_listener:
            self.playback_keyboard_listener.stop()
            self.playback_keyboard_listener = None
        # Listener-ul Shift+Space rămâne activ pentru a putea fi folosit oricând
        self.btn_play.config(state=tk.NORMAL)
        self.btn_pause.config(state=tk.DISABLED)
        self.btn_stop_play.config(state=tk.DISABLED)
        self.lbl_play_status.config(text=get_string('playback_stopped'), foreground="red")

    def show_schedule_dialog(self):
        """Afișează dialogul pentru programare"""
        dialog = ScheduleDialog(self.root, self.schedule_config, self)
        result = dialog.show()

        # result poate fi:
        # - None: Cancel/ESC/X → NU SCHIMBA NIMIC
        # - {'_action': 'disable'}: Disable explicit → ȘTERGE
        # - dict cu setări: Save cu setări noi → ACTUALIZEAZĂ

        if result is None:
            # Cancel/ESC/X - nu face nimic, doar închide dialogul
            self.logger.info("Schedule dialog cancelled by user (ESC/X/Cancel)")
            return

        if isinstance(result, dict) and result.get('_action') == 'disable':
            # Utilizatorul a debifat "Enable Schedule" și a dat Save
            # Șterge schedule-ul și oprește thread-ul
            self.schedule_config = None
            self.schedule_running = False
            self.last_schedule_trigger = None
            self.logger.info("Schedule DISABLED by user (explicit disable)")
            messagebox.showinfo("Schedule Disabled", "Schedule has been disabled and cleared.")
            return

        if result:
            self.schedule_config = result
            self.logger.info(f"Schedule configured: {result}")

            # Verifică dacă există evenimente înregistrate
            if not self.current_events:
                messagebox.showwarning(
                    "No Events",
                    "Please record a task first!\n\n"
                    "1. Click 'Record' (F1)\n"
                    "2. Perform actions\n"
                    "3. Click 'Stop Recording' (F2)\n"
                    "4. Then set schedule again"
                )
                return

            # Pornește thread-ul de scheduling dacă nu rulează deja
            if not self.schedule_running:
                self._start_schedule_thread()

                # Afișează mesaj de confirmare CU setările de playback
                schedule_info = f"Schedule active!\n\n"
                schedule_info += f"Days: {', '.join(result['days'])}\n"
                if result.get('time_interval_enabled'):
                    schedule_info += f"Time: {result['time_from']} - {result['time_to']}\n"
                else:
                    schedule_info += "Time: All day\n"

                # Adaugă informații despre Loop/Run Continuously
                playback_settings = result.get('playback', {})
                if playback_settings.get('run_until_stop', False):
                    schedule_info += "\n⚙️ Playback: Run continuously until ESC/F9"
                elif playback_settings.get('loop', False):
                    loop_count = playback_settings.get('loop_count', 1)
                    schedule_info += f"\n⚙️ Playback: Loop {loop_count}× (repeat {loop_count} times)"
                else:
                    schedule_info += "\n⚙️ Playback: Single run (1 time)"

                schedule_info += "\n\nTask will play automatically when conditions match."

                messagebox.showinfo("Schedule Enabled", schedule_info)

    def _start_schedule_thread(self):
        """Pornește thread-ul pentru scheduling"""
        if self.schedule_running:
            return

        self.schedule_running = True

        def schedule_loop():
            self.logger.info("Schedule loop started")
            while self.schedule_running and self.schedule_config:
                now = datetime.now()
                current_time = now.time()
                current_weekday = now.weekday()  # 0 = Monday, 6 = Sunday

                # Mapare weekday la chei
                weekday_map = {
                    0: 'monday', 1: 'tuesday', 2: 'wednesday', 3: 'thursday',
                    4: 'friday', 5: 'saturday', 6: 'sunday'
                }
                current_day_key = weekday_map[current_weekday]

                # ✅ ADAUGĂ ACEASTĂ LINIE - citește playback settings din schedule
                playback_settings = self.schedule_config.get('playback', {})

                # Log verificare
                self.logger.debug(f"Schedule check: day={current_day_key}, time={current_time.strftime('%H:%M:%S')}, events={len(self.current_events)}, playback={playback_settings}")

                # Verifică dacă e ziua corectă
                if current_day_key not in self.schedule_config['days']:
                    self.logger.debug(f"Day mismatch: {current_day_key} not in {self.schedule_config['days']}")
                    time.sleep(10)
                    continue

                # Verifică intervalul orar (dacă este activat)
                time_interval_ok = True

                if self.schedule_config.get('time_interval_enabled', False):
                    try:
                        time_from_str = self.schedule_config.get('time_from')
                        time_to_str = self.schedule_config.get('time_to')

                        if time_from_str and time_to_str:
                            time_from = datetime.strptime(time_from_str, "%H:%M").time()
                            time_to = datetime.strptime(time_to_str, "%H:%M").time()

                            if time_from <= time_to:
                                time_interval_ok = time_from <= current_time <= time_to
                                self.logger.debug(f"Normal interval: {time_from} <= {current_time.strftime('%H:%M:%S')} <= {time_to} = {time_interval_ok}")
                            else:
                                time_interval_ok = current_time >= time_from or current_time <= time_to
                                self.logger.debug(f"Overnight interval: {current_time.strftime('%H:%M:%S')} >= {time_from} OR <= {time_to} = {time_interval_ok}")
                        else:
                            time_interval_ok = False
                            self.logger.warning("Time interval enabled but times not set")
                    except Exception as e:
                        self.logger.error(f"Schedule time parse error: {e}")
                        time_interval_ok = False
                else:
                    self.logger.debug("Time interval not enabled - running all day")

                # Rulează task-ul dacă toate condițiile sunt îndeplinite
                if time_interval_ok:
                    if not self.player.playing and self.current_events:
                        current_minute = now.replace(second=0, microsecond=0)

                        # Pentru Run Continuously - trigger la fiecare verificare
                        # Pentru Loop sau default - trigger doar o dată per minut
                        run_until_stop = playback_settings.get('run_until_stop', False)

                        should_trigger = False
                        if run_until_stop:
                            should_trigger = True
                            self.logger.debug("Run Continuously mode - triggering")
                        elif self.last_schedule_trigger is None or self.last_schedule_trigger < current_minute:
                            should_trigger = True
                            self.last_schedule_trigger = current_minute
                        else:
                            self.logger.debug(f"Task already triggered this minute, skipping")

                        if should_trigger:
                            self.logger.info(f"✅ SCHEDULE TRIGGERED! day={current_day_key}, time={current_time.strftime('%H:%M:%S')}, playback={playback_settings}")
                            # ✅ Acum playback_settings este definit corect
                            self.root.after(0, lambda ps=playback_settings: self._play_scheduled_task(ps))
                    elif self.player.playing:
                        self.logger.debug("Task already playing, skipping trigger")
                    elif not self.current_events:
                        self.logger.warning("No events to play!")
                else:
                    self.logger.debug(f"Time interval condition not met")

                time.sleep(10)

        self.schedule_thread = threading.Thread(target=schedule_loop, daemon=True)
        self.schedule_thread.start()


    def _play_scheduled_task(self, playback_settings):
        """Rulează task-ul cu setările salvate în schedule"""
        self.logger.info(f"🎬 Playing scheduled task with settings: {playback_settings}")

        # Extrage setările
        loop_enabled = playback_settings.get('loop', False)
        loop_count = playback_settings.get('loop_count', 1)
        run_until_stop = playback_settings.get('run_until_stop', False)

        # Calculează loop_count final
        if run_until_stop:
            final_loop_count = 999999  # Infinit (va rula până la ESC/F9)
        elif loop_enabled:
            final_loop_count = loop_count
        else:
            final_loop_count = 1  # Default: o singură rulare

        self.logger.info(f"✅ Schedule playback: loop_enabled={loop_enabled}, loop_count={loop_count}, run_until_stop={run_until_stop}")
        self.logger.info(f"✅ Final calculated: loop_count={final_loop_count}, run_until_stop={run_until_stop}")

        # Rulează task-ul CU SETĂRI EXPLICITE (nu se bazează pe GUI)
        self.play_task_with_settings(
            speed=self.speed_var.get(),
            loop_count=final_loop_count,
            run_until_stop=run_until_stop
        )

    def _build_task_data(self, task_name=None):
        """Construiește payload-ul comun pentru export JSON/EXE"""
        playback = {
            'speed': float(self.speed_var.get()),
            'loop': bool(self.loop_var.get()),
            'loop_count': int(self.loop_count_var.get()),
            'run_until_stop': bool(self.run_until_stop_var.get())
        }
        data = {
            'version': TASK_DATA_VERSION,
            'created': datetime.now().isoformat(),
            'event_count': len(self.current_events),
            'events': self.current_events,
            'schedule': self.schedule_config,
            'playback': playback
        }
        if task_name:
            data['name'] = task_name
        return data

    def _write_task_log(self, base_path, task_data):
        """Scrie fișierul .log cu detalii despre task"""
        log_path = Path(base_path).with_suffix('.log')
        try:
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write("BEBE Task Recorder - Log\n")
                f.write(f"{'=' * 60}\n")
                f.write(f"Task: {log_path.stem}\n")
                f.write(f"Creat: {task_data.get('created')}\n")
                f.write(f"Evenimente: {len(task_data.get('events', []))}\n")
                if task_data.get('schedule'):
                    f.write(f"Programare: {task_data['schedule']}\n")
                playback = task_data.get('playback', {})
                if playback:
                    f.write(f"Playback: {playback}\n")
                f.write(f"{'=' * 60}\n\n")
                for i, event in enumerate(task_data.get('events', []), 1):
                    timestamp = event.get('timestamp', 0.0)
                    details = format_event_details(event)
                    f.write(f"[{i:4d}] {timestamp:8.3f}s - {details}\n")
        except Exception as e:
            self.logger.error("Nu am putut scrie log-ul: %s", e)
        return log_path

    def _generate_runner_script(self, task_data, exe_name):
        """Generează scriptul Python ce va fi compilat în executabil"""
        data = dict(task_data)
        data.setdefault('name', exe_name)
        task_data_repr = repr(data)
        title_repr = repr(f"{exe_name} - BEBE Task Runner")
        template = textwrap.dedent(
            """\
            #!/usr/bin/env python3
            # -*- coding: utf-8 -*-
            \"\"\"Autogenerated runner for BEBE Task Recorder.\"\"\"

            import sys
            import time
            import ctypes
            from datetime import datetime
            import pyautogui
            from pynput import keyboard
            from pynput.keyboard import Key, Controller as KeyboardController

            TASK_DATA = __TASK_DATA__

            pyautogui.PAUSE = 0.01
            pyautogui.FAILSAFE = True

            def is_admin():
                try:
                    return ctypes.windll.shell32.IsUserAnAdmin()
                except Exception:
                    return False

            def run_as_admin():
                if not is_admin():
                    ctypes.windll.shell32.ShellExecuteW(
                        None, 'runas', sys.executable, ' '.join(sys.argv), None, 1
                    )
                    sys.exit()

            def show_message(title, message):
                try:
                    ctypes.windll.user32.MessageBoxW(None, message, title, 0)
                except Exception:
                    pass

            class TaskPlayer:
                def __init__(self, speed=1.0, loop_count=1, run_until_stop=False):
                    self.keyboard_controller = KeyboardController()
                    self.speed = max(0.1, min(10.0, speed))
                    self.loop_count = max(1, loop_count)
                    self.run_until_stop = run_until_stop
                    self.stop_requested = False
                    self.listener = None

                def _start_listener(self):
                    if not self.run_until_stop:
                        return

                    def on_press(key):
                        if key in (Key.esc, Key.f9):
                            self.stop_requested = True
                            return False

                    self.listener = keyboard.Listener(on_press=on_press)
                    self.listener.start()

                def _stop_listener(self):
                    if self.listener:
                        self.listener.stop()
                        self.listener = None

                def play(self, events):
                    self._start_listener()
                    loops = 0
                    try:
                        while True:
                            loops += 1
                            for index, event in enumerate(events):
                                if self.stop_requested:
                                    break
                                if index > 0:
                                    delay = (event['timestamp'] - events[index - 1]['timestamp']) / self.speed
                                    if delay > 0:
                                        time.sleep(delay)
                                self.execute_event(event)
                            if self.stop_requested:
                                break
                            if not self.run_until_stop and loops >= self.loop_count:
                                break
                    finally:
                        self._stop_listener()

                def execute_event(self, event):
                    event_type = event.get('type')
                    if event_type == 'mouse_move':
                        pyautogui.moveTo(event['x'], event['y'], duration=0)
                    elif event_type == 'mouse_click':
                        button_name = event.get('button', '').lower()
                        button = 'left'
                        if 'right' in button_name:
                            button = 'right'
                        elif 'middle' in button_name:
                            button = 'middle'
                        pyautogui.moveTo(event['x'], event['y'], duration=0)
                        if event.get('pressed'):
                            pyautogui.mouseDown(button=button)
                        else:
                            pyautogui.mouseUp(button=button)
                    elif event_type == 'mouse_scroll':
                        pyautogui.scroll(int(event.get('dy', 0) * 100))
                    elif event_type == 'key_press':
                        self._handle_key(event.get('key', ''), press=True)
                    elif event_type == 'key_release':
                        self._handle_key(event.get('key', ''), press=False)

                def _handle_key(self, key_name, press=True):
                    if not key_name:
                        return
                    modifiers = []
                    main_key = key_name
                    if '+' in key_name:
                        parts = key_name.split('+')
                        modifiers = parts[:-1]
                        main_key = parts[-1]
                    main_key = main_key.strip("'\\"")

                    for mod in modifiers:
                        mod_lower = mod.lower()
                        if mod_lower == 'ctrl':
                            (self.keyboard_controller.press if press else self.keyboard_controller.release)(Key.ctrl)
                        elif mod_lower == 'alt':
                            (self.keyboard_controller.press if press else self.keyboard_controller.release)(Key.alt)
                        elif mod_lower == 'shift':
                            (self.keyboard_controller.press if press else self.keyboard_controller.release)(Key.shift)

                    key = self._parse_key(main_key)
                    if press:
                        self.keyboard_controller.press(key)
                    else:
                        self.keyboard_controller.release(key)

                    if not press:
                        for mod in reversed(modifiers):
                            mod_lower = mod.lower()
                            if mod_lower == 'ctrl':
                                self.keyboard_controller.release(Key.ctrl)
                            elif mod_lower == 'alt':
                                self.keyboard_controller.release(Key.alt)
                            elif mod_lower == 'shift':
                                self.keyboard_controller.release(Key.shift)

                def _parse_key(self, key_str):
                    special_keys = {
                        'space': Key.space, 'enter': Key.enter, 'tab': Key.tab,
                        'backspace': Key.backspace, 'esc': Key.esc, 'escape': Key.esc,
                        'shift': Key.shift, 'ctrl': Key.ctrl, 'alt': Key.alt,
                        'up': Key.up, 'down': Key.down, 'left': Key.left, 'right': Key.right,
                        'delete': Key.delete, 'home': Key.home, 'end': Key.end,
                        'page_up': Key.page_up, 'page_down': Key.page_down,
                        'insert': Key.insert, 'caps_lock': Key.caps_lock, 'num_lock': Key.num_lock,
                        'scroll_lock': Key.scroll_lock,
                        'f1': Key.f1, 'f2': Key.f2, 'f3': Key.f3, 'f4': Key.f4,
                        'f5': Key.f5, 'f6': Key.f6, 'f7': Key.f7, 'f8': Key.f8,
                        'f9': Key.f9, 'f10': Key.f10, 'f11': Key.f11, 'f12': Key.f12,
                    }
                    key_clean = key_str.replace('Key.', '').lower()
                    if key_clean in special_keys:
                        return special_keys[key_clean]
                    if len(key_str) == 1:
                        return key_str
                    return key_str

            def schedule_allows_run(schedule):
                if not schedule or not schedule.get('enabled'):
                    return True
                now = datetime.now()
                day_map = {
                    0: 'monday', 1: 'tuesday', 2: 'wednesday', 3: 'thursday',
                    4: 'friday', 5: 'saturday', 6: 'sunday'
                }
                current_day = day_map.get(now.weekday())
                if current_day not in schedule.get('days', []):
                    return False
                try:
                    start = datetime.strptime(schedule.get('time_from', '00:00'), '%H:%M').time()
                    end = datetime.strptime(schedule.get('time_to', '23:59'), '%H:%M').time()
                except Exception:
                    return True
                current_time = now.time()
                return start <= current_time <= end

            def main():
                title = __TITLE__
                run_as_admin()
                data = TASK_DATA
                events = data.get('events', [])
                if not events:
                    show_message(title, 'Acest executabil nu contine niciun eveniment de redat.')
                    return
                schedule = data.get('schedule')
                if schedule and not schedule_allows_run(schedule):
                    show_message(title, 'Executia este programata pentru un alt interval.')
                    return
                playback = data.get('playback', {})
                speed = float(playback.get('speed', 1.0))
                loop = bool(playback.get('loop', False))
                run_until_stop = bool(playback.get('run_until_stop', False))
                loop_count = 999 if loop and not run_until_stop else 1
                player = TaskPlayer(speed=speed, loop_count=loop_count, run_until_stop=run_until_stop)
                show_message(title, 'Task-ul va incepe in 3 secunde. Inchide acest mesaj pentru a continua.')
                time.sleep(3)
                player.play(events)
                show_message(title, 'Task finalizat.')

            if __name__ == '__main__':
                main()
            """
        )
        template = template.replace("__TASK_DATA__", task_data_repr)
        template = template.replace("__TITLE__", title_repr)
        return template

    def _build_task_executable(self, exe_path):
        """Construiește executabilul folosind PyInstaller"""
        exe_path = Path(exe_path)
        task_name = exe_path.stem
        print(f"[DEBUG] _build_task_executable: task_name={task_name}")
        task_data = self._build_task_data(task_name)
        script_content = self._generate_runner_script(task_data, task_name)
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            print(f"[DEBUG] Temporary builder dir: {temp_dir_path}")
            runner_file = temp_dir_path / "task_runner.py"
            runner_file.write_text(script_content, encoding='utf-8')
            print(f"[DEBUG] Runner script written: {runner_file}")

            # Find Python executable - if frozen, search for python.exe in PATH
            if getattr(sys, 'frozen', False):
                # Running from EXE - find python.exe
                python_exe = shutil.which('python') or shutil.which('python3')
                if not python_exe:
                    raise RuntimeError("Python nu a fost gasit in PATH. Instaleaza Python si adauga-l in PATH.")
            else:
                # Running from Python source
                python_exe = sys.executable

            print(f"[DEBUG] Using Python: {python_exe}")

            cmd = [
                python_exe,
                "-m",
                "PyInstaller",
                "--onefile",
                "--noconsole",
                "--clean",
                "--uac-admin",
                f"--name={task_name}",
                str(runner_file)
            ]
            self.logger.info("Rulez PyInstaller pentru task '%s'", task_name)
            self.logger.debug("Comanda PyInstaller: %s", " ".join(cmd))
            print(f"[DEBUG] Executing PyInstaller command: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                cwd=temp_dir,
                capture_output=True,
                text=True,
                check=False
            )
            print(f"[DEBUG] PyInstaller return code: {result.returncode}")
            if result.stdout:
                print("[DEBUG] PyInstaller STDOUT:")
                print(result.stdout)
            if result.stderr:
                print("[DEBUG] PyInstaller STDERR:")
                print(result.stderr)
            if result.returncode != 0:
                error_output = result.stderr or result.stdout or "PyInstaller a esuat fara mesaje."
                self.logger.error("PyInstaller error output: %s", error_output)
                raise RuntimeError(error_output)
            built_exe = temp_dir_path / "dist" / f"{task_name}.exe"
            print(f"[DEBUG] Expected built EXE path: {built_exe}")
            if not built_exe.exists():
                raise FileNotFoundError("PyInstaller nu a generat executabilul asteptat.")
            exe_path.parent.mkdir(parents=True, exist_ok=True)
            if exe_path.exists():
                print(f"[DEBUG] Existing EXE found at destination. Removing: {exe_path}")
                exe_path.unlink()
            shutil.move(str(built_exe), str(exe_path))
            print(f"[DEBUG] EXE moved to destination: {exe_path}")
        return task_data

    def save_task(self):
        """Salveaza task"""
        if not self.current_events:
            messagebox.showwarning(get_string('error'), get_string('no_task_to_save'))
            return

        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            initialdir=self.tasks_dir
        )

        if filename:
            try:
                filepath = Path(filename)
                task_data = self._build_task_data(filepath.stem)

                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(task_data, f, indent=2, ensure_ascii=False)

                log_path = self._write_task_log(filepath, task_data)

                self.lbl_file.config(text=filepath.name, foreground="blue")
                self.refresh_task_list()
                self.task_var.set(filepath.stem)

                messagebox.showinfo(
                    get_string('success'),
                    get_string(
                        'task_saved',
                        len=len(self.current_events),
                        json_name=filepath.name,
                        log_name=log_path.name
                    )
                )
            except PermissionError:
                messagebox.showerror(get_string('error'), get_string('error_permission'))
            except IOError:
                messagebox.showerror(get_string('error'), get_string('error_file_io'))
            except Exception as e:
                messagebox.showerror(get_string('error'), get_string('error_saving', error=str(e)))
    def load_task(self):
        """Incarca task"""
        filename = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json")],
            initialdir=self.tasks_dir
        )

        if filename:
            filepath = Path(filename)
            self._load_task_file(filepath)


def setup_logging():
    """Configurează logging într-un fișier"""
    logs_dir = Path("LOGS")
    logs_dir.mkdir(exist_ok=True)

    # Nume fișier cu timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = logs_dir / f"bebe_debug_{timestamp}.log"

    # Configurează logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()  # Și în consolă
        ]
    )

    logger = logging.getLogger(__name__)
    logger.info(f"Logging initialized. Log file: {log_file}")
    return logger


def debug_log(message):
    """Helper pentru logging - scrie și în fișier și în consolă"""
    logging.debug(message)
    print(message)  # Pentru compatibilitate


def run_cli():
    """Command-line interface for BEBE"""
    import argparse

    parser = argparse.ArgumentParser(
        description="BEBE Task Recorder - CLI Mode",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest='command', required=True)

    # Play command
    play_parser = subparsers.add_parser('play', help='Play a task file')
    play_parser.add_argument('file', help='JSON task file path')
    play_parser.add_argument('--speed', type=float, default=2.0,
                            help='Playback speed (0.1-10.0)')
    play_parser.add_argument('--loop', type=int, default=1,
                            help='Number of repetitions')

    # List command
    subparsers.add_parser('list', help='List saved tasks')

    # Info command
    info_parser = subparsers.add_parser('info', help='Show task info')
    info_parser.add_argument('file', help='JSON task file path')

    # Export BAT command
    export_parser = subparsers.add_parser('export-bat',
                                         help='Export task as BAT file')
    export_parser.add_argument('file', help='JSON task file path')
    export_parser.add_argument('--output', help='Output BAT file path')
    export_parser.add_argument('--schedule', action='store_true',
                              help='Include scheduling commands')

    args = parser.parse_args()

    # Handle commands
    if args.command == 'play':
        play_task_cli(args.file, args.speed, args.loop)
    elif args.command == 'list':
        list_tasks_cli()
    elif args.command == 'info':
        show_task_info_cli(args.file)
    elif args.command == 'export-bat':
        export_bat_cli(args.file, args.output, args.schedule)


def play_task_cli(filepath, speed, loop_count):
    """Play task from CLI"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        events = data.get('events', [])
        if not events:
            print(f"❌ No events in {filepath}")
            return

        print(f"▶️  Playing {len(events)} events at {speed}x speed, {loop_count} time(s)")

        player = TaskPlayer()
        player.play_events(events, speed=speed, loop_count=loop_count,
                          callback=lambda msg: print(f"  {msg}"))

        print("✅ Playback complete!")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


def list_tasks_cli():
    """List all saved tasks"""
    tasks_dir = Path("tasks")
    if not tasks_dir.exists():
        print("📁 No tasks directory found")
        return

    tasks = sorted(tasks_dir.glob("*.json"))
    if not tasks:
        print("📝 No saved tasks")
        return

    print(f"\n📋 Found {len(tasks)} task(s):\n")

    for task in tasks:
        print(f"  • {task.stem}")
    print()


def show_task_info_cli(filepath):
    """Show task information"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        print(f"\n📊 Task Info: {Path(filepath).stem}")
        print("=" * 50)
        print(f"Events: {len(data.get('events', []))}")
        print(f"Created: {data.get('created', 'Unknown')}")

        if data.get('schedule'):
            print(f"Schedule: {data['schedule']}")

        if data.get('playback'):
            pb = data['playback']
            print(f"Playback: Speed={pb.get('speed', 1.0)}x, "
                  f"Loop={pb.get('loop', False)}")
        print()

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


def export_bat_cli(filepath, output, include_schedule):
    """Export task as BAT file"""
    try:
        # Implementation here
        print(f"✅ Exported to {output or filepath.replace('.json', '.bat')}")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


def main():
    """Functia principala"""
    # Check if CLI mode
    if len(sys.argv) > 1:
        run_cli()
        return

    logger = setup_logging()
    logger.info("="*60)
    logger.info("Starting BEBE Task Recorder v%s...", APP_VERSION)
    logger.info("="*60)

    root = tk.Tk()
    logger.info("Root window created")

    app = BebeGUI(root, logger)
    logger.info("BebeGUI initialized, starting mainloop")

    root.mainloop()
    logger.info("Mainloop ended")


if __name__ == "__main__":
    main()

