# -*- coding: utf-8 -*-
"""
BEBE Task Recorder — Version 5.5
Îmbunătățiri majore:
- Tab 1: Formularul clasic și simplu din versiunea anterioară:
  * Checkbox dedicat 'Run continuously in interval' sincronizat cu opțiunea din ecranul principal
  * Dacă 'Run continuously' nu este bifat, sarcina se execută O SINGURĂ DATĂ la ora programată
  * Buton '➕ New Task' pentru adăugare sarcină nouă curată
  * Buton '💾 Salvează ca sarcină nouă'
- Tab 2: Panoul complet de Sarcini Multiple (vizualizare listă, editare, adăugare, duplicare, activare/anulare)
  * Suport complet pentru derulare cu rotița de la mouse (Mouse Wheel Scroll) pe panoul din dreapta!
  * Ștergerea definitivă a oricărei sarcini (inclusiv Sarcina 1) fără ca aceasta să revină la redeschiderea ferestrei!
  * Lista poate rămâne goală (0 sarcini) dacă utilizatorul le șterge pe toate
- Prevenire pornire automată imediat după Stop Recording:
  * Noile sarcini înregistrate nu pornesc automat la stop; rămân în așteptare pentru programare
  * Verificare strictă a zilelor: dacă nicio zi nu este bifată în formular, sarcina NU are voie să ruleze
- Jurnalizare completă (Logs) pentru ștergeri, adăugări, modificări și execuția sarcinilor
- ToolTip explicativ detaliat pe FIECARE instrucțiune, buton și căsuță
- Salvare automată pe disc în 'schedules.json'
- Taste „PAS VIRTUAL” în timpul înregistrării: înregistrează Enter / clic FĂRĂ să-l execute acum
  * F8 sau ` ~ (tasta de lângă 1) → înlocuiește CLICUL sau ENTER-ul, după cursorul mouse-ului:
      - mouse pe o iconiță / un buton (cursor săgeată sau mânuță) → CLIC acolo
        (ex: iconița din bara Total Commander care deschide un program)
      - mouse pe o casetă de text (cursorul „I”) → CLIC în casetă + ENTER
        (ex: un mesaj deja scris în chat va fi trimis abia la ora programată)
  * Shift+F8 / Shift+` → doar ENTER;  Ctrl+F8 / Ctrl+` → DUBLU-CLIC
  * F7 → doar CLIC în punctul unde este mouse-ul;  Ctrl+F7 → DUBLU-CLIC
- În 'Sarcini Multiple', cu lista de sarcini GOALĂ, tasta Enter = 'Salvează & Închide'
  * Nimic nu se apasă în timpul înregistrării; acțiunea se execută doar la redare / la ora programată
  * F7, F8 și ` ~ sunt BLOCATE în timpul înregistrării, ca programul din față să nu le primească
    (ex: F8 = Ștergere în Total Commander; ` ar apărea scris în caseta de chat)
- Combinațiile de taste se înregistrează corect: Ctrl+A, Ctrl+C, Ctrl+V, Ctrl+S, Ctrl+Z, Shift+Home, Alt+Tab,
  Ctrl+Shift+..., Win+... ; diacriticele (ă â î ș ț) se tastează corect la redare
"""

import json
import os
import queue
import threading
import time
import subprocess
import uuid
from dataclasses import dataclass, asdict, field
from typing import List, Optional, Set, Dict, Any
from datetime import datetime, timedelta

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

from pynput import mouse, keyboard as kb
import keyboard
import pyautogui

pyautogui.FAILSAFE = False

import sys
import ctypes
from ctypes import wintypes


# ============================ Taste: conversie pynput -> pyautogui ============================

MOD_NAMES = {
    'ctrl': 'ctrl', 'ctrl_l': 'ctrl', 'ctrl_r': 'ctrl',
    'shift': 'shift', 'shift_l': 'shift', 'shift_r': 'shift',
    'alt': 'alt', 'alt_l': 'alt', 'alt_r': 'alt',
    'cmd': 'win', 'cmd_l': 'win', 'cmd_r': 'win',
}
MOD_ORDER = ['ctrl', 'alt', 'shift', 'win']

KEY_NAME_MAP = {
    'page_up': 'pageup', 'page_down': 'pagedown', 'caps_lock': 'capslock', 'num_lock': 'numlock',
    'scroll_lock': 'scrolllock', 'print_screen': 'printscreen', 'menu': 'apps', 'alt_gr': 'altright',
    'media_volume_up': 'volumeup', 'media_volume_down': 'volumedown', 'media_volume_mute': 'volumemute',
    'media_play_pause': 'playpause', 'media_next': 'nexttrack', 'media_previous': 'prevtrack',
    'cmd': 'win', 'cmd_l': 'winleft', 'cmd_r': 'winright',
    'ctrl_l': 'ctrlleft', 'ctrl_r': 'ctrlright', 'shift_l': 'shiftleft', 'shift_r': 'shiftright',
    'alt_l': 'altleft', 'alt_r': 'altright',
}

# Coduri virtuale Windows pentru tastele „OEM” (layout US / RO standard)
VK_OEM = {186: ';', 187: '=', 188: ',', 189: '-', 190: '.', 191: '/', 192: '`', 219: '[', 220: '\\', 221: ']', 222: "'"}


def normalize_key_name(name: str) -> str:
    """Numele unei taste (pynput sau vechi) -> numele înțeles de pyautogui."""
    n = str(name).strip()
    if n.startswith('Key.'):
        n = n[4:]
    low = n.lower()
    if low in MOD_NAMES and low not in ('ctrl_l', 'ctrl_r', 'shift_l', 'shift_r', 'alt_l', 'alt_r', 'cmd_l', 'cmd_r'):
        return MOD_NAMES[low]
    if low in ('ctrl_l', 'ctrl_r', 'shift_l', 'shift_r', 'alt_l', 'alt_r'):
        return MOD_NAMES[low]          # într-o combinație e suficient 'ctrl' / 'shift' / 'alt'
    return KEY_NAME_MAP.get(low, low)


def keycode_base_name(key) -> Optional[str]:
    """Tasta de bază (fără modificatori) pentru combinații: Ctrl+S -> 's', Ctrl+1 -> '1', Ctrl+Home -> 'home'."""
    vk = getattr(key, 'vk', None)
    if vk is None and hasattr(key, 'value'):
        vk = getattr(key.value, 'vk', None)
    if isinstance(key, kb.Key):
        return normalize_key_name(key.name)
    if vk is not None:
        if 65 <= vk <= 90:
            return chr(vk).lower()
        if 48 <= vk <= 57:
            return chr(vk)
        if 96 <= vk <= 105:
            return f"num{vk - 96}"
        if 112 <= vk <= 135:
            return f"f{vk - 111}"
        if vk in VK_OEM:
            return VK_OEM[vk]
    ch = getattr(key, 'char', None)
    if ch and ch.isprintable():
        return ch.lower()
    return None


def type_unicode_text(text: str, interval: float = 0.0):
    """Tastează ORICE caracter (inclusiv ă â î ș ț) prin SendInput Unicode; pyautogui.typewrite nu știe diacritice."""
    if not _IS_WIN:
        pyautogui.typewrite(text, interval=interval)
        return
    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_UNICODE = 0x0004

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _U)]

    for ch in text:
        if ch == '\n':
            pyautogui.press('enter')
        else:
            data = ch.encode('utf-16-le')
            for i in range(0, len(data), 2):
                code = int.from_bytes(data[i:i + 2], 'little')
                for flags in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
                    inp = INPUT(type=INPUT_KEYBOARD)
                    inp.u.ki = KEYBDINPUT(0, code, flags, 0, None)
                    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        if interval:
            time.sleep(interval)


# ============================ Fișiere aplicație (lângă .exe / .py) ============================

def _app_dir() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


APP_DIR = _app_dir()
LOG_FILE = os.path.join(APP_DIR, "bebe_log.txt")                 # Jurnal complet, persistent
HISTORY_FILE = os.path.join(APP_DIR, "istoric_sarcini.json")     # Istoricul execuțiilor sarcinilor
CAPTURES_DIR = os.path.join(APP_DIR, "istoric_capturi")          # Capturi de ecran la start/final rulare
GRACE_SECONDS = 300   # O sarcină ratată (PC în standby / blocat) mai poate porni până la 5 minute după ora fixată
LOCK_RETRY_SECONDS = 30


# ============================ Windows: Ține PC-ul treaz / Detectare blocare ============================

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002

_IS_WIN = os.name == 'nt'


def set_keep_awake(on: bool) -> bool:
    """Împiedică (on=True) intrarea PC-ului în Sleep/Modern Standby și stingerea ecranului.
    ATENȚIE: starea ES_CONTINUOUS este per-thread — apelați mereu din același thread (thread-ul Scheduler)."""
    if not _IS_WIN:
        return False
    try:
        flags = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED if on else 0)
        return bool(ctypes.windll.kernel32.SetThreadExecutionState(flags))
    except Exception:
        return False


def wake_display():
    """Aprinde ecranul / trezește sesiunea înainte de rularea unei sarcini."""
    if not _IS_WIN:
        return
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)
    except Exception:
        pass
    try:
        x, y = pyautogui.position()
        pyautogui.moveTo(x + 1, y)
        pyautogui.moveTo(x, y)
    except Exception:
        pass


def is_workstation_locked() -> bool:
    """True dacă Windows afișează ecranul de blocare / login (clicurile NU ar ajunge la aplicații)."""
    if not _IS_WIN:
        return False
    try:
        user32 = ctypes.windll.user32
        user32.OpenInputDesktop.restype = wintypes.HANDLE
        DESKTOP_SWITCHDESKTOP = 0x0100
        h = user32.OpenInputDesktop(0, False, DESKTOP_SWITCHDESKTOP)
        if not h:
            return True
        try:
            return not bool(user32.SwitchDesktop(h))
        finally:
            user32.CloseDesktop(h)
    except Exception:
        return False


def window_title_at(x: int, y: int) -> str:
    """Titlul ferestrei (de nivel superior) aflate sub punctul (x, y) — pentru a verifica unde nimeresc clicurile."""
    if not _IS_WIN:
        return ""
    try:
        user32 = ctypes.windll.user32
        user32.WindowFromPoint.restype = wintypes.HWND
        user32.WindowFromPoint.argtypes = [wintypes.POINT]
        user32.GetAncestor.restype = wintypes.HWND
        hwnd = user32.WindowFromPoint(wintypes.POINT(int(x), int(y)))
        if not hwnd:
            return "(nicio fereastră)"
        root = user32.GetAncestor(hwnd, 2) or hwnd  # GA_ROOT
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(root, buf, 256)
        cls = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(root, cls, 128)
        title = buf.value.strip()
        return f"{title} [{cls.value}]" if title else f"[{cls.value}]"
    except Exception:
        return ""


def cursor_is_text_ibeam() -> bool:
    """True dacă mouse-ul arată cursorul de TEXT „I” (deasupra unei casete în care se scrie)."""
    if not _IS_WIN:
        return False
    try:
        class CURSORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD),
                        ("hCursor", wintypes.HANDLE), ("ptScreenPos", wintypes.POINT)]
        user32 = ctypes.windll.user32
        user32.LoadCursorW.restype = wintypes.HANDLE
        user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, wintypes.LPVOID]
        ci = CURSORINFO()
        ci.cbSize = ctypes.sizeof(CURSORINFO)
        if not user32.GetCursorInfo(ctypes.byref(ci)):
            return False
        ibeam = user32.LoadCursorW(None, ctypes.c_void_p(32513))   # IDC_IBEAM
        return bool(ci.hCursor) and ci.hCursor == ibeam
    except Exception:
        return False


def foreground_window_title() -> str:
    if not _IS_WIN:
        return ""
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        return buf.value.strip()
    except Exception:
        return ""


# ============================ Istoric execuții sarcini (persistent) ============================

class TaskHistory:
    """Păstrează pe disc (istoric_sarcini.json) fiecare execuție: programată, test, amânată, ratată etc."""
    MAX_ENTRIES = 3000

    def __init__(self, filepath: str = HISTORY_FILE):
        self.filepath = filepath
        self._lock = threading.RLock()
        self.entries: List[dict] = []
        self._load()

    def _load(self):
        try:
            if os.path.exists(self.filepath):
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self.entries = data
        except Exception as e:
            print(f"[HISTORY] Nu s-a putut citi istoricul: {e}")
            self.entries = []

    def _save(self):
        try:
            tmp = self.filepath + ".tmp"
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self.entries[-self.MAX_ENTRIES:], f, indent=1, ensure_ascii=False)
            os.replace(tmp, self.filepath)
        except Exception as e:
            print(f"[HISTORY] Nu s-a putut salva istoricul: {e}")

    def add(self, **fields) -> str:
        with self._lock:
            entry = {
                'run_id': datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:4],
                'task_id': '', 'task_name': '', 'trigger': 'Programat',
                'scheduled_for': '', 'started': '', 'ended': '',
                'status': '', 'steps_total': 0, 'steps_done': 0,
                'details': [],
            }
            entry.update(fields)
            self.entries.append(entry)
            self._save()
            return entry['run_id']

    def update(self, run_id: str, save: bool = True, **fields):
        with self._lock:
            for e in reversed(self.entries):
                if e.get('run_id') == run_id:
                    e.update(fields)
                    break
            if save:
                self._save()

    def append_detail(self, run_id: str, line: str):
        with self._lock:
            for e in reversed(self.entries):
                if e.get('run_id') == run_id:
                    e.setdefault('details', []).append(line)
                    break

    def get(self, run_id: str) -> Optional[dict]:
        with self._lock:
            for e in reversed(self.entries):
                if e.get('run_id') == run_id:
                    return dict(e)
        return None

    def snapshot(self) -> List[dict]:
        with self._lock:
            return [dict(e) for e in self.entries]

    def clear(self):
        with self._lock:
            self.entries = []
            self._save()


# ============================ Model ============================

@dataclass
class ScheduledTask:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = "Sarcina 1"
    enabled: bool = True               # Implicit Activă; utilizatorul o trece pe pauză doar dacă dorește
    action_type: str = "steps"         # "steps", "file", "current"
    steps: List[dict] = field(default_factory=list) # Pașii înregistrați proprii
    task_file: str = ""                # Calea către fișier .json (opțional)
    playback_speed: float = 1.0        # Viteza de redare (0.1x - 5.0x)
    run_mode: str = "once"             # Implicit "once" (o singură dată); sau "continuous", "repeat", "loop"
    repeat_minutes: int = 5            # Minute pentru modul "repeat"
    loop_count: int = 1                # Număr repetări pentru modul "loop"
    days: Set[str] = field(default_factory=set) # Implicit nicio zi bifată până la alegerea utilizatorului
    specific_date_enabled: bool = False
    specific_date: str = ""            # "YYYY-MM-DD"
    time_interval_enabled: bool = True
    from_time: str = "09:00"
    to_time: str = "17:00"

    # Runtime state (nu se salvează neapărat în JSON)
    last_run_date: str = ""
    last_run_minute: str = ""
    last_run_timestamp: float = 0.0

    def schedule_signature(self) -> tuple:
        """Amprenta programării: dacă se schimbă, sarcina poate rula din nou în aceeași zi."""
        return (self.from_time, self.to_time, tuple(sorted(self.days)), self.specific_date_enabled,
                self.specific_date, self.run_mode, self.time_interval_enabled, self.enabled)

    def copy(self, new_id: bool = True):
        t = self._copy_config(new_id)
        if not new_id:
            # Copia de lucru păstrează starea de rulare (altfel o sarcină deja rulată azi putea porni din nou)
            t.last_run_date = self.last_run_date
            t.last_run_minute = self.last_run_minute
            t.last_run_timestamp = self.last_run_timestamp
        return t

    def _copy_config(self, new_id: bool = True):
        return ScheduledTask(
            id=str(uuid.uuid4())[:8] if new_id else self.id,
            name=self.name,
            enabled=self.enabled,
            action_type=self.action_type,
            steps=[s.copy() if isinstance(s, dict) else s for s in self.steps],
            task_file=self.task_file,
            playback_speed=self.playback_speed,
            run_mode=self.run_mode,
            repeat_minutes=self.repeat_minutes,
            loop_count=self.loop_count,
            days=set(self.days),
            specific_date_enabled=self.specific_date_enabled,
            specific_date=self.specific_date,
            time_interval_enabled=self.time_interval_enabled,
            from_time=self.from_time,
            to_time=self.to_time
        )

    def get_days_summary(self) -> str:
        if self.specific_date_enabled and self.specific_date:
            return f"Data: {self.specific_date}"
        if len(self.days) == 7:
            return "Zilnic"
        if not self.days:
            return "Nicio zi aleasă ⚠"
        day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        day_ro = {'Monday': 'Lun', 'Tuesday': 'Mar', 'Wednesday': 'Mie', 'Thursday': 'Joi', 'Friday': 'Vin', 'Saturday': 'Sâm', 'Sunday': 'Dum'}
        sorted_d = [day_ro.get(d, d[:3]) for d in day_order if d in self.days]
        return ", ".join(sorted_d)

    def get_time_summary(self) -> str:
        if self.time_interval_enabled:
            return f"{self.from_time} - {self.to_time}"
        return f"La {self.from_time}"

    def get_action_summary(self) -> str:
        if self.action_type == "steps" or self.steps:
            return f"{len(self.steps)} pași înreg."
        if self.action_type == "file":
            if self.task_file:
                return os.path.basename(self.task_file)
            return "(Fișier nesetat)"
        return "Pași din aplicație"

    def get_mode_summary(self) -> str:
        if self.run_mode == "continuous":
            return "Continuu"
        if self.run_mode == "once":
            return "O singură dată"
        if self.run_mode == "repeat":
            return f"La {self.repeat_minutes} min"
        if self.run_mode == "loop":
            return f"{self.loop_count}x"
        return self.run_mode


@dataclass
class ScheduleConfig:
    enabled: bool = False
    tasks: List[ScheduledTask] = field(default_factory=list)
    keep_awake: bool = True            # Ține PC-ul și ecranul treze cât timp Scheduler-ul este ON
    auto_start: bool = False           # Pornește Scheduler-ul automat la deschiderea aplicației
    lock_check: bool = True            # Nu trimite clicuri când Windows este blocat; reîncearcă
    capture_screens: bool = True       # Captură de ecran la începutul și sfârșitul fiecărei rulări programate

    def copy(self):
        return ScheduleConfig(
            enabled=self.enabled,
            tasks=[t.copy(new_id=False) for t in self.tasks],
            keep_awake=self.keep_awake,
            auto_start=self.auto_start,
            lock_check=self.lock_check,
            capture_screens=self.capture_screens,
        )


@dataclass
class Step:
    kind: str
    args: dict
    timestamp: float = field(default_factory=time.time)

    def get_relative_time(self, first_time: float) -> float:
        return max(0, self.timestamp - first_time)

    def describe(self) -> str:
        if self.kind == "Wait":
            return f"Pauză {self.args.get('seconds', 0)} s"
        if self.kind == "LaunchPath":
            return f"Lansează '{self.args.get('path', '')}' {self.args.get('args','')}"
        if self.kind == "ClickAt":
            if int(self.args.get('clicks', 1) or 1) >= 2:
                return f"Dublu-clic la ({self.args.get('x')}, {self.args.get('y')})"
            return f"Clic la ({self.args.get('x')}, {self.args.get('y')}) buton={'dreapta' if self.args.get('button') == 'right' else ('mijloc' if self.args.get('button') == 'middle' else 'stânga')}"
        if self.kind == "MoveMouse":
            return f"Mută mouse-ul la ({self.args.get('x')}, {self.args.get('y')}) durată={self.args.get('duration',0)}"
        if self.kind == "SendKeys":
            txt = self.args.get('text','')
            return f"Tastează: '{txt[:40]}{'...' if len(txt) > 40 else ''}'"
        if self.kind == "Hotkey":
            return f"Combinație taste: {' + '.join(normalize_key_name(c) for c in self.args.get('combo', []))}"
        return f"{self.kind} {self.args}"


def parse_time_to_seconds(s: str, is_end_of_interval: bool = False) -> Optional[int]:
    """Convertește un string de timp HH:MM sau HH:MM:SS în număr total de secunde de la miezul nopții.
    Dacă formatul este HH:MM și is_end_of_interval=True, se adaugă 59 de secunde pentru a acoperi întregul minut.
    """
    try:
        parts = [p.strip() for p in s.strip().split(":")]
        if len(parts) == 2:
            h, m = int(parts[0]), int(parts[1])
            if 0 <= h <= 23 and 0 <= m <= 59:
                sec = 59 if is_end_of_interval else 0
                return h * 3600 + m * 60 + sec
        elif len(parts) == 3:
            h, m, sec = int(parts[0]), int(parts[1]), int(parts[2])
            if 0 <= h <= 23 and 0 <= m <= 59 and 0 <= sec <= 59:
                return h * 3600 + m * 60 + sec
        return None
    except Exception:
        return None


def is_time_in_range(cur_secs: int, from_str: str, to_str: str) -> bool:
    """Verifică dacă un număr curent de secunde se află în intervalul from_str - to_str (suportă și peste noapte)."""
    try:
        a = parse_time_to_seconds(from_str, is_end_of_interval=False)
        b = parse_time_to_seconds(to_str, is_end_of_interval=True)
        if a is None or b is None:
            return False
        if b < a:
            # Interval peste noapte, ex: 21:00 - 03:00 sau 21:00:30 - 03:00:15
            return cur_secs >= a or cur_secs <= b
        else:
            return a <= cur_secs <= b
    except Exception:
        return False


MIN_TASK_GAP_SECONDS = 30

DAY_RO = {'Monday': 'Luni', 'Tuesday': 'Marți', 'Wednesday': 'Miercuri', 'Thursday': 'Joi',
          'Friday': 'Vineri', 'Saturday': 'Sâmbătă', 'Sunday': 'Duminică'}


def times_are_same_instant(from_str: str, to_str: str) -> bool:
    """True când From time și To time reprezintă exact aceeași secundă (ex: 14:03:03 și 14:03:03)."""
    a = parse_time_to_seconds(from_str, is_end_of_interval=False)
    b = parse_time_to_seconds(to_str, is_end_of_interval=False)
    return a is not None and b is not None and a == b


def _task_applies_today(task: "ScheduledTask", current_day: str, current_date: str) -> bool:
    if not task.enabled:
        return False
    if task.specific_date_enabled and task.specific_date:
        return task.specific_date == current_date
    return bool(task.days) and current_day in task.days


def earlier_task_within_gap(task: "ScheduledTask", tasks: List["ScheduledTask"],
                            current_day: str, current_date: str,
                            gap_seconds: int = MIN_TASK_GAP_SECONDS) -> Optional["ScheduledTask"]:
    """Returnează sarcina anterioară (ca oră de start) aflată la mai puțin de gap_seconds de From time."""
    my = parse_time_to_seconds(task.from_time, is_end_of_interval=False)
    if my is None:
        return None
    try:
        my_idx = next(i for i, t in enumerate(tasks) if t.id == task.id)
    except StopIteration:
        my_idx = -1

    for i, other in enumerate(tasks):
        if other.id == task.id:
            continue
        if not _task_applies_today(other, current_day, current_date):
            continue
        other_s = parse_time_to_seconds(other.from_time, is_end_of_interval=False)
        if other_s is None:
            continue
        # Câte secunde sunt de la startul celuilalt până la startul sarcinii curente (peste miezul nopții inclus)
        forward = (my - other_s) % 86400
        if forward == 0:
            if 0 <= i < my_idx:
                return other
        elif forward < gap_seconds:
            return other
    return None


def is_time_matched(current_time_hm: str, current_time_hms: str, cur_secs: int, target_time_str: str) -> bool:
    """Verifică dacă momentul curent corespunde orei țintă fixate (HH:MM sau HH:MM:SS)."""
    try:
        parts = [p.strip() for p in target_time_str.strip().split(":")]
        if len(parts) == 2:
            h, m = int(parts[0]), int(parts[1])
            formatted = f"{h:02d}:{m:02d}"
            return current_time_hm == formatted
        elif len(parts) == 3:
            h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
            target_secs = h * 3600 + m * 60 + s
            # Marjă de 1 secundă în caz de ușoară variație a firului scheduler
            return 0 <= (cur_secs - target_secs) <= 1
        return False
    except Exception:
        return False


# ============================ Tooltip ============================

class ToolTip:
    def __init__(self, widget, text, delay_ms=300, padx=10, pady=6):
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
        self._tip = tk.Toplevel(self.widget)
        self._tip.wm_overrideredirect(True)
        self._tip.attributes("-topmost", True)
        label = tk.Label(self._tip, text=self.text, justify="left", relief="solid",
                         borderwidth=1, padx=8, pady=4, bg="#FFFFE0", fg="#000000",
                         font=("Arial", 8))
        label.pack()
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


# ============================ Scheduler ============================

class Scheduler:
    """Thread de fundal care verifică la fiecare 0,5 s ce sarcini trebuie pornite.

    Îmbunătățiri (diagnostic 25.11.2026 — sarcinile de la 02:01 / 02:08 au „rulat” dar PC-ul era
    în Modern Standby cu ecranul de blocare activ, deci clicurile n-au ajuns nicăieri):
      • Ține PC-ul și ecranul treze cât timp Scheduler-ul este ON (opțiune).
      • Înainte de rulare aprinde ecranul și verifică dacă Windows este blocat; dacă da, NU trimite
        clicuri „în gol”, ci reîncearcă la 30 s, timp de până la 5 minute.
      • Fereastră de toleranță de 5 minute: dacă thread-ul a fost înghețat (Sleep/Standby) exact în
        minutul programat, sarcina pornește imediat după trezire.
      • Fiecare execuție / amânare / ratare este scrisă în istoricul persistent (istoric_sarcini.json).
    """

    def __init__(self, controller):
        self.ctrl = controller
        self.running = False
        self._thread = None
        self.active_task_id: Optional[str] = None
        self._last_checked_minute = None
        self.user_stopped = False
        self._gap_skip_logged = set()

        self._armed_since: Optional[float] = None       # Momentul în care Scheduler-ul a fost pornit (ON)
        self._task_armed: Dict[str, tuple] = {}           # task_id -> (semnătură programare, ts) — fără rulări retroactive după editare
        self._keep_awake_state: Optional[bool] = None
        self._last_loop_ts = time.time()
        self._freezes: List[tuple] = []                   # (început, sfârșit) perioade în care thread-ul a fost înghețat
        self._missed_logged = set()                       # (task_id, data)
        self._lock_wait: Dict[str, dict] = {}             # task_id -> {date, next, run_id, attempts}

    def start(self):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._thread.start()
        print("[SCHEDULER] Multi-Task Scheduler Started")

    def stop(self):
        self.running = False
        print("[SCHEDULER] Stopped")

    # ------------------------------------------------------------------
    def _scheduler_loop(self):
        while self.running:
            try:
                now_ts = time.time()
                gap = now_ts - self._last_loop_ts
                self._last_loop_ts = now_ts
                cfg = self.ctrl.schedule_config
                if gap > 20:
                    self._freezes.append((now_ts - gap, now_ts))
                    self._freezes = self._freezes[-50:]
                    if cfg.enabled:
                        self.ctrl.log(
                            f"💤 [SCHEDULER] Aplicația a fost înghețată {int(gap)} s "
                            f"(PC în Sleep / Modern Standby între {time.strftime('%H:%M:%S', time.localtime(now_ts - gap))} "
                            f"și {time.strftime('%H:%M:%S', time.localtime(now_ts))}). Verific sarcinile întârziate...")

                self._update_keep_awake(cfg)

                if cfg.enabled:
                    if self._armed_since is None:
                        self._armed_since = now_ts
                    self._check_and_run_tasks()
                else:
                    self._armed_since = None
            except Exception as e:
                print(f"[SCHEDULER] Error in loop: {e}")
                try:
                    self.ctrl.log(f"❌ [SCHEDULER] Eroare internă: {e}")
                except Exception:
                    pass

            time.sleep(0.5)
        set_keep_awake(False)

    def _update_keep_awake(self, cfg: "ScheduleConfig"):
        want = bool(cfg.enabled and cfg.keep_awake and any(t.enabled for t in cfg.tasks))
        if want == self._keep_awake_state:
            return
        ok = set_keep_awake(want)
        self._keep_awake_state = want
        if want:
            self.ctrl.log("☕ [SCHEDULER] PC-ul și ecranul sunt ținute TREZE cât timp Scheduler-ul este ON "
                          f"(fără Sleep / Standby / blocare automată){'' if ok else ' — ATENȚIE: Windows a refuzat cererea!'}")
        elif self._keep_awake_state is not None:
            self.ctrl.log("💤 [SCHEDULER] PC-ul poate intra din nou în Sleep normal.")

    # ------------------------------------------------------------------
    def _effective_armed(self, task: ScheduledTask, now_ts: float) -> float:
        """Momentul de la care sarcina este „armată”: max(pornire Scheduler, ultima modificare a programării)."""
        sig = task.schedule_signature()
        prev = self._task_armed.get(task.id)
        if prev is None:
            self._task_armed[task.id] = (sig, self._armed_since or now_ts)
        elif prev[0] != sig:
            self._task_armed[task.id] = (sig, now_ts)
        task_armed = self._task_armed[task.id][1]
        return max(self._armed_since or now_ts, task_armed)

    @staticmethod
    def _scheduled_dt(task: ScheduledTask, now: datetime) -> Optional[datetime]:
        secs = parse_time_to_seconds(task.from_time, is_end_of_interval=False)
        if secs is None:
            return None
        return now.replace(hour=secs // 3600, minute=(secs % 3600) // 60, second=secs % 60, microsecond=0)

    def _in_trigger_window(self, task: ScheduledTask, now: datetime, armed_ts: float):
        """(True, ora_programată) dacă suntem între ora fixată și ora fixată + GRACE_SECONDS,
        iar Scheduler-ul era deja pornit la ora fixată (nu rulăm retroactiv la deschiderea programului)."""
        sched = self._scheduled_dt(task, now)
        if sched is None:
            return False, None
        delta = (now - sched).total_seconds()
        if delta < 0 or delta > GRACE_SECONDS:
            return False, sched
        if armed_ts > sched.timestamp() + 60:
            return False, sched
        return True, sched

    def _froze_around(self, ts: float) -> Optional[tuple]:
        for a, b in self._freezes:
            if a - 5 <= ts <= b + 5:
                return (a, b)
        return None

    def _check_missed(self, task: ScheduledTask, now: datetime, armed_ts: float, current_date: str):
        """Înregistrează în istoric o sarcină „o singură dată” care NU a mai putut porni în fereastra de toleranță."""
        key = (task.id, current_date)
        if key in self._missed_logged or task.last_run_date == current_date:
            return
        sched = self._scheduled_dt(task, now)
        if sched is None:
            return
        if (now - sched).total_seconds() <= GRACE_SECONDS or armed_ts > sched.timestamp() + 60:
            return
        self._missed_logged.add(key)
        lw = self._lock_wait.get(task.id)
        if lw and lw.get('date') == current_date:
            reason = "Windows a rămas BLOCAT (ecran de blocare / parolă) toată fereastra de 5 minute — clicurile nu au fost trimise."
            self.ctrl.history.update(lw['run_id'], status="⛔ Ratată (PC blocat)", ended=now.strftime("%Y-%m-%d %H:%M:%S"))
            self.ctrl.history.append_detail(lw['run_id'], f"{now:%H:%M:%S} {reason}")
            self.ctrl.history.update(lw['run_id'])
        else:
            fz = self._froze_around(sched.timestamp())
            if fz:
                reason = (f"PC-ul a fost în Sleep / Standby între {time.strftime('%H:%M:%S', time.localtime(fz[0]))} și "
                          f"{time.strftime('%H:%M:%S', time.localtime(fz[1]))} — aplicația nu a putut rula.")
            elif self.ctrl.playing:
                reason = "O altă redare a rulat continuu în toată fereastra de 5 minute."
            else:
                reason = "Sarcina nu a putut porni în fereastra de 5 minute (vezi bebe_log.txt)."
            self.ctrl.history.add(task_id=task.id, task_name=task.name, scheduled_for=sched.strftime("%Y-%m-%d %H:%M:%S"),
                                  started="", ended=now.strftime("%Y-%m-%d %H:%M:%S"),
                                  status="⛔ Ratată", details=[f"{now:%H:%M:%S} {reason}"])
        self.ctrl.log(f"⛔ [SCHEDULER] Sarcina '{task.name}' ({task.from_time}) a fost RATATĂ azi: {reason}")

    # ------------------------------------------------------------------
    def _check_and_run_tasks(self):
        now = datetime.now()
        now_ts = now.timestamp()
        current_day = now.strftime("%A")
        current_time_hm = now.strftime("%H:%M")
        current_date = now.strftime("%Y-%m-%d")
        cur_secs = now.hour * 3600 + now.minute * 60 + now.second

        # 1. Gestionare sarcină activă dacă rulează în acest moment
        if self.ctrl.playing:
            if self.active_task_id:
                active_task = next((t for t in self.ctrl.schedule_config.tasks if t.id == self.active_task_id), None)
                if active_task:
                    # From = To (aceeași secundă): lăsăm sarcina să se termine, chiar dacă durează mai mult de 1s
                    same_instant = times_are_same_instant(active_task.from_time, active_task.to_time)
                    if (active_task.time_interval_enabled and active_task.run_mode == "continuous"
                            and not same_instant):
                        if not is_time_in_range(cur_secs, active_task.from_time, active_task.to_time):
                            self.ctrl.log(f"⏰ [SCHEDULER] Intervalul orar ({active_task.from_time}-{active_task.to_time}) s-a încheiat pentru '{active_task.name}'. Oprim playback-ul.")
                            self.ctrl._stop_reason = "interval"
                            self.ctrl.stop()
                            self.active_task_id = None
            # Chiar și în timpul unei redări, notăm sarcinile ratate
            for task in self.ctrl.schedule_config.tasks:
                if _task_applies_today(task, current_day, current_date) and \
                        (task.run_mode in ("once", "loop") or times_are_same_instant(task.from_time, task.to_time)):
                    self._check_missed(task, now, self._effective_armed(task, now_ts), current_date)
            return

        # Playback-ul nu mai este activ
        self.active_task_id = None

        # În timpul înregistrării nu pornim nimic (sarcina așteaptă, în fereastra de toleranță de 5 minute)
        if self.ctrl.recording:
            return

        # Dacă utilizatorul a oprit manual sarcina în acest minut, așteptăm minutul următor
        if self.user_stopped and self._last_checked_minute == current_time_hm:
            return

        # 2. Căutare sarcină eligibilă pentru rulare
        for task in self.ctrl.schedule_config.tasks:
            # Sarcina trebuie să fie explicit bifată ca Activă
            if not task.enabled:
                continue

            # Verificare Zile / Dată:
            if task.specific_date_enabled and task.specific_date:
                if task.specific_date != current_date:
                    continue
            else:
                # IMPORTANT: Dacă nu este bifată nicio zi din săptămână, sarcina NU are voie să ruleze!
                if not task.days:
                    continue
                if current_day not in task.days:
                    continue

            armed_ts = self._effective_armed(task, now_ts)

            # Sarcină amânată pentru că Windows era blocat: așteptăm momentul reîncercării
            lw = self._lock_wait.get(task.id)
            if lw and lw.get('date') == current_date and lw.get('next', 0) > now_ts:
                continue

            trigger = False
            sched_dt: Optional[datetime] = None
            same_instant = times_are_same_instant(task.from_time, task.to_time)
            fixed_time = same_instant or task.run_mode in ("once", "loop")

            if fixed_time:
                # „O singură dată” / „De N ori” / From = To: pornește la ora fixată (from_time),
                # cu toleranță de GRACE_SECONDS dacă PC-ul a fost în standby / blocat exact atunci.
                ok, sched_dt = self._in_trigger_window(task, now, armed_ts)
                if not ok:
                    self._check_missed(task, now, armed_ts, current_date)
                    continue
                if task.last_run_date == current_date:
                    continue
                trigger = True

            elif task.run_mode == "continuous":
                if task.time_interval_enabled:
                    if not is_time_in_range(cur_secs, task.from_time, task.to_time):
                        continue
                trigger = True

            elif task.run_mode == "repeat":
                if task.time_interval_enabled:
                    if not is_time_in_range(cur_secs, task.from_time, task.to_time):
                        continue
                repeat_secs = max(1, task.repeat_minutes) * 60
                if (time.time() - task.last_run_timestamp) < repeat_secs:
                    continue
                trigger = True

            if not trigger:
                continue

            conflict = earlier_task_within_gap(
                task, self.ctrl.schedule_config.tasks, current_day, current_date
            )
            if conflict:
                skip_key = (task.id, current_date, current_time_hm)
                if skip_key not in self._gap_skip_logged:
                    self._gap_skip_logged.add(skip_key)
                    msg = (f"Sarcina '{task.name}' ({task.from_time}) NU rulează: este la mai puțin de "
                           f"{MIN_TASK_GAP_SECONDS}s de '{conflict.name}' ({conflict.from_time}).")
                    self.ctrl.log(f"⏭️ [SCHEDULER] {msg}")
                    self.ctrl.history.add(task_id=task.id, task_name=task.name,
                                          scheduled_for=sched_dt.strftime("%Y-%m-%d %H:%M:%S") if sched_dt else "",
                                          ended=now.strftime("%Y-%m-%d %H:%M:%S"), status="⏭ Sărită (conflict)",
                                          details=[msg])
                if fixed_time:
                    task.last_run_date = current_date
                    task.last_run_minute = f"{current_date} {current_time_hm}"
                continue

            # 3. Pregătire desktop: aprindem ecranul și verificăm că Windows NU este blocat
            if not self._prepare_desktop(task, now, sched_dt, current_date):
                continue

            if fixed_time:
                task.last_run_date = current_date
                task.last_run_minute = f"{current_date} {current_time_hm}"
                self.ctrl.persist_run_state()
            elif task.run_mode == "repeat":
                task.last_run_timestamp = time.time()

            self.user_stopped = False
            self._last_checked_minute = current_time_hm
            self.active_task_id = task.id
            self._execute_scheduled_task(task, force_once=same_instant, scheduled_for=sched_dt)
            break  # Rulăm o singură sarcină odată

    def _prepare_desktop(self, task: ScheduledTask, now: datetime, sched_dt: Optional[datetime], current_date: str) -> bool:
        """Aprinde ecranul. Dacă Windows este blocat, amână sarcina (reîncercare la LOCK_RETRY_SECONDS)."""
        cfg = self.ctrl.schedule_config
        wake_display()
        if not cfg.lock_check:
            time.sleep(0.3)
            return True
        locked = is_workstation_locked()
        if locked:
            # După ieșirea din Standby, sesiunea are nevoie de câteva secunde
            for _ in range(16):
                time.sleep(0.5)
                if not is_workstation_locked():
                    locked = False
                    break
        if not locked:
            lw = self._lock_wait.pop(task.id, None)
            if lw and lw.get('date') == current_date:
                self.ctrl.history.update(lw['run_id'], status="🔒→▶ Amânată, apoi pornită",
                                         ended=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            time.sleep(0.5)  # lăsăm desktopul să se redeseneze după trezire
            return True

        now_ts = time.time()
        lw = self._lock_wait.get(task.id)
        if not lw or lw.get('date') != current_date:
            msg = ("Windows este BLOCAT (ecran de blocare / cere parola după Standby). Clicurile NU sunt trimise — "
                   f"reîncerc la fiecare {LOCK_RETRY_SECONDS} s, timp de {GRACE_SECONDS // 60} minute.")
            run_id = self.ctrl.history.add(task_id=task.id, task_name=task.name,
                                           scheduled_for=sched_dt.strftime("%Y-%m-%d %H:%M:%S") if sched_dt else "",
                                           started=now.strftime("%Y-%m-%d %H:%M:%S"),
                                           status="🔒 Amânată (PC blocat)", details=[f"{now:%H:%M:%S} {msg}"])
            self._lock_wait[task.id] = {'date': current_date, 'next': now_ts + LOCK_RETRY_SECONDS,
                                        'run_id': run_id, 'attempts': 1}
            self.ctrl.log(f"🔒 [SCHEDULER] Sarcina '{task.name}': {msg}")
        else:
            lw['attempts'] += 1
            lw['next'] = now_ts + LOCK_RETRY_SECONDS
            self.ctrl.history.append_detail(lw['run_id'], f"{now:%H:%M:%S} Încercarea #{lw['attempts']}: Windows încă blocat.")
            self.ctrl.history.update(lw['run_id'])
        if task.run_mode == "repeat":
            task.last_run_timestamp = time.time()
        return False

    def _execute_scheduled_task(self, task: ScheduledTask, force_once: bool = False,
                                scheduled_for: Optional[datetime] = None, trigger: str = "Programat"):
        steps = self.ctrl.get_steps_for_task(task)
        if not steps:
            self.ctrl.log(f"⚠️ [SCHEDULER] Sarcina '{task.name}' nu are pași de executat!")
            self.ctrl.history.add(task_id=task.id, task_name=task.name, trigger=trigger,
                                  scheduled_for=scheduled_for.strftime("%Y-%m-%d %H:%M:%S") if scheduled_for else "",
                                  started=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                  ended=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                  status="⚠ Fără pași", details=["Sarcina nu are pași de executat."])
            self.active_task_id = None
            return

        is_cont = (task.run_mode == "continuous") and not force_once
        if force_once:
            mode_desc = "O singură dată (From = To)"
        else:
            mode_desc = "Continuu în interval" if is_cont else ("O singură dată" if task.run_mode == "once" else task.get_mode_summary())
        late = ""
        if scheduled_for is not None:
            delay = (datetime.now() - scheduled_for).total_seconds()
            if delay > 60:
                late = f" — ÎNTÂRZIERE {int(delay)} s față de ora programată"
        self.ctrl.log(f"⏰ [SCHEDULER] S-a declanșat sarcina: '{task.name}' ({len(steps)} pași, Mod: {mode_desc}, Viteză: {task.playback_speed}x){late}")
        print(f"[SCHEDULER] Starting '{task.name}' (mode={task.run_mode}, speed={task.playback_speed}x)")

        self.ctrl.steps = steps
        self.ctrl.ui_queue.put(("refresh", None))

        self.ctrl.playback_speed = max(0.1, float(task.playback_speed))
        if force_once:
            self.ctrl.run_continuously = False
            self.ctrl.loop_enabled = False
            self.ctrl.loop_count = 1
        elif task.run_mode == "continuous":
            self.ctrl.run_continuously = True
            self.ctrl.loop_enabled = False
            self.ctrl.loop_count = 1
        elif task.run_mode == "loop":
            self.ctrl.run_continuously = False
            self.ctrl.loop_enabled = True
            self.ctrl.loop_count = max(1, task.loop_count)
        else:  # "once" sau "repeat"
            self.ctrl.run_continuously = False
            self.ctrl.loop_enabled = False
            self.ctrl.loop_count = 1

        self.ctrl.begin_run_record(task, trigger=trigger, scheduled_for=scheduled_for, steps_total=len(steps))
        self.ctrl.play()
        self.ctrl.ui_queue.put(("state", None))


# ============================ Controller ============================

class TaskController:
    def __init__(self, log_fn):
        self.steps: List[Step] = []
        self.log = log_fn
        self.schedule_config = ScheduleConfig()
        self.history = TaskHistory()
        self._run_ctx: Optional[dict] = None      # Execuția curentă înregistrată în istoric
        self._stop_reason: Optional[str] = None

        # Încarcă din schedules.json dacă există, altfel inițializează implicit
        loaded = self.load_schedules_from_disk()
        if not loaded and not self.schedule_config.tasks:
            self._init_default_schedules()

        self.scheduler = Scheduler(self)

        # Recorder
        self.recording = False
        self._mouse_listener = None
        self._kb_listener = None

        # Playback
        self.playing = False
        self.paused = False
        self._play_thread: Optional[threading.Thread] = None
        self.playback_speed = 1.0
        self.loop_enabled = False
        self.loop_count = 1
        self.run_continuously = False

        # UI queue
        self.ui_queue = queue.Queue()

        print("[CTRL] TaskController initialized")
        self.scheduler.start()

    def _init_default_schedules(self):
        default_task = ScheduledTask(
            id=str(uuid.uuid4())[:8],
            name="Sarcina 1",
            enabled=True,
            action_type="steps",
            playback_speed=1.0,
            run_mode="once",
            days=set(),
            time_interval_enabled=True,
            from_time="09:00",
            to_time="17:00"
        )
        self.schedule_config.tasks.append(default_task)

    def get_steps_for_task(self, task: ScheduledTask) -> List[Step]:
        # 1. Dacă sarcina are pași proprii salvați direct:
        if task.steps:
            st_list = []
            for o in task.steps:
                st = Step(kind=o['kind'], args=o['args'])
                if 'timestamp' in o:
                    st.timestamp = o['timestamp']
                st_list.append(st)
            return st_list

        # 2. Dacă sarcina are un fișier .json asociat:
        if task.action_type == "file" and task.task_file:
            filepath = task.task_file
            if not os.path.isabs(filepath):
                filepath = os.path.join(os.getcwd(), filepath)
            if os.path.exists(filepath):
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.loads(f.read())
                    st_list = []
                    for o in data.get('steps', []):
                        st = Step(kind=o['kind'], args=o['args'])
                        if 'timestamp' in o:
                            st.timestamp = o['timestamp']
                        st_list.append(st)
                    return st_list
                except Exception as e:
                    self.log(f"❌ Eroare la citirea fișierului {task.task_file}: {e}")
                    return []
            else:
                self.log(f"⚠️ Fișierul nu a fost găsit: {task.task_file}")
                return []

        # 3. În caz contrar, folosește pașii din memoria curentă
        return list(self.steps)

    def test_play_task(self, task: ScheduledTask):
        # Dacă deja rulează un playback (de la testul anterior sau altul), oprim mai întâi
        if self.playing:
            self.stop()
            time.sleep(0.1)

        steps = self.get_steps_for_task(task)
        if not steps:
            self.log(f"⚠️ [TEST] Nu există evenimente de rulat pentru '{task.name}'")
            return
        self.log(f"▶️ [TEST] Testare sarcină '{task.name}' ({len(steps)} pași, viteză: {task.playback_speed}x)...")
        self.steps = steps
        self.ui_queue.put(("refresh", None))
        self.playback_speed = max(0.1, float(task.playback_speed))
        self.run_continuously = False
        self.loop_enabled = False
        self.loop_count = 1
        self.begin_run_record(task, trigger="Test manual", scheduled_for=None, steps_total=len(steps))
        self.play()
        self.ui_queue.put(("state", None))

    # ----- Istoric execuții
    def begin_run_record(self, task: ScheduledTask, trigger: str, scheduled_for: Optional[datetime], steps_total: int):
        now = datetime.now()
        run_id = self.history.add(
            task_id=task.id, task_name=task.name, trigger=trigger,
            scheduled_for=scheduled_for.strftime("%Y-%m-%d %H:%M:%S") if scheduled_for else "",
            started=now.strftime("%Y-%m-%d %H:%M:%S"), status="▶ În curs",
            steps_total=steps_total, steps_done=0,
            details=[f"{now:%H:%M:%S} Start. Fereastra activă: '{foreground_window_title()}'. "
                     f"Windows blocat: {'DA' if is_workstation_locked() else 'nu'}."],
        )
        self._run_ctx = {'run_id': run_id, 'task_name': task.name, 'step_no': 0}
        self._stop_reason = None
        self._capture_screen("start")

    def _capture_screen(self, label: str):
        ctx = self._run_ctx
        if not ctx or not self.schedule_config.capture_screens:
            return
        try:
            from PIL import ImageGrab
            folder = os.path.join(CAPTURES_DIR, ctx['run_id'])
            os.makedirs(folder, exist_ok=True)
            img = ImageGrab.grab(all_screens=True)
            img = img.convert("RGB")
            img.thumbnail((1920, 1920))
            path = os.path.join(folder, f"{label}.jpg")
            img.save(path, "JPEG", quality=60)
            self.history.append_detail(ctx['run_id'], f"{datetime.now():%H:%M:%S} Captură ecran ({label}): {path}")
        except Exception as e:
            self.history.append_detail(ctx['run_id'], f"{datetime.now():%H:%M:%S} Captura '{label}' a eșuat: {e}")

    def _finish_run_record(self, status: str, extra: str = "", ctx: Optional[dict] = None):
        ctx = ctx or self._run_ctx
        if not ctx or ctx.get('finished'):
            return
        ctx['finished'] = True
        if ctx is self._run_ctx:
            self._capture_screen("final")
        now = datetime.now()
        if extra:
            self.history.append_detail(ctx['run_id'], f"{now:%H:%M:%S} {extra}")
        self.history.update(ctx['run_id'], status=status, ended=now.strftime("%Y-%m-%d %H:%M:%S"),
                            steps_done=ctx['step_no'])
        self.log(f"📜 [ISTORIC] '{ctx['task_name']}': {status} ({ctx['step_no']} pași executați).")
        if ctx is self._run_ctx:
            self._run_ctx = None

    def persist_run_state(self):
        """Salvează pe disc starea „a rulat azi” — după o repornire, sarcina nu se repetă în aceeași zi."""
        try:
            self.save_schedules_to_disk()
        except Exception:
            pass

    # ----- Persistence: schedules.json
    def save_schedules_to_disk(self, filepath="schedules.json"):
        try:
            cfg = self.schedule_config
            data = {
                'schedule_global_enabled': cfg.enabled,
                'keep_awake': cfg.keep_awake,
                'auto_start_scheduler': cfg.auto_start,
                'lock_check': cfg.lock_check,
                'capture_screens': cfg.capture_screens,
                'scheduled_tasks': [
                    {
                        'id': t.id,
                        'name': t.name,
                        'enabled': t.enabled,
                        'action_type': t.action_type,
                        'steps': t.steps,
                        'task_file': t.task_file,
                        'playback_speed': t.playback_speed,
                        'run_mode': t.run_mode,
                        'repeat_minutes': t.repeat_minutes,
                        'loop_count': t.loop_count,
                        'days': sorted(t.days),
                        'specific_date_enabled': t.specific_date_enabled,
                        'specific_date': t.specific_date,
                        'time_interval_enabled': t.time_interval_enabled,
                        'from_time': t.from_time,
                        'to_time': t.to_time,
                        'last_run_date': t.last_run_date
                    }
                    for t in list(cfg.tasks)
                ]
            }
            tmp = filepath + ".tmp"
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, filepath)
            print(f"[CTRL] Schedules saved to {filepath} ({len(self.schedule_config.tasks)} tasks)")
        except Exception as e:
            print(f"[CTRL] Failed to save schedules to {filepath}: {e}")

    def load_schedules_from_disk(self, filepath="schedules.json") -> bool:
        if not os.path.exists(filepath):
            return False
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                obj = json.load(f)
            # Scheduler-ul pornește OPRIT (OFF) la deschiderea aplicației, CU EXCEPȚIA cazului în care
            # utilizatorul a bifat „Pornește Scheduler-ul automat la deschiderea aplicației”.
            cfg = self.schedule_config
            cfg.keep_awake = bool(obj.get('keep_awake', True))
            cfg.auto_start = bool(obj.get('auto_start_scheduler', False))
            cfg.lock_check = bool(obj.get('lock_check', True))
            cfg.capture_screens = bool(obj.get('capture_screens', True))
            cfg.enabled = bool(obj.get('schedule_global_enabled', False)) if cfg.auto_start else False
            loaded_tasks = []
            for t_data in obj.get('scheduled_tasks', []):
                st = ScheduledTask(
                    id=t_data.get('id', str(uuid.uuid4())[:8]),
                    name=t_data.get('name', 'Sarcina'),
                    enabled=t_data.get('enabled', True),
                    action_type=t_data.get('action_type', 'steps'),
                    steps=t_data.get('steps', []),
                    task_file=t_data.get('task_file', ''),
                    playback_speed=t_data.get('playback_speed', 1.0),
                    run_mode=t_data.get('run_mode', 'once'),
                    repeat_minutes=t_data.get('repeat_minutes', 5),
                    loop_count=t_data.get('loop_count', 1),
                    days=set(t_data.get('days', [])),
                    specific_date_enabled=t_data.get('specific_date_enabled', False),
                    specific_date=t_data.get('specific_date', ''),
                    time_interval_enabled=t_data.get('time_interval_enabled', True),
                    from_time=t_data.get('from_time', '09:00'),
                    to_time=t_data.get('to_time', '17:00'),
                    last_run_date=t_data.get('last_run_date', '')
                )
                loaded_tasks.append(st)
            self.schedule_config.tasks = loaded_tasks
            print(f"[CTRL] Loaded {len(self.schedule_config.tasks)} scheduled tasks from {filepath}")
            return True
        except Exception as e:
            print(f"[CTRL] Failed to load schedules from {filepath}: {e}")
            return False

    # ----- JSON Task file Save / Load
    def to_json(self) -> str:
        print(f"[CTRL] Saving to JSON: {len(self.steps)} steps")
        first_t = self.schedule_config.tasks[0] if self.schedule_config.tasks else None
        data = {
            'version': '5.5',
            'steps': [asdict(s) for s in self.steps],
            'schedule_global_enabled': self.schedule_config.enabled,
            'scheduled_tasks': [
                {
                    'id': t.id,
                    'name': t.name,
                    'enabled': t.enabled,
                    'action_type': t.action_type,
                    'steps': t.steps,
                    'task_file': t.task_file,
                    'playback_speed': t.playback_speed,
                    'run_mode': t.run_mode,
                    'repeat_minutes': t.repeat_minutes,
                    'loop_count': t.loop_count,
                    'days': list(t.days),
                    'specific_date_enabled': t.specific_date_enabled,
                    'specific_date': t.specific_date,
                    'time_interval_enabled': t.time_interval_enabled,
                    'from_time': t.from_time,
                    'to_time': t.to_time
                }
                for t in self.schedule_config.tasks
            ],
            # Compatibilitate înapoi cu v5.4
            'schedule': {
                'enabled': self.schedule_config.enabled,
                'days': list(first_t.days) if first_t else [],
                'time_interval_enabled': first_t.time_interval_enabled if first_t else False,
                'from_time': first_t.from_time if first_t else '09:00',
                'to_time': first_t.to_time if first_t else '17:00'
            }
        }
        return json.dumps(data, indent=2, ensure_ascii=False)

    def load_json(self, data_str: str):
        print("[CTRL] Loading from JSON...")
        obj = json.loads(data_str)
        self.steps = []
        for o in obj.get('steps', []):
            step = Step(kind=o['kind'], args=o['args'])
            if 'timestamp' in o:
                step.timestamp = o['timestamp']
            self.steps.append(step)
        print(f"[CTRL] Loaded {len(self.steps)} steps")

        # IMPORTANT: Fișierele de task conțin și un snapshot al sarcinilor programate (backup).
        # NU suprascriem sarcinile programate curente la încărcarea unui fișier de task,
        # decât dacă lista curentă este goală! (Altfel orarele configurate se pierdeau silențios.)
        if 'scheduled_tasks' in obj:
            if self.schedule_config.tasks:
                self.log("ℹ️ Fișierul conține și sarcini programate (snapshot vechi) — au fost IGNORATE. "
                         "Sarcinile programate curente rămân neschimbate.")
                return
            self.schedule_config.enabled = obj.get('schedule_global_enabled', False)
            tasks = []
            for t_data in obj.get('scheduled_tasks', []):
                st = ScheduledTask(
                    id=t_data.get('id', str(uuid.uuid4())[:8]),
                    name=t_data.get('name', 'Sarcina'),
                    enabled=t_data.get('enabled', True),
                    action_type=t_data.get('action_type', 'steps'),
                    steps=t_data.get('steps', []),
                    task_file=t_data.get('task_file', ''),
                    playback_speed=t_data.get('playback_speed', 1.0),
                    run_mode=t_data.get('run_mode', 'once'),
                    repeat_minutes=t_data.get('repeat_minutes', 5),
                    loop_count=t_data.get('loop_count', 1),
                    days=set(t_data.get('days', [])),
                    specific_date_enabled=t_data.get('specific_date_enabled', False),
                    specific_date=t_data.get('specific_date', ''),
                    time_interval_enabled=t_data.get('time_interval_enabled', True),
                    from_time=t_data.get('from_time', '09:00'),
                    to_time=t_data.get('to_time', '17:00')
                )
                tasks.append(st)
            self.schedule_config.tasks = tasks
        elif 'schedule' in obj:
            if self.schedule_config.tasks:
                self.log("ℹ️ Fișierul conține o programare veche (v5.4) — a fost IGNORATĂ. "
                         "Sarcinile programate curente rămân neschimbate.")
                return
            sch = obj['schedule']
            st = ScheduledTask(
                id=str(uuid.uuid4())[:8],
                name="Sarcina 1",
                enabled=sch.get('enabled', False),
                action_type="current",
                run_mode="once",
                days=set(sch.get('days', [])),
                time_interval_enabled=sch.get('time_interval_enabled', False),
                from_time=sch.get('from_time', '09:00'),
                to_time=sch.get('to_time', '17:00')
            )
            self.schedule_config.enabled = sch.get('enabled', False)
            self.schedule_config.tasks = [st]

    # ----- Steps ops
    def add_step(self, step: Step):
        self.steps.append(step)
        print(f"[CTRL] Added step: {step.describe()}")
        self.log(f"+ {step.describe()}")

    def delete_indices(self, idxs: List[int]):
        if not idxs:
            return
        print(f"[CTRL] Deleting indices: {idxs}")
        for i in sorted(set(idxs), reverse=True):
            if 0 <= i < len(self.steps):
                self.log(f"- Delete: {self.steps[i].describe()}")
                del self.steps[i]
        print(f"[CTRL] After delete: {len(self.steps)} steps remain")

    # ----- Recording
    def start_recording(self):
        if self.recording:
            return
        self.recording = True
        self.log("🔴 Recording started (Press ESC or F1 to stop)")
        print("[CTRL] Recording STARTED")

        def on_click(x, y, button, pressed, injected=False):
            if not self.recording:
                return
            # Ignorăm clicurile generate de program (redare), altfel se re-înregistrează la nesfârșit
            if injected or self.playing:
                return
            if pressed:
                self.add_step(Step("ClickAt", {"x": x, "y": y, "button": str(button).split(".")[-1]}))
                self.ui_queue.put(("refresh", None))

        # Starea tastelor modificatoare: nume normalizat ('ctrl','alt','shift','win','altgr') -> folosită într-o combinație?
        held = {}
        APP_KEYS = ('f1', 'esc', 'f9', 'f10')     # tastele aplicației — nu se înregistrează

        def mod_of(key) -> Optional[str]:
            if isinstance(key, kb.Key):
                if key.name == 'alt_gr':
                    return 'altgr'
                return MOD_NAMES.get(key.name)
            return None

        def on_release(key, injected=False):
            if injected:
                return
            m = mod_of(key)
            if not m or m not in held:
                return
            used = held.pop(m)
            # Win sau Alt apăsate SINGURE (fără altă tastă) au efect propriu (meniul Start / bara de meniu)
            if self.recording and not used and m in ('win', 'alt') and 'altgr' not in held:
                self.add_step(Step("Hotkey", {"combo": [m]}))
                self.ui_queue.put(("refresh", None))

        def on_press(key, injected=False):
            if not self.recording:
                return
            if injected or self.playing:
                return
            try:
                m = mod_of(key)
                if m:
                    # Auto-repeat Windows (tasta ținută apăsată) -> ignorăm repetările
                    if m not in held:
                        held[m] = False
                    return

                for mm in held:
                    held[mm] = True
                name = key.name if isinstance(key, kb.Key) else None
                altgr = 'altgr' in held
                mods = [mm for mm in MOD_ORDER if mm in held and not (altgr and mm in ('ctrl', 'alt'))]

                # ---- Pași VIRTUALI (nu se execută acum, doar la redare)
                vk = getattr(key, 'vk', None)
                if name == 'f8' or vk == 192 or getattr(key, 'char', None) in ('`', '~'):
                    self._record_virtual_step('smart', ctrl='ctrl' in mods, shift='shift' in mods)
                    return
                if name == 'f7':
                    self._record_virtual_step('dblclick' if 'ctrl' in mods else 'click')
                    return
                if name in APP_KEYS:
                    return

                ch = getattr(key, 'char', None)
                real_mods = [mm for mm in mods if mm != 'shift']

                if not real_mods and ch and ch.isprintable():
                    # Text normal (inclusiv litere mari cu Shift și diacritice cu AltGr)
                    self.add_step(Step("SendKeys", {"text": ch}))
                else:
                    base = keycode_base_name(key)
                    if not base:
                        return
                    combo = mods + [base] if mods else [base]
                    self.add_step(Step("Hotkey", {"combo": combo}))
                self.ui_queue.put(("refresh", None))
            except Exception as e:
                print(f"[CTRL] Error recording key: {e}")

        # ---- Windows: tastele VIRTUALE (F7, F8, `~) sunt BLOCATE în timpul înregistrării,
        # ca să nu ajungă la programul din față (ex: în Total Commander F8 = Ștergere,
        # iar ` ar apărea scris în caseta de chat). Se înregistrează direct de aici.
        virt_down = set()

        def kb_filter(msg, data):
            suppress = False
            try:
                if not self.recording or self.playing:
                    return True
                if data.flags & 0x12:            # LLKHF_INJECTED / LOWER_IL_INJECTED (generat de program)
                    return True
                vk, sc = int(data.vkCode), int(data.scanCode)
                is_tilde = vk == 192 or sc == 0x29   # tasta `~ de lângă 1 (orice layout)
                if vk in (118, 119) or is_tilde:
                    suppress = True
                    kid = 'tilde' if is_tilde else vk
                    if msg in (0x100, 0x104):        # WM_KEYDOWN / WM_SYSKEYDOWN
                        if kid not in virt_down:     # fără auto-repeat (tasta ținută apăsată)
                            virt_down.add(kid)
                            for mm in held:
                                held[mm] = True
                            if vk == 118:
                                self._record_virtual_step('dblclick' if 'ctrl' in held else 'click')
                            else:
                                self._record_virtual_step('smart', ctrl='ctrl' in held, shift='shift' in held)
                    else:
                        virt_down.discard(kid)
            except Exception as e:
                print(f"[CTRL] kb_filter error: {e}")
            if suppress:
                self._kb_listener.suppress_event()   # aruncă excepția internă pynput -> tasta e blocată
            return True

        self._mouse_listener = mouse.Listener(on_click=on_click)
        if _IS_WIN:
            self._kb_listener = kb.Listener(on_press=on_press, on_release=on_release, win32_event_filter=kb_filter)
        else:
            self._kb_listener = kb.Listener(on_press=on_press, on_release=on_release)
        self._mouse_listener.start()
        self._kb_listener.start()
        print("[CTRL] Mouse and keyboard listeners started")

    def _record_virtual_step(self, what: str, ctrl: bool = False, shift: bool = False):
        """Pași VIRTUALI — nimic nu se apasă acum, acțiunea se execută doar la redare / la ora programată.
        F8 sau ` ~  ('smart'):
            • mouse pe o iconiță / un buton (cursor săgeată sau mânuță) -> CLIC acolo
            • mouse pe o casetă de text (cursor „I”)                   -> CLIC în casetă + ENTER
            • Shift + tasta -> doar ENTER   • Ctrl + tasta -> DUBLU-CLIC
        F7 = CLIC la mouse; Ctrl+F7 = DUBLU-CLIC."""
        if what == 'smart':
            if ctrl:
                what = 'dblclick'
            elif shift:
                what = 'enter'
            elif cursor_is_text_ibeam():
                what = 'click+enter'
            else:
                what = 'click'
        if what == 'enter':
            step = Step("Hotkey", {"combo": ["enter"], "virtual": True})
            msg = "⏎ ENTER înregistrat (NU a fost apăsat acum — se va apăsa la redare / la ora programată)"
        elif what == 'click+enter':
            x, y = pyautogui.position()
            click = Step("ClickAt", {"x": int(x), "y": int(y), "button": "left", "virtual": True})
            enter = Step("Hotkey", {"combo": ["enter"], "virtual": True}, timestamp=click.timestamp + 0.4)
            self.steps.append(click)
            step = enter
            msg = (f"🎯⏎ CLIC în caseta de text la ({x}, {y}) + ENTER înregistrate pe '{window_title_at(x, y)}' "
                   f"(NU au fost apăsate acum — se vor apăsa la redare / la ora programată)")
        else:
            x, y = pyautogui.position()
            args = {"x": int(x), "y": int(y), "button": "left", "virtual": True}
            if what == 'dblclick':
                args["clicks"] = 2
            step = Step("ClickAt", args)
            label = "DUBLU-CLIC" if what == 'dblclick' else "CLIC"
            msg = (f"🎯 {label} înregistrat la ({x}, {y}) pe '{window_title_at(x, y)}' "
                   f"(NU a fost apăsat acum — se va apăsa la redare / la ora programată)")
        self.steps.append(step)
        self.log(msg)
        print(f"[CTRL] Virtual step: {step.describe()}")
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_OK)
        except Exception:
            pass
        self.ui_queue.put(("refresh", None))

    def stop_recording(self):
        if not self.recording:
            return
        self.recording = False
        self.log("⏹ Recording stopped")
        print("[CTRL] Recording STOPPED")
        try:
            if self._mouse_listener:
                self._mouse_listener.stop()
        except Exception:
            pass
        try:
            if self._kb_listener:
                self._kb_listener.stop()
        except Exception:
            pass
        self._mouse_listener = None
        self._kb_listener = None

        # --- Trimitere automată a pașilor înregistrați în Schedule ---
        if self.steps:
            # Preluare mod de rulare: o singură dată ("once") dacă nu e bifat în ecranul principal
            assigned_run_mode = "continuous" if self.run_continuously else "once"
            now = datetime.now()
            cur_date = now.strftime("%Y-%m-%d")

            target_task = None
            # Căutăm prima sarcină care nu are pași definiți încă
            for t in self.schedule_config.tasks:
                if not t.steps and (not t.task_file or t.action_type == "current"):
                    target_task = t
                    break

            if target_task is None:
                if len(self.schedule_config.tasks) < 20:
                    new_num = len(self.schedule_config.tasks) + 1
                    target_task = ScheduledTask(
                        id=str(uuid.uuid4())[:8],
                        name=f"Sarcina {new_num}",
                        enabled=True,
                        action_type="steps",
                        playback_speed=self.playback_speed,
                        run_mode=assigned_run_mode,
                        days=set(),    # IMPORTANT: Nicio zi bifată până când utilizatorul alege ziua!
                        time_interval_enabled=True,
                        from_time="09:00",
                        to_time="17:00",
                        last_run_date=cur_date # Marcată pentru a preveni rularea accidentală imediată
                    )
                    self.schedule_config.tasks.append(target_task)
                else:
                    target_task = self.schedule_config.tasks[-1]

            target_task.steps = [asdict(s) for s in self.steps]
            target_task.action_type = "steps"
            target_task.run_mode = assigned_run_mode
            target_task.last_run_date = cur_date
            self.save_schedules_to_disk()

            mode_txt = "Continuu în interval" if assigned_run_mode == "continuous" else "O singură dată"
            self.log(f"📋 Înregistrarea ({len(self.steps)} pași) a fost salvată în Schedule ca '{target_task.name}' (Mod: {mode_txt}, Status: În așteptare programare).")

    # ----- Playback
    def play(self, indices: Optional[List[int]] = None):
        if self.playing:
            return
        if self.recording:
            # Redarea în timpul înregistrării reda chiar înregistrarea curentă, iar recorder-ul
            # re-înregistra clicurile redate -> sarcina se dubla și „o lua razna” (bug 25.11.2026)
            self.log("⛔ Redarea NU poate porni în timpul înregistrării. Opriți întâi înregistrarea cu F1.")
            return
        if not self.steps:
            self.log("ℹ️ No steps to play.")
            return

        self.playing = True
        self.paused = False
        run_ctx = self._run_ctx   # execuția din istoric care aparține ACESTEI redări (None = redare manuală)

        steps = self.steps if not indices else [self.steps[i] for i in sorted(indices) if 0 <= i < len(self.steps)]
        mode = "continuously" if self.run_continuously else (f"{self.loop_count} times" if self.loop_enabled else "once")
        self.log(f"▶️ Playing task {mode} (Speed: {self.playback_speed}x)")
        print(f"[CTRL] Will play {len(steps)} steps")

        def runner():
            try:
                def do_pass():
                    first_ts = steps[0].timestamp
                    last_rel = 0.0
                    for st in steps:
                        while self.paused and self.playing:
                            time.sleep(0.05)
                        if not self.playing:
                            return
                        rel = st.get_relative_time(first_ts)
                        delay = max(0.0, (rel - last_rel)) / max(0.01, self.playback_speed)
                        # Sleep întreruptibil în tranșe de 0.05s pentru oprire/reluare instantă
                        sleep_rem = delay
                        while sleep_rem > 0 and self.playing:
                            chunk = min(0.05, sleep_rem)
                            time.sleep(chunk)
                            sleep_rem -= chunk
                            while self.paused and self.playing:
                                time.sleep(0.05)
                        if not self.playing:
                            return
                        last_rel = rel
                        self.execute_step(st)

                if self.run_continuously:
                    it = 0
                    while self.playing:
                        it += 1
                        self.log(f"🔄 Continuous run iteration #{it}")
                        do_pass()
                        if not self.playing:
                            break
                else:
                    loops = self.loop_count if self.loop_enabled else 1
                    for i in range(loops):
                        if not self.playing:
                            break
                        if loops > 1:
                            self.log(f"🔄 Loop {i+1}/{loops}")
                        do_pass()

                if self.playing:
                    self.log("✅ Playback completed")
                    run_status = "✅ Finalizată"
                else:
                    reason = self._stop_reason or "manual"
                    run_status = ("⏹ Oprită (interval încheiat)" if reason == "interval"
                                  else "⏹ Oprită manual (ESC / Stop)")
                if run_ctx:
                    self._finish_run_record(run_status, ctx=run_ctx)
            except Exception as e:
                self.log(f"❌ Playback error: {e}")
                if run_ctx:
                    self._finish_run_record("❌ Eroare", f"Eroare la redare: {e}", ctx=run_ctx)
            finally:
                self.playing = False
                self.paused = False
                self._stop_reason = None
                self.ui_queue.put(("state", None))

        self._play_thread = threading.Thread(target=runner, daemon=True)
        self._play_thread.start()

    def toggle_pause(self):
        if self.playing:
            self.paused = not self.paused
            self.log("⏸ Paused" if self.paused else "▶️ Resumed")
            self.ui_queue.put(("state", None))

    def stop(self):
        if self.recording:
            self.stop_recording()
        if self.playing:
            self.playing = False
            self.paused = False
            self.log("⏹ Playback stopped")
            if hasattr(self, 'scheduler'):
                self.scheduler.user_stopped = True
                # Marcăm minutul OPRIRII (nu al pornirii), altfel o sarcină 'Continuu'
                # oprită manual într-un minut diferit de cel de start repornea în 0,5 secunde!
                self.scheduler._last_checked_minute = datetime.now().strftime("%H:%M")
                self.scheduler.active_task_id = None

    def execute_step(self, st: Step):
        k = st.kind
        a = st.args

        ctx = self._run_ctx
        if ctx:
            ctx['step_no'] += 1
            try:
                line = f"{datetime.now():%H:%M:%S} Pas {ctx['step_no']}: {st.describe()}"
                if k in ("ClickAt", "MoveMouse"):
                    line += f"  → sub cursor: {window_title_at(a.get('x', 0), a.get('y', 0))}"
                elif k in ("Hotkey", "SendKeys"):
                    line += f"  → fereastra activă: '{foreground_window_title()}'"
                if is_workstation_locked():
                    line += "  ⚠ WINDOWS BLOCAT!"
                self.history.append_detail(ctx['run_id'], line)
            except Exception:
                pass

        def adjusted_sleep(seconds):
            tot = seconds / max(0.01, self.playback_speed)
            rem = tot
            while rem > 0 and self.playing:
                chunk = min(0.05, rem)
                time.sleep(chunk)
                rem -= chunk
                while self.paused and self.playing:
                    time.sleep(0.05)

        if k == "Wait":
            adjusted_sleep(float(a.get("seconds", 0)))
        elif k == "LaunchPath":
            path = a.get("path", "").strip()
            args = a.get("args", "").strip()
            if not path:
                return
            if os.path.isfile(path) and not path.lower().endswith(".exe"):
                os.startfile(path)
            else:
                if args:
                    subprocess.Popen([path] + args.split())
                else:
                    subprocess.Popen([path])
            adjusted_sleep(float(a.get("post_wait", 0)))
        elif k == "MoveMouse":
            duration = float(a.get("duration", 0)) / max(0.01, self.playback_speed)
            pyautogui.moveTo(a.get("x", 0), a.get("y", 0), duration=duration)
        elif k == "ClickAt":
            clicks = max(1, int(a.get("clicks", 1) or 1))
            pyautogui.click(a.get("x", 0), a.get("y", 0), clicks=clicks, interval=0.12,
                            button=a.get("button", "left"))
        elif k == "SendKeys":
            text = a.get("text", "")
            interval = float(a.get("interval", 0)) / max(0.01, self.playback_speed)
            if interval == 0 and len(text) > 1:
                interval = 0.01 / max(0.01, self.playback_speed)
            if len(text) == 1 and 1 <= ord(text) <= 26:
                # Înregistrări vechi: Ctrl+litera era salvată ca un caracter de control (ex: Ctrl+A = '\x01')
                pyautogui.hotkey('ctrl', chr(96 + ord(text)), interval=0.05)
            elif text and all(32 <= ord(c) < 127 or c == '\n' for c in text):
                pyautogui.typewrite(text, interval=interval)
            elif text:
                type_unicode_text(text, interval=interval)   # diacritice: ă â î ș ț etc.
        elif k == "Hotkey":
            combo = [normalize_key_name(c) for c in a.get("combo", []) if str(c).strip()]
            # Înregistrări vechi: Ctrl / Shift apăsate SINGURE nu au efect — le sărim
            if combo and not (len(combo) == 1 and combo[0] in ('ctrl', 'shift')):
                if len(combo) == 1:
                    pyautogui.press(combo[0])
                else:
                    pyautogui.hotkey(*combo, interval=0.05)


# ============================ Task Events & Step Editor Dialogs ============================

def format_step_details(kind: str, args: dict) -> str:
    """Generează o descriere prietenoasă în limba română pentru fiecare tip de eveniment."""
    if kind == "ClickAt":
        btn = args.get("button", "left")
        btn_ro = "Stânga" if btn == "left" else ("Dreapta" if btn == "right" else "Mijloc")
        dbl = "Dublu-click" if int(args.get("clicks", 1) or 1) >= 2 else "Click"
        return f"{dbl} {btn_ro} la X={args.get('x', 0)}, Y={args.get('y', 0)}"
    elif kind == "MoveMouse":
        dur = float(args.get("duration", 0))
        return f"Mișcare mouse la X={args.get('x', 0)}, Y={args.get('y', 0)} (durată: {dur:.2f}s)"
    elif kind == "SendKeys":
        txt = args.get("text", "")
        return f"Scriere text: '{txt}'"
    elif kind == "Hotkey":
        combo = args.get("combo", [])
        combo_str = " + ".join(combo) if isinstance(combo, list) else str(combo)
        return f"Combinație taste: {combo_str}"
    elif kind == "Wait":
        sec = float(args.get("seconds", 0))
        return f"Pauză fixă: {sec:.2f} s"
    elif kind == "LaunchPath":
        p = args.get("path", "")
        a = args.get("args", "")
        return f"Lansare program: '{p}' {a}"
    return f"{kind}: {args}"


class StepEditDialog(tk.Toplevel):
    """Fereastră modală pentru editarea detaliată a unui pas / eveniment individual (clic, coordonate, durată, pauză)."""
    def __init__(self, parent, step_dict: dict, step_num: int, prev_delay: float, on_save_callback):
        super().__init__(parent)
        self.step_dict = step_dict
        self.step_num = step_num
        self.prev_delay = max(0.0, prev_delay)
        self.on_save_callback = on_save_callback

        self.title(f"Editare Pas #{step_num} — {step_dict.get('kind', 'Step')}")
        self.geometry("560x520")
        self.minsize(500, 450)
        self.transient(parent)
        self.grab_set()

        self.kind_var = tk.StringVar(value=step_dict.get('kind', 'ClickAt'))
        self.args = dict(step_dict.get('args', {}))

        self.x_var = tk.StringVar(value=str(self.args.get('x', 0)))
        self.y_var = tk.StringVar(value=str(self.args.get('y', 0)))
        self.button_var = tk.StringVar(value=str(self.args.get('button', 'left')))
        self.duration_var = tk.StringVar(value=str(self.args.get('duration', 0.1)))
        self.wait_sec_var = tk.StringVar(value=str(self.args.get('seconds', 1.0)))
        self.text_var = tk.StringVar(value=str(self.args.get('text', '')))
        self.key_interval_var = tk.StringVar(value=str(self.args.get('interval', 0.01)))
        combo_val = self.args.get('combo', [])
        self.hotkey_var = tk.StringVar(value=", ".join(combo_val) if isinstance(combo_val, list) else str(combo_val))
        self.path_var = tk.StringVar(value=str(self.args.get('path', '')))
        self.path_args_var = tk.StringVar(value=str(self.args.get('args', '')))
        self.delay_var = tk.StringVar(value=f"{self.prev_delay:.3f}")

        self._build_ui()
        self._center()

    def _center(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        px = self.master.winfo_rootx()
        py = self.master.winfo_rooty()
        pw = self.master.winfo_width()
        ph = self.master.winfo_height()
        self.geometry(f"+{max(10, px + (pw - w)//2)}+{max(10, py + (ph - h)//2)}")

    def _build_ui(self):
        top_box = ttk.Frame(self, padding=12)
        top_box.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(top_box)
        header.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header, text=f"✏️ Configurare Detaliată — Pas #{self.step_num}",
                  font=("Arial", 11, "bold")).pack(side=tk.LEFT)

        # Tip Eveniment
        type_row = ttk.Frame(top_box)
        type_row.pack(fill=tk.X, pady=4)
        ttk.Label(type_row, text="Tip Eveniment:", width=18, font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        types = ["ClickAt", "MoveMouse", "SendKeys", "Hotkey", "Wait", "LaunchPath"]
        cb_type = ttk.Combobox(type_row, textvariable=self.kind_var, values=types, state="readonly", width=18)
        cb_type.pack(side=tk.LEFT)
        cb_type.bind("<<ComboboxSelected>>", lambda e: self._on_type_changed())

        # Container câmpuri dinamice
        self.fields_container = ttk.LabelFrame(top_box, text="Parametri Eveniment (Coordonate / Acțiune)", padding=10)
        self.fields_container.pack(fill=tk.BOTH, expand=True, pady=6)

        # Pauză înainte de acest pas
        delay_lf = ttk.LabelFrame(top_box, text="⏱️ Pauză / Temporizare înainte de acest pas", padding=8)
        delay_lf.pack(fill=tk.X, pady=6)
        d_row = ttk.Frame(delay_lf)
        d_row.pack(fill=tk.X)
        ttk.Label(d_row, text="Pauză (secunde):", width=18).pack(side=tk.LEFT)
        e_del = ttk.Entry(d_row, textvariable=self.delay_var, width=12)
        e_del.pack(side=tk.LEFT, padx=5)
        ttk.Label(d_row, text="secunde așteptare de la pasul anterior", foreground="#555555").pack(side=tk.LEFT)
        ToolTip(e_del, "Dacă doriți ca acest pas să se execute mai rapid sau fără pauză lungă,\n"
                       "modificați această valoare (ex: 0.5s sau 1.0s în loc de 50s).")

        # Butoane salvare
        btn_bar = ttk.Frame(self, padding=(10, 10))
        btn_bar.pack(fill=tk.X, side=tk.BOTTOM)
        btn_save = ttk.Button(btn_bar, text="💾 Salvează Pasul", command=self._on_save)
        btn_save.pack(side=tk.RIGHT, padx=5)
        btn_cancel = ttk.Button(btn_bar, text="✕ Anulează", command=self.destroy)
        btn_cancel.pack(side=tk.RIGHT, padx=5)

        self._render_kind_fields()

    def _on_type_changed(self):
        self._render_kind_fields()

    def _render_kind_fields(self):
        for w in self.fields_container.winfo_children():
            w.destroy()

        kind = self.kind_var.get()

        if kind == "ClickAt":
            r1 = ttk.Frame(self.fields_container); r1.pack(fill=tk.X, pady=4)
            ttk.Label(r1, text="Coordonata X:", width=16).pack(side=tk.LEFT)
            ttk.Entry(r1, textvariable=self.x_var, width=10).pack(side=tk.LEFT, padx=4)
            ttk.Label(r1, text="pixeli").pack(side=tk.LEFT)

            r2 = ttk.Frame(self.fields_container); r2.pack(fill=tk.X, pady=4)
            ttk.Label(r2, text="Coordonata Y:", width=16).pack(side=tk.LEFT)
            ttk.Entry(r2, textvariable=self.y_var, width=10).pack(side=tk.LEFT, padx=4)
            ttk.Label(r2, text="pixeli").pack(side=tk.LEFT)

            r3 = ttk.Frame(self.fields_container); r3.pack(fill=tk.X, pady=4)
            ttk.Label(r3, text="Buton Mouse:", width=16).pack(side=tk.LEFT)
            ttk.Combobox(r3, textvariable=self.button_var, values=["left", "right", "middle"],
                         state="readonly", width=10).pack(side=tk.LEFT, padx=4)

            r_pick = ttk.Frame(self.fields_container); r_pick.pack(fill=tk.X, pady=(10, 4))
            self.btn_pick = ttk.Button(r_pick, text="🎯 Alege Coordonate de pe Ecran (2 secunde)",
                                       command=self._pick_screen_coords)
            self.btn_pick.pack(side=tk.LEFT)
            ToolTip(self.btn_pick, "Apasă butonul, apoi ai 2 secunde să plasezi cursorul mouse-ului\n"
                                   "pe ecran unde vrei noul clic. Coordonatele X și Y se vor prelua automat!")

        elif kind == "MoveMouse":
            r1 = ttk.Frame(self.fields_container); r1.pack(fill=tk.X, pady=4)
            ttk.Label(r1, text="Destinație X:", width=16).pack(side=tk.LEFT)
            ttk.Entry(r1, textvariable=self.x_var, width=10).pack(side=tk.LEFT, padx=4)
            ttk.Label(r1, text="pixeli").pack(side=tk.LEFT)

            r2 = ttk.Frame(self.fields_container); r2.pack(fill=tk.X, pady=4)
            ttk.Label(r2, text="Destinație Y:", width=16).pack(side=tk.LEFT)
            ttk.Entry(r2, textvariable=self.y_var, width=10).pack(side=tk.LEFT, padx=4)
            ttk.Label(r2, text="pixeli").pack(side=tk.LEFT)

            r3 = ttk.Frame(self.fields_container); r3.pack(fill=tk.X, pady=4)
            ttk.Label(r3, text="Durată Mișcare:", width=16).pack(side=tk.LEFT)
            ttk.Entry(r3, textvariable=self.duration_var, width=10).pack(side=tk.LEFT, padx=4)
            ttk.Label(r3, text="secunde (ex: 0.1s sau 0.5s)").pack(side=tk.LEFT)

            r_pick = ttk.Frame(self.fields_container); r_pick.pack(fill=tk.X, pady=(10, 4))
            self.btn_pick = ttk.Button(r_pick, text="🎯 Alege Coordonate de pe Ecran (2 secunde)",
                                       command=self._pick_screen_coords)
            self.btn_pick.pack(side=tk.LEFT)

        elif kind == "SendKeys":
            r1 = ttk.Frame(self.fields_container); r1.pack(fill=tk.X, pady=4)
            ttk.Label(r1, text="Text de tastat:", width=16).pack(side=tk.LEFT)
            ttk.Entry(r1, textvariable=self.text_var, width=32).pack(side=tk.LEFT, padx=4)

            r2 = ttk.Frame(self.fields_container); r2.pack(fill=tk.X, pady=4)
            ttk.Label(r2, text="Interval Taste:", width=16).pack(side=tk.LEFT)
            ttk.Entry(r2, textvariable=self.key_interval_var, width=10).pack(side=tk.LEFT, padx=4)
            ttk.Label(r2, text="secunde între caractere (ex: 0.01)").pack(side=tk.LEFT)

        elif kind == "Hotkey":
            r1 = ttk.Frame(self.fields_container); r1.pack(fill=tk.X, pady=4)
            ttk.Label(r1, text="Combinație Taste:", width=16).pack(side=tk.LEFT)
            ttk.Entry(r1, textvariable=self.hotkey_var, width=30).pack(side=tk.LEFT, padx=4)
            ttk.Label(r1, text="(ex: enter sau ctrl, c)").pack(side=tk.LEFT)

        elif kind == "Wait":
            r1 = ttk.Frame(self.fields_container); r1.pack(fill=tk.X, pady=4)
            ttk.Label(r1, text="Pauză (secunde):", width=16).pack(side=tk.LEFT)
            ttk.Entry(r1, textvariable=self.wait_sec_var, width=10).pack(side=tk.LEFT, padx=4)
            ttk.Label(r1, text="secunde").pack(side=tk.LEFT)

        elif kind == "LaunchPath":
            r1 = ttk.Frame(self.fields_container); r1.pack(fill=tk.X, pady=4)
            ttk.Label(r1, text="Cale Program:", width=16).pack(side=tk.LEFT)
            ttk.Entry(r1, textvariable=self.path_var, width=30).pack(side=tk.LEFT, padx=4)
            ttk.Button(r1, text="Răsfoiește...", command=self._browse_path).pack(side=tk.LEFT)

            r2 = ttk.Frame(self.fields_container); r2.pack(fill=tk.X, pady=4)
            ttk.Label(r2, text="Argumente:", width=16).pack(side=tk.LEFT)
            ttk.Entry(r2, textvariable=self.path_args_var, width=30).pack(side=tk.LEFT, padx=4)

    def _browse_path(self):
        fp = filedialog.askopenfilename(parent=self)
        if fp:
            self.path_var.set(fp)

    def _pick_screen_coords(self):
        if hasattr(self, 'btn_pick'):
            self.btn_pick.config(state="disabled")
        def step_count(rem):
            if rem > 0:
                if hasattr(self, 'btn_pick') and self.btn_pick.winfo_exists():
                    self.btn_pick.config(text=f"🎯 Pune mouse-ul... ({rem:.1f}s)")
                self.after(300, lambda: step_count(round(rem - 0.3, 1)))
            else:
                x, y = pyautogui.position()
                self.x_var.set(str(x))
                self.y_var.set(str(y))
                if hasattr(self, 'btn_pick') and self.btn_pick.winfo_exists():
                    self.btn_pick.config(text=f"✓ Coordonate preluate: ({x}, {y})", state="normal")
        step_count(2.0)

    def _on_save(self):
        kind = self.kind_var.get()
        new_args = {}

        try:
            if kind == "ClickAt":
                new_args["x"] = int(self.x_var.get().strip())
                new_args["y"] = int(self.y_var.get().strip())
                new_args["button"] = self.button_var.get().strip() or "left"
                if int(self.args.get("clicks", 1) or 1) >= 2:
                    new_args["clicks"] = int(self.args.get("clicks", 2))
            elif kind == "MoveMouse":
                new_args["x"] = int(self.x_var.get().strip())
                new_args["y"] = int(self.y_var.get().strip())
                new_args["duration"] = max(0.0, float(self.duration_var.get().strip()))
            elif kind == "SendKeys":
                new_args["text"] = self.text_var.get()
                new_args["interval"] = max(0.0, float(self.key_interval_var.get().strip()))
            elif kind == "Hotkey":
                raw = self.hotkey_var.get().strip()
                keys = [k.strip() for k in raw.split(",") if k.strip()]
                new_args["combo"] = keys if keys else [raw]
            elif kind == "Wait":
                new_args["seconds"] = max(0.0, float(self.wait_sec_var.get().strip()))
            elif kind == "LaunchPath":
                new_args["path"] = self.path_var.get().strip()
                new_args["args"] = self.path_args_var.get().strip()
                new_args["post_wait"] = 0.0

            new_delay = max(0.0, float(self.delay_var.get().strip()))
        except ValueError as e:
            messagebox.showerror("Eroare de Validare", f"Valoare numerică invalidă:\n{e}", parent=self)
            return

        self.step_dict["kind"] = kind
        self.step_dict["args"] = new_args
        if self.on_save_callback:
            self.on_save_callback(new_delay)
        self.destroy()


class TaskEventsEditorDialog(tk.Toplevel):
    """Panou complet pentru vizualizarea și editarea fiecărui eveniment din sarcina selectată."""
    def __init__(self, parent, task: ScheduledTask, controller: TaskController, on_save_callback=None):
        super().__init__(parent)
        self.parent_dialog = parent
        self.task = task
        self.ctrl = controller
        self.on_save_callback = on_save_callback

        self.title(f"Editor Evenimente & Traseu Mouse — {task.name}")
        self.geometry("980x640")
        self.minsize(860, 520)
        self.transient(parent)
        self.grab_set()

        # Copie de lucru a pașilor sarcinii
        self.steps_data: List[dict] = [s.copy() if isinstance(s, dict) else asdict(s) for s in task.steps]

        # Dacă sarcina nu are pași proprii încă, dar există pași în controller:
        if not self.steps_data and self.ctrl.steps:
            if messagebox.askyesno("Importă Pași",
                                   f"Sarcina '{task.name}' nu are pași proprii salvați încă.\n"
                                   f"Doriți să importați cei {len(self.ctrl.steps)} pași înregistrați din memoria aplicației?",
                                   parent=self):
                self.steps_data = [asdict(s) for s in self.ctrl.steps]

        self._build_ui()
        self._center()
        self._populate_events()
        self.after(200, self._poll_playback)

    def _center(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        px = self.master.winfo_rootx()
        py = self.master.winfo_rooty()
        pw = self.master.winfo_width()
        ph = self.master.winfo_height()
        self.geometry(f"+{max(10, px + (pw - w)//2)}+{max(10, py + (ph - h)//2)}")

    def _build_ui(self):
        main_box = ttk.Frame(self, padding=10)
        main_box.pack(fill=tk.BOTH, expand=True)

        # Header
        top_hdr = ttk.Frame(main_box)
        top_hdr.pack(fill=tk.X, pady=(0, 6))

        title_lbl = ttk.Label(top_hdr, text=f"📋 Editor Evenimente: {self.task.name}",
                              font=("Arial", 12, "bold"), foreground="#00008B")
        title_lbl.pack(side=tk.LEFT)

        self.lbl_count = ttk.Label(top_hdr, text="", font=("Arial", 9, "bold"), foreground="#4B0082")
        self.lbl_count.pack(side=tk.RIGHT)

        ttk.Label(main_box,
                  text="Dublu-click pe un rând pentru a edita coordonatele clic-ului, traseul mouse-ului sau pauza.\n"
                       "Folosiți butoanele de mai jos pentru a reordona, adăuga, șterge sau optimiza pauzele dintre pași.",
                  foreground="#444444", font=("Arial", 8)).pack(anchor='w', pady=(0, 6))

        # Tabel evenimente (Treeview)
        tree_frame = ttk.Frame(main_box)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=4)

        cols = ("#", "Time", "Delay", "Type", "Details")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="extended")
        self.tree.heading("#", text="#")
        self.tree.heading("Time", text="Timp (s)")
        self.tree.heading("Delay", text="Pauză (+s)")
        self.tree.heading("Type", text="Tip Eveniment")
        self.tree.heading("Details", text="Detalii (Coordonate / Acțiune)")

        self.tree.column("#", width=45, anchor='center')
        self.tree.column("Time", width=85, anchor='center')
        self.tree.column("Delay", width=95, anchor='center')
        self.tree.column("Type", width=120, anchor='w')
        self.tree.column("Details", width=580, anchor='w')

        sb_v = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb_v.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb_v.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<Double-1>", lambda e: self.edit_selected_step())
        self.tree.bind("<Delete>", lambda e: self.delete_selected_steps())

        # Bară acțiuni evenimente
        act_bar = ttk.Frame(main_box, padding=(0, 6))
        act_bar.pack(fill=tk.X)

        btn_edit = ttk.Button(act_bar, text="✏️ Editează Pasul", command=self.edit_selected_step)
        btn_edit.pack(side=tk.LEFT, padx=3)
        ToolTip(btn_edit, "Editează coordonatele, butonul, durata sau pauza pasului selectat (sau dublu-click pe rând).")

        btn_up = ttk.Button(act_bar, text="▲ Sus", width=8, command=self.move_step_up)
        btn_up.pack(side=tk.LEFT, padx=2)
        ToolTip(btn_up, "Mută pasul selectat mai sus în ordinea de execuție.")

        btn_down = ttk.Button(act_bar, text="▼ Jos", width=8, command=self.move_step_down)
        btn_down.pack(side=tk.LEFT, padx=2)
        ToolTip(btn_down, "Mută pasul selectat mai jos în ordinea de execuție.")

        btn_add = ttk.Button(act_bar, text="➕ Adaugă Pas Nou", command=self.add_step_dialog)
        btn_add.pack(side=tk.LEFT, padx=4)
        ToolTip(btn_add, "Adaugă un eveniment nou (clic, mișcare mouse, tastare, pauză) la poziția curentă.")

        btn_del = ttk.Button(act_bar, text="🗑️ Șterge Selectate", command=self.delete_selected_steps)
        btn_del.pack(side=tk.LEFT, padx=3)
        ToolTip(btn_del, "Șterge pașii selectați din serie.")

        # Buton optimizare pauze lungi
        btn_compress = ttk.Button(act_bar, text="⏱️ Comprimă Pauze Lungi (Max 2s)", command=self.compress_long_pauses)
        btn_compress.pack(side=tk.LEFT, padx=6)
        ToolTip(btn_compress, "Dacă între doi pași s-a înregistrat o pauză moartă mare (ex: 50s sau 25s),\n"
                              "acest buton o reduce automat la 1 secundă, făcând sarcina să ruleze instant!")

        # Butoane inferioare (Salvare & Test)
        bot_bar = ttk.Frame(main_box, padding=(0, 8))
        bot_bar.pack(fill=tk.X, side=tk.BOTTOM)

        btn_save = ttk.Button(bot_bar, text="💾 Salvează în Sarcină", command=self.save_and_close)
        btn_save.pack(side=tk.LEFT, padx=4)
        ToolTip(btn_save, "Aplică modificările aduse evenimentelor acestei sarcini.")

        btn_cancel = ttk.Button(bot_bar, text="✕ Închide", command=self.destroy)
        btn_cancel.pack(side=tk.LEFT, padx=4)

        self.btn_test = ttk.Button(bot_bar, text="▶ Testează Pașii", width=22, command=self.test_play_steps)
        self.btn_test.pack(side=tk.RIGHT, padx=4)
        ToolTip(self.btn_test, "Rulează imediat acești pași pentru a verifica clicurile și traseul mouse-ului.")

    def _populate_events(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        if not self.steps_data:
            self.lbl_count.config(text="0 pași înregistrați (Lista este goală)")
            return

        first_ts = self.steps_data[0].get('timestamp', time.time())
        prev_ts = first_ts
        total_time = 0.0

        for i, st in enumerate(self.steps_data):
            cur_ts = st.get('timestamp', prev_ts)
            rel_time = max(0.0, cur_ts - first_ts)
            delay = max(0.0, cur_ts - prev_ts)
            prev_ts = cur_ts
            total_time = rel_time

            kind = st.get('kind', 'Unknown')
            args = st.get('args', {})
            details_str = format_step_details(kind, args)

            delay_str = f"+{delay:.3f} s"
            if delay > 5.0:
                delay_str += " ⚠️"

            self.tree.insert('', 'end', iid=f"step_{i}", values=(
                i + 1,
                f"{rel_time:.3f} s",
                delay_str,
                kind,
                details_str
            ))

        self.lbl_count.config(text=f"Total: {len(self.steps_data)} pași | Durată: ~{total_time:.1f}s")

    def _normalize_timestamps(self):
        if not self.steps_data:
            return
        first_ts = self.steps_data[0].get('timestamp', time.time())
        cur_ts = first_ts
        self.steps_data[0]['timestamp'] = cur_ts
        for i in range(1, len(self.steps_data)):
            prev = self.steps_data[i - 1].get('timestamp', cur_ts)
            curr = self.steps_data[i].get('timestamp', prev + 0.5)
            delay = max(0.02, curr - prev) if curr >= prev else 0.5
            cur_ts = prev + delay
            self.steps_data[i]['timestamp'] = cur_ts

    def edit_selected_step(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Informație", "Selectați un pas pentru a-l edita (sau faceți dublu-click pe el).", parent=self)
            return
        idx = int(sel[0].split('_')[1])
        if not (0 <= idx < len(self.steps_data)):
            return

        st = self.steps_data[idx]
        first_ts = self.steps_data[0].get('timestamp', time.time())
        prev_ts = self.steps_data[idx - 1].get('timestamp', first_ts) if idx > 0 else first_ts
        cur_ts = st.get('timestamp', prev_ts)
        delay = max(0.0, cur_ts - prev_ts)

        def on_saved(new_delay):
            delta = new_delay - delay
            for k in range(idx, len(self.steps_data)):
                self.steps_data[k]['timestamp'] = self.steps_data[k].get('timestamp', time.time()) + delta
            self._populate_events()
            item_id = f"step_{idx}"
            if self.tree.exists(item_id):
                self.tree.selection_set(item_id)
                self.tree.focus(item_id)

        StepEditDialog(self, st, idx + 1, delay, on_saved)

    def move_step_up(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0].split('_')[1])
        if idx <= 0:
            return
        self.steps_data[idx - 1], self.steps_data[idx] = self.steps_data[idx], self.steps_data[idx - 1]
        self._normalize_timestamps()
        self._populate_events()
        new_id = f"step_{idx - 1}"
        if self.tree.exists(new_id):
            self.tree.selection_set(new_id)
            self.tree.focus(new_id)

    def move_step_down(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0].split('_')[1])
        if idx >= len(self.steps_data) - 1:
            return
        self.steps_data[idx + 1], self.steps_data[idx] = self.steps_data[idx], self.steps_data[idx + 1]
        self._normalize_timestamps()
        self._populate_events()
        new_id = f"step_{idx + 1}"
        if self.tree.exists(new_id):
            self.tree.selection_set(new_id)
            self.tree.focus(new_id)

    def add_step_dialog(self):
        sel = self.tree.selection()
        insert_idx = int(sel[0].split('_')[1]) + 1 if sel else len(self.steps_data)

        new_step = {
            "kind": "ClickAt",
            "args": {"x": 500, "y": 500, "button": "left"},
            "timestamp": time.time()
        }

        def on_saved(new_delay):
            self.steps_data.insert(insert_idx, new_step)
            self._normalize_timestamps()
            self._populate_events()
            new_id = f"step_{insert_idx}"
            if self.tree.exists(new_id):
                self.tree.selection_set(new_id)
                self.tree.focus(new_id)

        StepEditDialog(self, new_step, insert_idx + 1, 0.5, on_saved)

    def delete_selected_steps(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Informație", "Selectați unul sau mai mulți pași de șters.", parent=self)
            return
        indices = sorted([int(item.split('_')[1]) for item in sel], reverse=True)
        if not messagebox.askyesno("Confirmare Ștergere",
                                   f"Sigur doriți să ștergeți cei {len(indices)} pași selectați?",
                                   parent=self):
            return
        for idx in indices:
            del self.steps_data[idx]
        self._normalize_timestamps()
        self._populate_events()

    def compress_long_pauses(self):
        if len(self.steps_data) < 2:
            messagebox.showinfo("Informație", "Sarcina conține mai puțin de 2 pași.", parent=self)
            return

        count = 0
        first_ts = self.steps_data[0].get('timestamp', time.time())
        cur_ts = first_ts
        self.steps_data[0]['timestamp'] = cur_ts

        for i in range(1, len(self.steps_data)):
            prev_raw = self.steps_data[i - 1].get('timestamp', cur_ts)
            this_raw = self.steps_data[i].get('timestamp', prev_raw)
            delay = max(0.0, this_raw - prev_raw)
            if delay > 2.0:
                count += 1
                delay = 1.0  # comprimăm pauza la 1 secundă
            cur_ts += delay
            self.steps_data[i]['timestamp'] = cur_ts

        self._populate_events()
        if count > 0:
            messagebox.showinfo("Pauze Comprimate",
                                f"Au fost detectate și reduse {count} pauze lungi la 1.0 secundă.\n"
                                f"Traseul se va derula acum rapid și fără timpi morți de așteptare!",
                                parent=self)
        else:
            messagebox.showinfo("Informație",
                                "Nu au fost găsite pauze mai mari de 2.0 secunde în această sarcină.",
                                parent=self)

    def test_play_steps(self):
        if self.ctrl.playing:
            self.ctrl.stop()
            self.btn_test.config(text="▶ Testează Pașii")
            return

        if not self.steps_data:
            messagebox.showinfo("Informație", "Nu există pași de testat.", parent=self)
            return

        st_list = []
        for o in self.steps_data:
            st = Step(kind=o['kind'], args=o['args'])
            if 'timestamp' in o:
                st.timestamp = o['timestamp']
            st_list.append(st)

        self.ctrl.steps = st_list
        self.ctrl.playback_speed = max(0.1, float(self.task.playback_speed))
        self.ctrl.run_continuously = False
        self.ctrl.loop_enabled = False
        self.ctrl.loop_count = 1
        self.ctrl.play()
        self.btn_test.config(text="⏹ Oprește Testul")

    def _poll_playback(self):
        try:
            if hasattr(self, 'btn_test') and self.btn_test.winfo_exists():
                if self.ctrl.playing:
                    self.btn_test.config(text="⏹ Oprește Testul")
                else:
                    self.btn_test.config(text="▶ Testează Pașii")
        except Exception:
            pass
        self.after(200, self._poll_playback)

    def save_and_close(self):
        self.task.steps = [s.copy() for s in self.steps_data]
        self.task.action_type = "steps"
        if self.on_save_callback:
            self.on_save_callback()
        self.ctrl.log(f"💾 [EDITOR] Evenimentele sarcinii '{self.task.name}' au fost actualizate ({len(self.task.steps)} pași).")
        messagebox.showinfo("Salvat",
                            f"Evenimentele sarcinii '{self.task.name}' au fost actualizate cu succes ({len(self.task.steps)} pași).",
                            parent=self)
        self.destroy()


# ============================ Schedule Settings Window (Tabs) ============================

class ScheduleDialog(tk.Toplevel):
    def __init__(self, parent, schedule_config: ScheduleConfig, controller: TaskController):
        super().__init__(parent)
        self.title("Setări Programare (Scheduler)")
        self.geometry("1060x760")
        self.minsize(960, 700)
        self.resizable(True, True)

        self.parent_app = parent
        self.ctrl = controller
        # Copie de lucru: Nu recreăm automat Sarcina 1 dacă lista este goală!
        self.config_obj = schedule_config.copy()
        self.tasks: List[ScheduledTask] = self.config_obj.tasks

        self.current_selected_index: Optional[int] = 0 if self.tasks else None
        self.result: Optional[ScheduleConfig] = None
        # IMPORTANT: Suprimăm evenimentele pe durata construirii UI-ului!
        # Altfel, apelurile inițiale (ex: _on_tab1_time_enable_change din _build_tab1_ui)
        # suprascriu prima sarcină cu valorile implicite ale formularului (09:00-17:00, nicio zi)
        # înainte ca valorile reale să fie încărcate. (Bug: orele salvate se pierdeau la redeschidere)
        self._suppress_events = True
        self._drag_item: Optional[str] = None

        self.transient(parent)
        self.grab_set()

        self._init_variables()
        self._build_ui()
        self._center_window()

        # Încărcare inițială
        if self.tasks:
            self._sync_tab1_from_task(self.tasks[0])
            self._populate_tasks_tree()
            self._select_task_tab2(0)
        else:
            self._sync_tab1_from_task(None)
            self._populate_tasks_tree()
            self._clear_tab2_pane()

        self.after(250, self._poll_schedule_test_playback)

    def _on_dialog_enter(self, event=None):
        if self._is_tab1_active() or self.tasks:
            return None
        if isinstance(getattr(event, 'widget', None), tk.Text):
            return None
        self.on_save()
        return "break"

    def _is_tab1_active(self) -> bool:
        try:
            return str(self.notebook.select()) == str(self.tab1_frame)
        except Exception:
            return False

    def _center_window(self):
        self.update_idletasks()
        pw = self.parent_app.winfo_width()
        ph = self.parent_app.winfo_height()
        px = self.parent_app.winfo_rootx()
        py = self.parent_app.winfo_rooty()
        w = 1060
        h = 760
        x = max(10, px + (pw - w) // 2)
        y = max(10, py + (ph - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _init_variables(self):
        self.enable_global_var = tk.BooleanVar(value=self.config_obj.enabled)
        self.keep_awake_var = tk.BooleanVar(value=self.config_obj.keep_awake)
        self.auto_start_var = tk.BooleanVar(value=self.config_obj.auto_start)
        self.lock_check_var = tk.BooleanVar(value=self.config_obj.lock_check)
        self.capture_var = tk.BooleanVar(value=self.config_obj.capture_screens)
        # Amprenta programării la deschidere: doar sarcinile reprogramate pot rula din nou azi
        self._orig_sigs = {t.id: t.schedule_signature() for t in self.tasks}

        # Variabile Tab 1 (Formular Simplu)
        self.tab1_task_name_var = tk.StringVar(value="")
        self.tab1_day_vars = {
            'Monday': tk.BooleanVar(),
            'Tuesday': tk.BooleanVar(),
            'Wednesday': tk.BooleanVar(),
            'Thursday': tk.BooleanVar(),
            'Friday': tk.BooleanVar(),
            'Saturday': tk.BooleanVar(),
            'Sunday': tk.BooleanVar()
        }
        self.tab1_interval_enabled_var = tk.BooleanVar(value=True)
        self.tab1_from_time_var = tk.StringVar(value="09:00")
        self.tab1_to_time_var = tk.StringVar(value="17:00")
        self.tab1_run_continuous_var = tk.BooleanVar(value=self.ctrl.run_continuously)

        # Variabile Tab 2 (Formular Sarcini Multiple)
        self.tab2_enabled_var = tk.BooleanVar(value=True)
        self.tab2_name_var = tk.StringVar(value="")
        self.tab2_action_type_var = tk.StringVar(value="steps")
        self.tab2_task_file_var = tk.StringVar(value="")
        self.tab2_run_mode_var = tk.StringVar(value="once")
        self.tab2_speed_var = tk.DoubleVar(value=1.0)
        self.tab2_repeat_min_var = tk.IntVar(value=5)
        self.tab2_loop_count_var = tk.IntVar(value=1)
        self.tab2_day_vars = {
            'Monday': tk.BooleanVar(),
            'Tuesday': tk.BooleanVar(),
            'Wednesday': tk.BooleanVar(),
            'Thursday': tk.BooleanVar(),
            'Friday': tk.BooleanVar(),
            'Saturday': tk.BooleanVar(),
            'Sunday': tk.BooleanVar()
        }
        self.tab2_spec_date_enabled_var = tk.BooleanVar(value=False)
        self.tab2_spec_date_var = tk.StringVar(value="")
        self.tab2_interval_enabled_var = tk.BooleanVar(value=True)
        self.tab2_from_time_var = tk.StringVar(value="09:00")
        self.tab2_to_time_var = tk.StringVar(value="17:00")

    def _build_ui(self):
        main = ttk.Frame(self, padding=8)
        main.pack(fill=tk.BOTH, expand=True)

        # Tab Control principal (Notebook)
        self.notebook = ttk.Notebook(main)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Tab 1: Formular Simplu (Original + Run continuously + opțiuni adăugare)
        self.tab1_frame = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(self.tab1_frame, text="📅 Programare Simplă (O Sarcină)")
        self._build_tab1_ui(self.tab1_frame)

        # Tab 2: Sarcini Multiple & Manager
        self.tab2_frame = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(self.tab2_frame, text="📋 Sarcini Multiple & Manager")
        self._build_tab2_ui(self.tab2_frame)

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        # Enter în tab-ul 'Sarcini Multiple' cu lista GOALĂ = 'Salvează & Închide'
        self.bind("<Return>", self._on_dialog_enter)
        self.bind("<KP_Enter>", self._on_dialog_enter)

    # ======================== TAB 1: FORMULAR SIMPLU ========================

    def _build_tab1_ui(self, parent):
        # 1. Activare generală
        top_box = ttk.Frame(parent)
        top_box.pack(fill=tk.X, pady=(0, 10))

        cb_enable = ttk.Checkbutton(top_box, text="Activează Programarea (Scheduler Global)", variable=self.enable_global_var)
        cb_enable.pack(side=tk.LEFT)
        ToolTip(cb_enable, "Comutator General: Bifați pentru a porni Scheduler-ul automat. Dacă este debifat, nicio sarcină nu va rula automat.")

        self.tab1_task_indicator = ttk.Label(top_box, text="", font=("Arial", 9, "bold"), foreground="#4B0082")
        self.tab1_task_indicator.pack(side=tk.RIGHT)
        ToolTip(self.tab1_task_indicator, "Indică sarcina activă ale cărei setări sunt afișate în acest formular.")

        # 2. Zile (Days)
        lbl_days = ttk.Label(parent, text="Zile:")
        lbl_days.pack(anchor='w', pady=(0, 5))

        days_frame = ttk.LabelFrame(parent, padding=12)
        days_frame.pack(fill=tk.X, pady=(0, 12))

        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        for i, day in enumerate(days):
            var = self.tab1_day_vars[day]
            row = i // 2
            col = i % 2
            cb = ttk.Checkbutton(days_frame, text=DAY_RO[day], variable=var, command=self._on_tab1_fields_changed)
            cb.grid(row=row, column=col, sticky='w', padx=15, pady=4)
            ToolTip(cb, f"Bifați dacă doriți ca sarcina să se execute în ziua de {DAY_RO[day]}.\nIMPORTANT: Dacă nicio zi nu este bifată, sarcina NU va rula!")

        btn_days_row = ttk.Frame(days_frame)
        btn_days_row.grid(row=4, column=0, columnspan=2, pady=(10, 0))

        btn_today = ttk.Button(btn_days_row, text="📅 Doar Azi", command=self.tab1_select_today)
        btn_today.pack(side=tk.LEFT, padx=5)
        ToolTip(btn_today, "Selectează doar ziua de AZI.")

        btn_tomorrow = ttk.Button(btn_days_row, text="📅 Doar Mâine", command=self.tab1_select_tomorrow)
        btn_tomorrow.pack(side=tk.LEFT, padx=5)
        ToolTip(btn_tomorrow, "Selectează doar ziua de MÂINE.")

        btn_all_days = ttk.Button(btn_days_row, text="✓ Toate Zilele", command=self.tab1_select_all_days)
        btn_all_days.pack(side=tk.LEFT, padx=5)
        ToolTip(btn_all_days, "Selectează toate zilele din săptămână.")

        btn_clear_days = ttk.Button(btn_days_row, text="✕ Niciuna", command=self.tab1_clear_days)
        btn_clear_days.pack(side=tk.LEFT, padx=5)
        ToolTip(btn_clear_days, "Deselectează toate zilele.")

        # 3. Interval Orar (Time Interval)
        lbl_ti = ttk.Label(parent, text="Interval Orar (Opțional)")
        lbl_ti.pack(anchor='w', pady=(5, 5))

        time_frame = ttk.LabelFrame(parent, padding=12)
        time_frame.pack(fill=tk.X, pady=(0, 15))

        cb_time_enable = ttk.Checkbutton(time_frame, text="Activează intervalul orar",
                                         variable=self.tab1_interval_enabled_var,
                                         command=self._on_tab1_time_enable_change)
        cb_time_enable.pack(anchor='w', pady=(0, 8))
        ToolTip(cb_time_enable, "Bifați pentru a restrânge execuția la un anumit interval orar.")

        from_frame = ttk.Frame(time_frame); from_frame.pack(fill=tk.X, pady=3)
        ttk.Label(from_frame, text="De la ora:", width=12).pack(side=tk.LEFT)
        self.tab1_from_entry = ttk.Entry(from_frame, textvariable=self.tab1_from_time_var, width=12)
        self.tab1_from_entry.pack(side=tk.LEFT, padx=5)
        self.tab1_from_entry.bind("<KeyRelease>", lambda e: self._on_tab1_fields_changed())
        ToolTip(self.tab1_from_entry, "Ora de început (format HH:MM sau HH:MM:SS, ex: 12:16 sau 12:16:05, AM/PM).")
        ttk.Label(from_frame, text="(ex: 21:00 sau 21:16:05 = seara, 09:16:05 = dimineața)", foreground="gray").pack(side=tk.LEFT, padx=5)

        to_frame = ttk.Frame(time_frame); to_frame.pack(fill=tk.X, pady=3)
        ttk.Label(to_frame, text="Până la ora:", width=12).pack(side=tk.LEFT)
        self.tab1_to_entry = ttk.Entry(to_frame, textvariable=self.tab1_to_time_var, width=12)
        self.tab1_to_entry.pack(side=tk.LEFT, padx=5)
        self.tab1_to_entry.bind("<KeyRelease>", lambda e: self._on_tab1_fields_changed())
        ToolTip(self.tab1_to_entry, "Ora de sfârșit (format HH:MM sau HH:MM:SS, ex: 12:16 sau 12:16:05, AM/PM).")
        ttk.Label(to_frame, text="(ex: 08:00 sau 08:16:05 = dimineața, 20:16:05 = seara)", foreground="gray").pack(side=tk.LEFT, padx=5)

        lbl_overnight = ttk.Label(time_frame, text="⏰ Interval peste noapte: ex: 21:00 - 03:00 sau 21:00:00 - 03:00:00",
                                  foreground="blue", font=("Arial", 9))
        lbl_overnight.pack(anchor='w', pady=(6, 4))
        ToolTip(lbl_overnight, "Sunt acceptate și intervale peste noapte (ex: 21:00 - 03:00 sau 21:00:30 - 03:00:15).")

        lbl_same = ttk.Label(
            time_frame,
            text="Dacă 'De la ora' = 'Până la ora' (ex: 14:03:03 – 14:03:03), sarcina rulează O SINGURĂ DATĂ la acea secundă, chiar dacă redarea durează mai mult. "
                 "Între orele de start ale sarcinilor trebuie cel puțin 30 de secunde, altfel sarcina de mai târziu nu rulează.",
            foreground="#8B0000", font=("Arial", 8), wraplength=720, justify="left"
        )
        lbl_same.pack(anchor='w', pady=(2, 4))
        ToolTip(lbl_same, "From = To: o singură rulare completă la acea secundă.\n"
                          "Între sarcini trebuie cel puțin 30 de secunde diferență la From time.")

        # --- Checkbox Run continuously în Tab 1 ---
        cont_frame = ttk.Frame(time_frame)
        cont_frame.pack(fill=tk.X, pady=(6, 2))
        self.cb_tab1_continuous = ttk.Checkbutton(
            cont_frame,
            text="Rulează continuu în interval",
            variable=self.tab1_run_continuous_var,
            command=self._on_tab1_fields_changed
        )
        self.cb_tab1_continuous.pack(side=tk.LEFT)
        ToolTip(self.cb_tab1_continuous,
                "Bifați pentru ca sarcina să ruleze continuu în buclă pe toată durata intervalului orar (se oprește automat când se termină intervalul).\n\n"
                "IMPORTANT: Dacă această căsuță NU este bifată, sarcina se va derula O SINGURĂ DATĂ la ora programată!")

        ttk.Label(cont_frame, text="(Debifat = O SINGURĂ DATĂ; Bifat = Repetă continuu)",
                  foreground="#666666", font=("Arial", 8, "italic")).pack(side=tk.LEFT, padx=8)

        self._on_tab1_time_enable_change()

        # 4. Butoane Acțiuni Tab 1
        btn_bar = ttk.Frame(parent)
        btn_bar.pack(fill=tk.X, pady=(15, 0))

        btn_new_task = ttk.Button(btn_bar, text="➕ Sarcină Nouă", width=14, command=self.tab1_new_task)
        btn_new_task.pack(side=tk.LEFT, padx=5)
        ToolTip(btn_new_task, "Resetează formularul pentru o sarcină nouă, păstrând în memoria Scheduler-ului sarcina curentă.")

        btn_save_as_new = ttk.Button(btn_bar, text="💾 Salvează ca sarcină nouă", width=26, command=self.tab1_save_as_new_task)
        btn_save_as_new.pack(side=tk.LEFT, padx=5)
        ToolTip(btn_save_as_new, "Salvează setările curente ca o sarcină nouă în lista de Sarcini Multiple (Tab 2).")

        btn_save = ttk.Button(btn_bar, text="💾 Salvează", width=12, command=self.on_save)
        btn_save.pack(side=tk.RIGHT, padx=5)
        ToolTip(btn_save, "Salvează toate sarcinile pe disc și închide fereastra.")

        btn_cancel = ttk.Button(btn_bar, text="✕ Anulează", width=12, command=self.destroy)
        btn_cancel.pack(side=tk.RIGHT, padx=5)
        ToolTip(btn_cancel, "Închide fereastra fără a salva modificările recente.")

        self.tab1_btn_test = ttk.Button(btn_bar, text="▶ Testează", width=14, command=self.test_current_task)
        self.tab1_btn_test.pack(side=tk.RIGHT, padx=5)
        ToolTip(self.tab1_btn_test, "Rulează sau oprește testul pentru pașii acestei sarcini.")

    def tab1_select_today(self):
        today = datetime.now().strftime("%A")
        for day, var in self.tab1_day_vars.items():
            var.set(day == today)
        self._on_tab1_fields_changed()

    def tab1_select_tomorrow(self):
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%A")
        for day, var in self.tab1_day_vars.items():
            var.set(day == tomorrow)
        self._on_tab1_fields_changed()

    def tab1_select_all_days(self):
        for var in self.tab1_day_vars.values():
            var.set(True)
        self._on_tab1_fields_changed()

    def tab1_clear_days(self):
        for var in self.tab1_day_vars.values():
            var.set(False)
        self._on_tab1_fields_changed()

    def _on_tab1_time_enable_change(self):
        enabled = self.tab1_interval_enabled_var.get()
        st = 'normal' if enabled else 'disabled'
        self.tab1_from_entry.config(state=st)
        self.tab1_to_entry.config(state=st)
        self._on_tab1_fields_changed()

    def _sync_tab1_from_task(self, task: Optional[ScheduledTask]):
        self._suppress_events = True
        if task is None:
            self.tab1_task_indicator.config(text="Nicio sarcină configurată (Lista este goală)")
            for var in self.tab1_day_vars.values():
                var.set(False)
            self.tab1_interval_enabled_var.set(False)
            self.tab1_run_continuous_var.set(False)
            self._suppress_events = False
            return

        self.tab1_task_name_var.set(task.name)
        steps_info = f"({len(task.steps)} pași înreg.)" if task.steps else "(fără pași)"
        self.tab1_task_indicator.config(text=f"Sarcină activă: {task.name} {steps_info}")

        for d, var in self.tab1_day_vars.items():
            var.set(d in task.days)

        self.tab1_interval_enabled_var.set(task.time_interval_enabled)
        self.tab1_from_time_var.set(task.from_time)
        self.tab1_to_time_var.set(task.to_time)

        # Sincronizare mod continuu
        self.tab1_run_continuous_var.set(task.run_mode == "continuous")

        self._on_tab1_time_enable_change()
        self._suppress_events = False

    def _save_tab1_to_task(self, task: Optional[ScheduledTask]):
        if task is None:
            return
        task.days = {d for d, var in self.tab1_day_vars.items() if var.get()}
        task.time_interval_enabled = self.tab1_interval_enabled_var.get()
        task.from_time = self.tab1_from_time_var.get().strip() or "09:00"
        task.to_time = self.tab1_to_time_var.get().strip() or "17:00"
        if self.tab1_run_continuous_var.get():
            task.run_mode = "continuous"
        elif task.run_mode not in ("repeat", "loop"):
            task.run_mode = "once"

    def _mirror_tab2_schedule_from_task(self, task: ScheduledTask):
        """Actualizează în Tab 2 zilele și intervalul orar ale aceleiași sarcini, fără buclă de evenimente."""
        if not hasattr(self, "tab2_from_entry"):
            return
        self._suppress_events = True
        self.tab2_interval_enabled_var.set(task.time_interval_enabled)
        self.tab2_from_time_var.set(task.from_time)
        self.tab2_to_time_var.set(task.to_time)
        for d, var in self.tab2_day_vars.items():
            var.set(d in task.days)
        self.tab2_run_mode_var.set(task.run_mode)
        st = "normal" if task.time_interval_enabled else "disabled"
        self.tab2_from_entry.config(state=st)
        self.tab2_to_entry.config(state=st)
        self._suppress_events = False

    def _on_tab1_fields_changed(self):
        if self._suppress_events:
            return
        idx = self.current_selected_index
        if idx is not None and 0 <= idx < len(self.tasks):
            self._save_tab1_to_task(self.tasks[idx])
            self._mirror_tab2_schedule_from_task(self.tasks[idx])
            if hasattr(self, "task_tree"):
                self._update_tab2_current_row()

    def tab1_new_task(self):
        if len(self.tasks) >= 20:
            messagebox.showwarning("Limită atinsă", "Puteți programa maximum 20 de sarcini independente.", parent=self)
            return

        # 1. Salvează sarcina curentă dacă există
        idx = self.current_selected_index
        if idx is not None and 0 <= idx < len(self.tasks):
            self._save_tab1_to_task(self.tasks[idx])

        # 2. Creează sarcina nouă cu modul pe baza 'Run continuously' din formularul principal
        new_name = f"Sarcina {len(self.tasks) + 1}"
        init_mode = "continuous" if self.ctrl.run_continuously else "once"
        new_task = ScheduledTask(
            id=str(uuid.uuid4())[:8],
            name=new_name,
            enabled=True,
            action_type="steps",
            steps=[asdict(s) for s in self.ctrl.steps] if self.ctrl.steps else [],
            run_mode=init_mode,
            days=set(),
            time_interval_enabled=True,
            from_time="09:00",
            to_time="17:00"
        )
        self.tasks.append(new_task)
        self.current_selected_index = len(self.tasks) - 1

        # 3. Sincronizează Tab 1 cu sarcina nouă
        self._sync_tab1_from_task(new_task)
        self.ctrl.log(f"➕ Sarcină nouă creată în Schedule: '{new_name}' (Mod: {'Continuu' if init_mode == 'continuous' else 'O singură dată'}).")
        messagebox.showinfo("Sarcină Nouă", f"'{new_name}' a fost creată și este gata pentru configurare!\nSarcina anterioară a fost păstrată în memorie.", parent=self)

    def tab1_save_as_new_task(self):
        if len(self.tasks) >= 20:
            messagebox.showwarning("Limită atinsă", "Puteți programa maximum 20 de sarcini independente.", parent=self)
            return

        new_name = f"Sarcina {len(self.tasks) + 1}"
        chosen_mode = "continuous" if self.tab1_run_continuous_var.get() else "once"
        new_task = ScheduledTask(
            id=str(uuid.uuid4())[:8],
            name=new_name,
            enabled=True,
            action_type="steps",
            steps=[asdict(s) for s in self.ctrl.steps] if self.ctrl.steps else [],
            run_mode=chosen_mode,
            days={d for d, var in self.tab1_day_vars.items() if var.get()},
            time_interval_enabled=self.tab1_interval_enabled_var.get(),
            from_time=self.tab1_from_time_var.get().strip() or "09:00",
            to_time=self.tab1_to_time_var.get().strip() or "17:00"
        )
        self.tasks.append(new_task)
        self.current_selected_index = len(self.tasks) - 1
        self._sync_tab1_from_task(new_task)
        self.ctrl.log(f"💾 Sarcina a fost salvată ca sarcină nouă: '{new_name}' (Mod: {'Continuu' if chosen_mode == 'continuous' else 'O singură dată'}).")
        messagebox.showinfo("Salvat", f"Sarcina a fost adăugată în lista din Tab 2 ca '{new_name}'.", parent=self)

    # ======================== TAB 2: SARCINI MULTIPLE ========================

    def _build_tab2_ui(self, parent):
        # Header: Global scheduler toggle & status
        header = ttk.LabelFrame(parent, text="Stare Generală Scheduler", padding=8)
        header.pack(fill=tk.X, pady=(0, 6))

        cb_master = ttk.Checkbutton(header, text="Activează Scheduler Global (Master On/Off)",
                                    variable=self.enable_global_var)
        cb_master.pack(side=tk.LEFT)
        ToolTip(cb_master, "Comutator General: Când este activ, toate sarcinile marcate ca 'Active' vor rula la orele programate.")

        self.tab2_stats_label = ttk.Label(header, text="", font=("Arial", 9, "bold"), foreground="#4B0082")
        self.tab2_stats_label.pack(side=tk.RIGHT, padx=10)

        opts = ttk.Frame(parent)
        opts.pack(fill=tk.X, pady=(0, 4))
        cb_awake = ttk.Checkbutton(opts, text="☕ Ține PC-ul și ecranul treze (fără Sleep/Standby)", variable=self.keep_awake_var)
        cb_awake.pack(side=tk.LEFT, padx=(4, 10))
        ToolTip(cb_awake, "RECOMANDAT. Cât timp Scheduler-ul este ON, Windows nu mai intră în Sleep / Modern Standby\n"
                          "și nu mai stinge ecranul, deci nu mai apare ecranul de blocare (cu parolă).\n"
                          "Fără această opțiune, noaptea PC-ul dormea, iar clicurile ajungeau pe ecranul de blocare.\n"
                          "Notă: închiderea capacului laptopului îl adoarme oricum.")
        cb_lock = ttk.Checkbutton(opts, text="🔒 Verifică ecranul de blocare", variable=self.lock_check_var)
        cb_lock.pack(side=tk.LEFT, padx=(0, 10))
        ToolTip(cb_lock, "Înainte de rulare aprinde ecranul și verifică dacă Windows este blocat.\n"
                         "Dacă da, NU trimite clicuri în gol: reîncearcă la fiecare 30 s, timp de 5 minute,\n"
                         "și notează în Istoric 'Amânată' sau 'Ratată (PC blocat)'.")
        cb_auto = ttk.Checkbutton(opts, text="🚀 Pornește Scheduler-ul automat la deschidere", variable=self.auto_start_var)
        cb_auto.pack(side=tk.LEFT, padx=(0, 10))
        ToolTip(cb_auto, "Dacă aplicația este repornită (ex: după un restart Windows), Scheduler-ul\n"
                         "revine singur la starea ON salvată. Fără bifă, pornește mereu OPRIT.")
        cb_cap = ttk.Checkbutton(opts, text="📷 Capturi ecran", variable=self.capture_var)
        cb_cap.pack(side=tk.LEFT)
        ToolTip(cb_cap, "Salvează o captură de ecran la începutul și la sfârșitul fiecărei rulări\n"
                        "(folderul 'istoric_capturi'), ca să vedeți ce era pe ecran și unde au nimerit clicurile.")

        # Paned Window (Stânga: Lista sarcini, Dreapta: Editare detaliată)
        paned = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, pady=4)

        left_frame = ttk.Frame(paned, padding=4)
        right_frame = ttk.Frame(paned, padding=4)
        paned.add(left_frame, weight=1)
        paned.add(right_frame, weight=2)

        self._build_tab2_left(left_frame)
        self._build_tab2_right(right_frame)

        # Bottom Bar Tab 2
        bottom_bar = ttk.Frame(parent, padding=(0, 6))
        bottom_bar.pack(fill=tk.X)

        btn_save = ttk.Button(bottom_bar, text="💾 Salvează & Închide", width=20, command=self.on_save)
        btn_save.pack(side=tk.LEFT, padx=4)
        ToolTip(btn_save, "Salvează lista de sarcini (adăugare, redenumire, ștergere, activare, duplicare) pe disc și închide fereastra.\n"
                          "Când lista de sarcini este goală, tasta Enter apasă acest buton.")

        btn_cancel = ttk.Button(bottom_bar, text="✕ Anulează", width=12, command=self.destroy)
        btn_cancel.pack(side=tk.LEFT, padx=4)
        ToolTip(btn_cancel, "Închide fereastra fără salvare.")

        self.tab2_btn_test = ttk.Button(bottom_bar, text="▶ Testează Sarcina Acum", width=25, command=self.test_current_task)
        self.tab2_btn_test.pack(side=tk.RIGHT, padx=4)

        btn_hist = ttk.Button(bottom_bar, text="📜 Istoric Execuții", width=20,
                              command=lambda: HistoryWindow.open(self, self.ctrl))
        btn_hist.pack(side=tk.RIGHT, padx=4)
        ToolTip(btn_hist, "Arată toate execuțiile sarcinilor: când au pornit, dacă s-au terminat, au fost amânate (PC blocat)\n"
                          "sau ratate (PC în Standby), plus fiecare pas și fereastra în care a nimerit fiecare clic.")
        ToolTip(self.tab2_btn_test, "Rulează sau oprește testul pentru pașii sarcinii selectate.")

    def _build_tab2_left(self, parent):
        top_bar = ttk.Frame(parent)
        top_bar.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(top_bar, text="📋 Sarcini Programate (Maxim 20):", font=("Arial", 9, "bold")).pack(side=tk.LEFT)

        tree_container = ttk.Frame(parent)
        tree_container.pack(fill=tk.BOTH, expand=True)

        cols = ("#", "Status", "Name", "Interval", "Zile", "Sursă")
        self.task_tree = ttk.Treeview(tree_container, columns=cols, show="headings", selectmode="extended")
        self.task_tree.heading("#", text="#")
        self.task_tree.heading("Status", text="Status")
        self.task_tree.heading("Name", text="Nume Sarcină")
        self.task_tree.heading("Interval", text="Interval")
        self.task_tree.heading("Zile", text="Zile")
        self.task_tree.heading("Sursă", text="Sursă")

        self.task_tree.column("#", width=28, anchor='center')
        self.task_tree.column("Status", width=68, anchor='center')
        self.task_tree.column("Name", width=125, anchor='w')
        self.task_tree.column("Interval", width=155, minwidth=120, anchor='center')
        self.task_tree.column("Zile", width=85, anchor='w')
        self.task_tree.column("Sursă", width=110, anchor='w')

        sb = ttk.Scrollbar(tree_container, orient="vertical", command=self.task_tree.yview)
        self.task_tree.configure(yscrollcommand=sb.set)
        self.task_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        ToolTip(self.task_tree, "Faceți clic pe o sarcină pentru a-i vizualiza și edita detaliile.\n"
                                "Click DREAPTA pe o sarcină = Redenumește sarcina.\n"
                                "Tasta DELETE pe sarcina selectată = Șterge sarcina (cu confirmare).\n"
                                "Shift+Click / Ctrl+Click = selectați mai multe sarcini (pentru ștergere).\n"
                                "Trageți cu mouse-ul (Drag & Drop) o sarcină pentru a o muta în ordinea dorită.")

        self.task_tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.task_tree.bind("<Double-1>", self._on_tree_double_click)
        # Click dreapta pe o sarcină = deschide fereastra 'Redenumește Sarcină'
        self.task_tree.bind("<Button-3>", self._on_tree_right_click)
        # Tasta Delete pe o sarcină selectată = exact ca butonul '🗑️ Șterge' (cu confirmare)
        self.task_tree.bind("<Delete>", self._on_tree_delete_key)
        # Drag & Drop pentru reordonarea sarcinilor
        self.task_tree.bind("<ButtonPress-1>", self._on_tree_drag_start)
        self.task_tree.bind("<B1-Motion>", self._on_tree_drag_motion)
        self.task_tree.bind("<ButtonRelease-1>", self._on_tree_drag_drop)

        # Butoane gestionare sarcini
        btn_box = ttk.Frame(parent, padding=(0, 4))
        btn_box.pack(fill=tk.X)

        row1 = ttk.Frame(btn_box); row1.pack(fill=tk.X, pady=2)
        self.btn_add = ttk.Button(row1, text="➕ Adaugă Sarcină", command=self.add_task_tab2)
        self.btn_add.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        ToolTip(self.btn_add, "Adaugă o sarcină nouă în listă (până la 20 de sarcini).")

        self.btn_del = ttk.Button(row1, text="🗑️ Șterge", command=self.delete_task_tab2)
        self.btn_del.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        ToolTip(self.btn_del, "Șterge definitiv sarcinile selectate (orice sarcină, inclusiv Sarcina 1, fără să mai revină).\n"
                              "Puteți selecta mai multe sarcini cu Shift+Click sau Ctrl+Click.")

        row2 = ttk.Frame(btn_box); row2.pack(fill=tk.X, pady=2)
        btn_ren = ttk.Button(row2, text="✏️ Redenumește", command=self.rename_task_tab2)
        btn_ren.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        ToolTip(btn_ren, "Redenumește sarcina selectată.")

        btn_dup = ttk.Button(row2, text="📋 Duplică", command=self.duplicate_task_tab2)
        btn_dup.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        ToolTip(btn_dup, "Creează o copie identică a sarcinii selectate.")

        row3 = ttk.Frame(btn_box); row3.pack(fill=tk.X, pady=2)
        btn_toggle = ttk.Button(row3, text="⏸️ Activează / Anulează", command=self.toggle_task_tab2)
        btn_toggle.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        ToolTip(btn_toggle, "Comută sarcina selectată între Activă și Anulată (nu se șterge, doar este pusă pe pauză).")

        btn_up = ttk.Button(row3, text="▲", width=4, command=self.move_task_up_tab2)
        btn_up.pack(side=tk.LEFT, padx=1)
        ToolTip(btn_up, "Mută sarcina mai sus în listă.")

        btn_down = ttk.Button(row3, text="▼", width=4, command=self.move_task_down_tab2)
        btn_down.pack(side=tk.LEFT, padx=1)
        ToolTip(btn_down, "Mută sarcina mai jos în listă.")

        row4 = ttk.Frame(btn_box); row4.pack(fill=tk.X, pady=2)
        self.btn_edit_events = ttk.Button(row4, text="📝 Editează Evenimentele Sarcinii", command=self.open_task_events_editor)
        self.btn_edit_events.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        ToolTip(self.btn_edit_events, "Deschide panoul cu fiecare eveniment (clic, coordonate, traseu mouse, tastatură, pauze) pentru sarcina selectată.\n"
                                      "Sau faceți DUBLE-CLICK direct pe rândul sarcinii în tabel!")

    def _build_tab2_right(self, parent):
        # Canvas cu Scrollbar pentru derulare lină cu mouse-ul
        canvas_container = ttk.Frame(parent)
        canvas_container.pack(fill=tk.BOTH, expand=True)

        self.right_canvas = tk.Canvas(canvas_container, highlightthickness=0, bg="#F5E9FF")
        self.right_sb = ttk.Scrollbar(canvas_container, orient="vertical", command=self.right_canvas.yview)
        self.right_canvas.configure(yscrollcommand=self.right_sb.set)

        self.right_scrollable_frame = ttk.Frame(self.right_canvas)
        self.right_scrollable_window = self.right_canvas.create_window((0, 0), window=self.right_scrollable_frame, anchor="nw")

        self.right_scrollable_frame.bind("<Configure>", lambda e: self.right_canvas.configure(scrollregion=self.right_canvas.bbox("all")))
        self.right_canvas.bind("<Configure>", lambda e: self.right_canvas.itemconfig(self.right_scrollable_window, width=e.width))

        self.right_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.right_sb.pack(side=tk.RIGHT, fill=tk.Y)

        self.tab2_details_lf = ttk.LabelFrame(self.right_scrollable_frame, text="⚙️ Configurare Sarcină Selectată", padding=8)
        self.tab2_details_lf.pack(fill=tk.BOTH, expand=True)

        # 1. Nume & Activare
        top_row = ttk.Frame(self.tab2_details_lf); top_row.pack(fill=tk.X, pady=(0, 6))
        cb_task_act = ttk.Checkbutton(top_row, text=" Sarcină Activă (Bifat = Programat, Debifat = Anulat/Pauză)",
                                      variable=self.tab2_enabled_var, command=self._on_tab2_field_changed)
        cb_task_act.pack(side=tk.LEFT)
        ToolTip(cb_task_act, "Dacă este bifat, sarcina va fi luată în considerare de Scheduler. Dacă este debifat, sarcina este anulată/în pauză.")

        name_box = ttk.Frame(self.tab2_details_lf); name_box.pack(fill=tk.X, pady=3)
        ttk.Label(name_box, text="Nume Sarcină:", width=14, font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        self.tab2_name_entry = ttk.Entry(name_box, textvariable=self.tab2_name_var)
        self.tab2_name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.tab2_name_entry.bind("<KeyRelease>", lambda e: self._on_tab2_name_modified())
        ToolTip(self.tab2_name_entry, "Puteți redenumi sarcina introducând numele dorit direct aici.")

        # 2. Acțiunea de executat
        action_lf = ttk.LabelFrame(self.tab2_details_lf, text="📁 Ce acțiune execută mouse-ul/tastatura?", padding=6)
        action_lf.pack(fill=tk.X, pady=5)

        r_steps = ttk.Radiobutton(action_lf, text="Rulează pașii înregistrați proprii acestei sarcini:",
                                  variable=self.tab2_action_type_var, value="steps", command=self._on_tab2_field_changed)
        r_steps.pack(anchor='w')
        ToolTip(r_steps, "Folosește pașii înregistrați cu mouse-ul și tastatura asociați acestei sarcini.")

        self.tab2_steps_info_label = ttk.Label(action_lf, text="", foreground="#00008B", font=("Arial", 9))
        self.tab2_steps_info_label.pack(anchor='w', padx=20, pady=(1, 4))

        btn_open_events = ttk.Button(action_lf, text="📝 Deschide Editorul de Evenimente (Dublu-Click pe Sarcină)",
                                     command=self.open_task_events_editor)
        btn_open_events.pack(anchor='w', padx=20, pady=(0, 6))
        ToolTip(btn_open_events, "Vizualizați și modificați coordonatele X/Y ale fiecărui clic, traseul mouse-ului, pauzele sau tastarea.")

        r_file = ttk.Radiobutton(action_lf, text="Rulează un fișier de sarcini (.json) salvat:",
                                 variable=self.tab2_action_type_var, value="file", command=self._on_tab2_field_changed)
        r_file.pack(anchor='w')
        ToolTip(r_file, "Încarcă și rulează pașii dintr-un fișier .json salvat pe disc.")

        file_row = ttk.Frame(action_lf); file_row.pack(fill=tk.X, pady=(2, 4), padx=20)
        self.tab2_file_combo = ttk.Combobox(file_row, textvariable=self.tab2_task_file_var, width=32)
        self.tab2_file_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.tab2_file_combo.bind("<<ComboboxSelected>>", lambda e: self._on_tab2_field_changed())
        ToolTip(self.tab2_file_combo, "Alegeți un fișier .json din directorul curent.")

        btn_browse = ttk.Button(file_row, text="📂 Răsfoiește...", width=14, command=self.browse_task_file_tab2)
        btn_browse.pack(side=tk.LEFT, padx=3)
        ToolTip(btn_browse, "Răsfoiește computerul pentru a alege orice fișier .json.")

        btn_save_steps = ttk.Button(file_row, text="💾 Salvează ca fișier...", command=self.save_steps_as_file_tab2)
        btn_save_steps.pack(side=tk.LEFT, padx=2)
        ToolTip(btn_save_steps, "Exportă pașii acestei sarcini într-un fișier nou .json.")

        r_curr = ttk.Radiobutton(action_lf, text="Rulează evenimentele încărcate în prezent în aplicație",
                                 variable=self.tab2_action_type_var, value="current", command=self._on_tab2_field_changed)
        r_curr.pack(anchor='w')
        ToolTip(r_curr, "Execută pașii aflați în memoria ecranului principal.")

        self._refresh_tab2_files_dropdown()

        # 3. Mod de Rulare & Viteză
        mode_lf = ttk.LabelFrame(self.tab2_details_lf, text="⚡ Mod de Rulare & Viteză Playback", padding=6)
        mode_lf.pack(fill=tk.X, pady=5)

        m_row2 = ttk.Frame(mode_lf); m_row2.pack(fill=tk.X, pady=2)
        r_once = ttk.Radiobutton(m_row2, text="O singură dată pe zi, la începutul intervalului",
                                 variable=self.tab2_run_mode_var, value="once", command=self._on_tab2_field_changed)
        r_once.pack(anchor='w')
        ToolTip(r_once, "Sarcina va rula o singură dată pe zi când ceasul intră în intervalul orar.")

        m_row1 = ttk.Frame(mode_lf); m_row1.pack(fill=tk.X, pady=2)
        r_cont = ttk.Radiobutton(m_row1, text="Rulează Continuu în intervalul orar (Se oprește automat la final de interval)",
                                 variable=self.tab2_run_mode_var, value="continuous", command=self._on_tab2_field_changed)
        r_cont.pack(anchor='w')
        ToolTip(r_cont, "Sarcina va rula continuu în buclă pe toată durata intervalului orar și se va opri automat când intervalul expiră.")

        m_row3 = ttk.Frame(mode_lf); m_row3.pack(fill=tk.X, pady=2)
        r_rep = ttk.Radiobutton(m_row3, text="Repetă la fiecare", variable=self.tab2_run_mode_var, value="repeat",
                                command=self._on_tab2_field_changed)
        r_rep.pack(side=tk.LEFT)
        ToolTip(r_rep, "Sarcina se va repeta la intervalul de minute specificat.")

        self.tab2_rep_spin = ttk.Spinbox(m_row3, from_=1, to=1440, width=5, textvariable=self.tab2_repeat_min_var,
                                         command=self._on_tab2_field_changed)
        self.tab2_rep_spin.pack(side=tk.LEFT, padx=4)
        self.tab2_rep_spin.bind("<KeyRelease>", lambda e: self._on_tab2_field_changed())
        ttk.Label(m_row3, text="minute în interiorul intervalului orar").pack(side=tk.LEFT)

        m_row4 = ttk.Frame(mode_lf); m_row4.pack(fill=tk.X, pady=2)
        r_loop = ttk.Radiobutton(m_row4, text="Rulează de", variable=self.tab2_run_mode_var, value="loop",
                                 command=self._on_tab2_field_changed)
        r_loop.pack(side=tk.LEFT)
        ToolTip(r_loop, "Sarcina va rula de N ori consecutiv la intrarea în interval.")

        self.tab2_loop_spin = ttk.Spinbox(m_row4, from_=1, to=999, width=5, textvariable=self.tab2_loop_count_var,
                                          command=self._on_tab2_field_changed)
        self.tab2_loop_spin.pack(side=tk.LEFT, padx=4)
        self.tab2_loop_spin.bind("<KeyRelease>", lambda e: self._on_tab2_field_changed())
        ttk.Label(m_row4, text="ori consecutiv").pack(side=tk.LEFT)

        speed_row = ttk.Frame(mode_lf); speed_row.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(speed_row, text="Viteză Playback:", width=14).pack(side=tk.LEFT)
        self.tab2_speed_slider = ttk.Scale(speed_row, from_=0.1, to=5.0, variable=self.tab2_speed_var,
                                           orient=tk.HORIZONTAL, length=180, command=self._on_tab2_speed_slider)
        self.tab2_speed_slider.pack(side=tk.LEFT, padx=4)
        self.tab2_speed_label = ttk.Label(speed_row, text="1.0x", width=6)
        self.tab2_speed_label.pack(side=tk.LEFT, padx=4)
        ToolTip(self.tab2_speed_slider, "Reglează viteza cu care se execută mișcările de mouse și tastele (0.1x până la 5.0x).")

        # 4. Zile de Rulare
        days_lf = ttk.LabelFrame(self.tab2_details_lf, text="📅 Zile de Rulare", padding=6)
        days_lf.pack(fill=tk.X, pady=5)

        days_grid = ttk.Frame(days_lf); days_grid.pack(fill=tk.X)
        days_list = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        days_ro = {'Monday': 'Luni', 'Tuesday': 'Marți', 'Wednesday': 'Miercuri', 'Thursday': 'Joi', 'Friday': 'Vineri', 'Saturday': 'Sâmbătă', 'Sunday': 'Duminică'}

        for i, d in enumerate(days_list):
            row = i // 4
            col = i % 4
            cb = ttk.Checkbutton(days_grid, text=days_ro[d], variable=self.tab2_day_vars[d],
                                 command=self._on_tab2_field_changed)
            cb.grid(row=row, column=col, sticky='w', padx=8, pady=2)
            ToolTip(cb, f"Activează execuția sarcinii în ziua de {days_ro[d]}.\nIMPORTANT: Dacă nicio zi nu este bifată, sarcina NU va rula!")

        btn_d_box = ttk.Frame(days_lf); btn_d_box.pack(fill=tk.X, pady=(5, 2))
        btn_today2 = ttk.Button(btn_d_box, text="📅 Doar Azi", command=self.tab2_select_today)
        btn_today2.pack(side=tk.LEFT, padx=2)
        ToolTip(btn_today2, "Selectează doar ziua de AZI.")

        btn_tom2 = ttk.Button(btn_d_box, text="📅 Doar Mâine", command=self.tab2_select_tomorrow)
        btn_tom2.pack(side=tk.LEFT, padx=2)
        ToolTip(btn_tom2, "Selectează doar ziua de MÂINE.")

        btn_all2 = ttk.Button(btn_d_box, text="✓ Toate Zilele", command=self.tab2_select_all_days)
        btn_all2.pack(side=tk.LEFT, padx=2)
        ToolTip(btn_all2, "Selectează toate zilele.")

        btn_clr2 = ttk.Button(btn_d_box, text="✕ Niciuna", command=self.tab2_clear_days)
        btn_clr2.pack(side=tk.LEFT, padx=2)
        ToolTip(btn_clr2, "Deselectează toate zilele.")

        # Opțional: Dată fixă
        spec_box = ttk.Frame(days_lf); spec_box.pack(fill=tk.X, pady=(4, 0))
        cb_spec = ttk.Checkbutton(spec_box, text="Rulează doar la data specifică (o singură dată):",
                                  variable=self.tab2_spec_date_enabled_var, command=self._on_tab2_field_changed)
        cb_spec.pack(side=tk.LEFT)
        ToolTip(cb_spec, "Bifați pentru a rula sarcina exclusiv la data calendaristică aleasă.")

        self.tab2_spec_date_entry = ttk.Entry(spec_box, textvariable=self.tab2_spec_date_var, width=12)
        self.tab2_spec_date_entry.pack(side=tk.LEFT, padx=4)
        self.tab2_spec_date_entry.bind("<KeyRelease>", lambda e: self._on_tab2_field_changed())
        ToolTip(self.tab2_spec_date_entry, "Data calendaristică în format YYYY-MM-DD.")

        btn_set_today = ttk.Button(spec_box, text="Azi", width=5, command=self.tab2_set_spec_today)
        btn_set_today.pack(side=tk.LEFT, padx=1)
        btn_set_tom = ttk.Button(spec_box, text="Mâine", width=6, command=self.tab2_set_spec_tomorrow)
        btn_set_tom.pack(side=tk.LEFT, padx=1)

        # 5. Interval Orar
        time_lf = ttk.LabelFrame(self.tab2_details_lf, text="⏰ Interval Orar", padding=6)
        time_lf.pack(fill=tk.X, pady=5)

        cb_ti2 = ttk.Checkbutton(time_lf, text="Activează intervalul orar pentru această sarcină",
                                 variable=self.tab2_interval_enabled_var,
                                 command=self._on_tab2_time_enable_change)
        cb_ti2.pack(anchor='w', pady=(0, 3))
        ToolTip(cb_ti2, "Bifați pentru a impune orele de început (From time) și sfârșit (To time).")

        from_row = ttk.Frame(time_lf); from_row.pack(fill=tk.X, pady=2)
        ttk.Label(from_row, text="De la ora:", width=12).pack(side=tk.LEFT)
        self.tab2_from_entry = ttk.Entry(from_row, textvariable=self.tab2_from_time_var, width=12)
        self.tab2_from_entry.pack(side=tk.LEFT, padx=5)
        self.tab2_from_entry.bind("<KeyRelease>", lambda e: self._on_tab2_field_changed())
        self.tab2_from_entry.bind("<FocusOut>", lambda e: self._on_tab2_field_changed())
        ToolTip(self.tab2_from_entry, "Ora de început (format HH:MM sau HH:MM:SS, ex: 12:16 sau 12:16:05, AM/PM).")
        ttk.Label(from_row, text="(ex: 09:00 sau 09:16:05 = dimineața, 21:16:05 = seara)", foreground="gray").pack(side=tk.LEFT, padx=5)

        to_row = ttk.Frame(time_lf); to_row.pack(fill=tk.X, pady=2)
        ttk.Label(to_row, text="Până la ora:", width=12).pack(side=tk.LEFT)
        self.tab2_to_entry = ttk.Entry(to_row, textvariable=self.tab2_to_time_var, width=12)
        self.tab2_to_entry.pack(side=tk.LEFT, padx=5)
        self.tab2_to_entry.bind("<KeyRelease>", lambda e: self._on_tab2_field_changed())
        self.tab2_to_entry.bind("<FocusOut>", lambda e: self._on_tab2_field_changed())
        ToolTip(self.tab2_to_entry, "Ora de sfârșit (format HH:MM sau HH:MM:SS, ex: 12:16 sau 12:16:05, AM/PM).")
        ttk.Label(to_row, text="(ex: 17:00 sau 17:16:05 = seara, 08:16:05 = dimineața)", foreground="gray").pack(side=tk.LEFT, padx=5)

        ttk.Label(time_lf, text="⏰ Interval peste noapte: ex: 21:00 - 03:00 sau 21:00:00 - 03:00:00",
                  foreground="#00008B", font=("Arial", 8)).pack(anchor='w', pady=(3, 0))
        lbl_same2 = ttk.Label(
            time_lf,
            text="Dacă 'De la ora' = 'Până la ora', sarcina rulează O SINGURĂ DATĂ la acea secundă (redare completă). "
                 "Minim 30 de secunde între orele de start ale sarcinilor, altfel sarcina de mai târziu nu rulează.",
            foreground="#8B0000", font=("Arial", 8), wraplength=520, justify="left"
        )
        lbl_same2.pack(anchor='w', pady=(2, 0))
        ToolTip(lbl_same2, "From = To: o singură rulare completă la acea secundă.\n"
                           "Între sarcini trebuie cel puțin 30 de secunde diferență la From time.")

        # 6. Salvare imediată a sarcinii curente (fără închiderea ferestrei)
        save_task_row = ttk.Frame(self.tab2_details_lf)
        save_task_row.pack(fill=tk.X, pady=(8, 2))
        self.btn_save_task = ttk.Button(save_task_row, text="💾 Salvează Modificările Sarcinii",
                                        command=self.tab2_save_current_task)
        self.btn_save_task.pack(side=tk.LEFT)
        ToolTip(self.btn_save_task, "Salvează IMEDIAT pe disc toate modificările acestei sarcini\n"
                                    "(interval orar, zile, mod de rulare, viteză etc.), fără a închide fereastra.")
        self.tab2_save_status_label = ttk.Label(save_task_row, text="", foreground="#006400",
                                                font=("Arial", 9, "bold"))
        self.tab2_save_status_label.pack(side=tk.LEFT, padx=8)

        # Legare Mouse Wheel pe toate componentele din panoul din dreapta
        self._bind_mousewheel_recursive(self.right_canvas)
        self._bind_mousewheel_recursive(self.right_scrollable_frame)

    # ----- Suport Mouse Wheel Scroll pe panoul din dreapta
    def _bind_mousewheel_recursive(self, widget):
        def _on_wheel(event):
            if hasattr(self, 'right_canvas') and self.right_canvas.winfo_exists():
                # Pe Windows event.delta este +/-120
                scroll_units = int(-1 * (event.delta / 120))
                self.right_canvas.yview_scroll(scroll_units, "units")
                return "break"
        widget.bind("<MouseWheel>", _on_wheel, add="+")
        for child in widget.winfo_children():
            self._bind_mousewheel_recursive(child)

    def _refresh_tab2_files_dropdown(self):
        json_files = []
        try:
            for f in sorted(os.listdir('.')):
                if f.endswith('.json') and f != "schedules.json":
                    json_files.append(f)
        except Exception:
            pass
        self.tab2_file_combo['values'] = json_files

    # ----- Sincronizare selecție Treeview Tab 2
    def _populate_tasks_tree(self):
        for item in self.task_tree.get_children():
            self.task_tree.delete(item)

        for i, t in enumerate(self.tasks):
            status_str = "✓ Activ" if t.enabled else "⏸ Inactiv"
            self.task_tree.insert('', 'end', iid=f"t_{i}", values=(
                i + 1,
                status_str,
                t.name,
                t.get_time_summary(),
                t.get_days_summary(),
                t.get_action_summary()
            ))

        active_count = sum(1 for t in self.tasks if t.enabled)
        self.tab2_stats_label.config(text=f"Sarcini Active: {active_count} / {len(self.tasks)} (Maxim 20)")
        self.btn_add.config(state='normal' if len(self.tasks) < 20 else 'disabled')

    def _on_tree_select(self, _):
        sel = self.task_tree.selection()
        if not sel:
            return
        if len(sel) > 1:
            # Selecție multiplă (Shift+Click / Ctrl+Click): păstrăm panoul de editare pe sarcina curentă
            return
        idx = int(sel[0].split('_')[1])
        if idx == self.current_selected_index:
            return
        self._save_tab2_to_task(self.current_selected_index)
        self._select_task_tab2(idx)

    # ----- Drag & Drop pentru reordonarea sarcinilor în Treeview
    def _on_tree_drag_start(self, event):
        row = self.task_tree.identify_row(event.y)
        self._drag_item = row if row else None

    def _on_tree_drag_motion(self, event):
        if not self._drag_item:
            return
        if len(self.task_tree.selection()) > 1:
            # Nu reordonăm în timpul selecției multiple
            return
        target = self.task_tree.identify_row(event.y)
        if target and target != self._drag_item:
            # Feedback vizual: mutăm rândul în timp ce este tras
            self.task_tree.move(self._drag_item, '', self.task_tree.index(target))

    def _on_tree_drag_drop(self, event):
        if not self._drag_item:
            return
        item = self._drag_item
        self._drag_item = None
        try:
            old_idx = int(item.split('_')[1])
            new_idx = self.task_tree.index(item)
        except (ValueError, tk.TclError):
            return
        if old_idx == new_idx or not (0 <= old_idx < len(self.tasks)):
            return
        # Salvăm formularul în sarcina curentă înainte de reordonare
        self._save_tab2_to_task(self.current_selected_index)
        task = self.tasks.pop(old_idx)
        new_idx = max(0, min(new_idx, len(self.tasks)))
        self.tasks.insert(new_idx, task)
        self.current_selected_index = None
        self._populate_tasks_tree()
        self._select_task_tab2(new_idx)
        self.ctrl.log(f"↕️ Sarcina '{task.name}' a fost mutată pe poziția {new_idx + 1}.")

    def _select_task_tab2(self, idx: Optional[int]):
        if idx is None or not (0 <= idx < len(self.tasks)):
            self._clear_tab2_pane()
            return

        self.current_selected_index = idx
        task = self.tasks[idx]

        self._suppress_events = True
        self.tab2_enabled_var.set(task.enabled)
        self.tab2_name_var.set(task.name)
        self.tab2_action_type_var.set(task.action_type)
        self.tab2_task_file_var.set(task.task_file)
        self.tab2_run_mode_var.set(task.run_mode)
        self.tab2_speed_var.set(task.playback_speed)
        self.tab2_speed_label.config(text=f"{task.playback_speed:.1f}x")
        self.tab2_repeat_min_var.set(task.repeat_minutes)
        self.tab2_loop_count_var.set(task.loop_count)

        if task.steps:
            self.tab2_steps_info_label.config(text=f"✓ Această sarcină conține {len(task.steps)} pași înregistrați proprii.")
        else:
            self.tab2_steps_info_label.config(text="(Această sarcină nu conține pași înregistrați încă)")

        for d, var in self.tab2_day_vars.items():
            var.set(d in task.days)

        self.tab2_spec_date_enabled_var.set(task.specific_date_enabled)
        self.tab2_spec_date_var.set(task.specific_date)

        self.tab2_interval_enabled_var.set(task.time_interval_enabled)
        self.tab2_from_time_var.set(task.from_time)
        self.tab2_to_time_var.set(task.to_time)

        self._on_tab2_time_enable_change()
        self._suppress_events = False

        self.tab2_details_lf.config(text=f"⚙️ Configurare: #{idx+1} — {task.name}")

        item_id = f"t_{idx}"
        if self.task_tree.exists(item_id):
            self.task_tree.selection_set(item_id)
            self.task_tree.focus(item_id)

    def _clear_tab2_pane(self):
        self.tab2_details_lf.config(text="⚙️ Configurare Sarcină (Nicio sarcină în listă)")
        self.tab2_name_var.set("")
        self.tab2_steps_info_label.config(text="Lista este goală. Înregistrați pași noi sau apăsați '➕ Adaugă Sarcină'.")

    def _save_tab2_to_task(self, idx: Optional[int]):
        if idx is None or not (0 <= idx < len(self.tasks)):
            return
        task = self.tasks[idx]
        task.enabled = self.tab2_enabled_var.get()
        task.name = self.tab2_name_var.get().strip() or f"Sarcina {idx+1}"
        task.action_type = self.tab2_action_type_var.get()
        task.task_file = self.tab2_task_file_var.get().strip()
        task.run_mode = self.tab2_run_mode_var.get()
        task.playback_speed = float(self.tab2_speed_var.get())
        task.repeat_minutes = max(1, self.tab2_repeat_min_var.get())
        task.loop_count = max(1, self.tab2_loop_count_var.get())

        task.days = {d for d, var in self.tab2_day_vars.items() if var.get()}
        task.specific_date_enabled = self.tab2_spec_date_enabled_var.get()
        task.specific_date = self.tab2_spec_date_var.get().strip()

        task.time_interval_enabled = self.tab2_interval_enabled_var.get()
        task.from_time = self.tab2_from_time_var.get().strip() or "09:00"
        task.to_time = self.tab2_to_time_var.get().strip() or "17:00"

    def _on_tab2_field_changed(self):
        if self._suppress_events:
            return
        self._save_tab2_to_task(self.current_selected_index)
        self._update_tab2_current_row()
        idx = self.current_selected_index
        if idx is not None and 0 <= idx < len(self.tasks):
            self._sync_tab1_from_task(self.tasks[idx])

    def _on_tab2_name_modified(self):
        if self._suppress_events:
            return
        name = self.tab2_name_var.get().strip()
        if self.current_selected_index is not None and 0 <= self.current_selected_index < len(self.tasks):
            self.tasks[self.current_selected_index].name = name or f"Sarcina {self.current_selected_index+1}"
            self.tab2_details_lf.config(text=f"⚙️ Configurare: #{self.current_selected_index+1} — {self.tasks[self.current_selected_index].name}")
            self._update_tab2_current_row()

    def _on_tab2_speed_slider(self, val):
        speed = float(val)
        self.tab2_speed_label.config(text=f"{speed:.1f}x")
        self._on_tab2_field_changed()

    def _on_tab2_time_enable_change(self):
        enabled = self.tab2_interval_enabled_var.get()
        st = 'normal' if enabled else 'disabled'
        self.tab2_from_entry.config(state=st)
        self.tab2_to_entry.config(state=st)
        self._on_tab2_field_changed()

    def _update_tab2_current_row(self):
        idx = self.current_selected_index
        if idx is None or not (0 <= idx < len(self.tasks)):
            return
        t = self.tasks[idx]
        item_id = f"t_{idx}"
        if self.task_tree.exists(item_id):
            status_str = "✓ Activ" if t.enabled else "⏸ Inactiv"
            self.task_tree.item(item_id, values=(
                idx + 1,
                status_str,
                t.name,
                t.get_time_summary(),
                t.get_days_summary(),
                t.get_action_summary()
            ))
        active_count = sum(1 for item in self.tasks if item.enabled)
        self.tab2_stats_label.config(text=f"Sarcini Active: {active_count} / {len(self.tasks)} (Maxim 20)")

    # ----- Butoane gestionare sarcini Tab 2
    def add_task_tab2(self):
        if len(self.tasks) >= 20:
            messagebox.showwarning("Limită atinsă", "Puteți programa maximum 20 de sarcini independente.", parent=self)
            return
        self._save_tab2_to_task(self.current_selected_index)

        new_name = f"Sarcina {len(self.tasks) + 1}"
        init_mode = "continuous" if self.ctrl.run_continuously else "once"
        new_task = ScheduledTask(
            id=str(uuid.uuid4())[:8],
            name=new_name,
            enabled=True,
            action_type="steps",
            steps=[asdict(s) for s in self.ctrl.steps] if self.ctrl.steps else [],
            run_mode=init_mode,
            playback_speed=1.0,
            days=set(),
            time_interval_enabled=True,
            from_time="09:00",
            to_time="17:00"
        )
        self.tasks.append(new_task)
        self._populate_tasks_tree()
        self._select_task_tab2(len(self.tasks) - 1)
        self.ctrl.log(f"➕ Sarcină nouă adăugată în Schedule: '{new_name}'.")

    def delete_task_tab2(self):
        if not self.tasks:
            messagebox.showinfo("Informație", "Nu există nicio sarcină de șters.", parent=self)
            return

        # Suport selecție multiplă (Shift+Click / Ctrl+Click)
        sel = self.task_tree.selection()
        if sel:
            indices = sorted({int(iid.split('_')[1]) for iid in sel
                              if 0 <= int(iid.split('_')[1]) < len(self.tasks)})
        elif self.current_selected_index is not None and 0 <= self.current_selected_index < len(self.tasks):
            indices = [self.current_selected_index]
        else:
            return
        if not indices:
            return

        names = [self.tasks[i].name for i in indices]
        if len(names) == 1:
            msg = f"Sigur doriți să ștergeți definitiv '{names[0]}'?"
        else:
            msg = (f"Sigur doriți să ștergeți definitiv cele {len(names)} sarcini selectate?\n\n"
                   + "\n".join(f"  • {n}" for n in names))

        if messagebox.askyesno("Ștergere Sarcină", msg, parent=self):
            for i in reversed(indices):
                del self.tasks[i]
            self.ctrl.log(f"🗑️ Șterse din Schedule: {', '.join(names)}.")

            if not self.tasks:
                # Toate sarcinile au fost șterse: lăsăm lista goală!
                self.current_selected_index = None
                self._populate_tasks_tree()
                self._clear_tab2_pane()
                self._sync_tab1_from_task(None)
            else:
                new_idx = min(indices[0], len(self.tasks) - 1)
                self.current_selected_index = None
                self._populate_tasks_tree()
                self._select_task_tab2(new_idx)
                self._sync_tab1_from_task(self.tasks[new_idx])

    def _on_tree_delete_key(self, event=None):
        self.delete_task_tab2()
        return "break"

    def _on_tree_right_click(self, event):
        row = self.task_tree.identify_row(event.y)
        if not row:
            return "break"
        try:
            idx = int(row.split('_')[1])
        except (ValueError, IndexError):
            return "break"
        if not (0 <= idx < len(self.tasks)):
            return "break"
        self._drag_item = None
        if idx != self.current_selected_index:
            self._save_tab2_to_task(self.current_selected_index)
            self._select_task_tab2(idx)
        else:
            self.task_tree.selection_set(row)
            self.task_tree.focus(row)
        self.rename_task_tab2()
        return "break"

    def rename_task_tab2(self):
        idx = self.current_selected_index
        if idx is None or not (0 <= idx < len(self.tasks)):
            return
        task = self.tasks[idx]
        old_name = task.name
        new_name = simpledialog.askstring("Redenumește Sarcină", "Introduceți noul nume pentru sarcină:",
                                          initialvalue=task.name, parent=self)
        if new_name and new_name.strip():
            task.name = new_name.strip()
            self.tab2_name_var.set(task.name)
            self._update_tab2_current_row()
            self.tab2_details_lf.config(text=f"⚙️ Configurare: #{idx+1} — {task.name}")
            self.ctrl.log(f"✏️ Sarcina '{old_name}' a fost redenumită în '{task.name}'.")

    def duplicate_task_tab2(self):
        if len(self.tasks) >= 20:
            messagebox.showwarning("Limită atinsă", "Puteți programa maximum 20 de sarcini independente.", parent=self)
            return
        idx = self.current_selected_index
        if idx is None or not (0 <= idx < len(self.tasks)):
            return
        self._save_tab2_to_task(idx)
        original = self.tasks[idx]
        dup = original.copy()
        dup.name = f"{original.name} (Copie)"
        self.tasks.insert(idx + 1, dup)
        self._populate_tasks_tree()
        self._select_task_tab2(idx + 1)
        self.ctrl.log(f"📋 Sarcina '{original.name}' a fost duplicată ca '{dup.name}'.")

    def toggle_task_tab2(self):
        idx = self.current_selected_index
        if idx is None or not (0 <= idx < len(self.tasks)):
            return
        task = self.tasks[idx]
        task.enabled = not task.enabled
        self.tab2_enabled_var.set(task.enabled)
        self._update_tab2_current_row()
        st_txt = "activată" if task.enabled else "pusă pe pauză/anulată"
        self.ctrl.log(f"⏸️ Sarcina '{task.name}' a fost {st_txt}.")

    def _check_runnable_warnings(self, tasks_to_check):
        """Avertizează despre condițiile care împiedică rularea sarcinilor și oferă reparare rapidă."""
        # 1. Sarcini active fără nicio zi bifată (și fără dată specifică) — NU vor rula niciodată!
        for task in tasks_to_check:
            if not task.enabled:
                continue
            if task.specific_date_enabled and task.specific_date:
                continue
            if task.days:
                continue
            if messagebox.askyesno(
                    "⚠ Sarcina NU va rula — Nicio zi bifată!",
                    f"Sarcina '{task.name}' este Activă și are interval orar setat,\n"
                    f"dar NICIO ZI din săptămână nu este bifată la 'Zile de Rulare'.\n\n"
                    f"Fără cel puțin o zi bifată, sarcina NU va rula NICIODATĂ.\n\n"
                    f"Doriți să bifez automat ziua de AZI pentru această sarcină?",
                    parent=self):
                task.days = {datetime.now().strftime("%A")}

        # 2. Scheduler-ul Global (Master) este OPRIT — nicio sarcină nu rulează, indiferent de ore!
        if not self.enable_global_var.get() and any(t.enabled for t in self.tasks):
            if messagebox.askyesno(
                    "⚠ Scheduler Global OPRIT",
                    "Comutatorul 'Activează Scheduler Global (Master On/Off)' este DEBIFAT.\n\n"
                    "Cât timp este oprit, NICIO sarcină nu va rula automat,\n"
                    "indiferent de orele și zilele programate.\n\n"
                    "Doriți să-l ACTIVEZ acum?",
                    parent=self):
                self.enable_global_var.set(True)

    def tab2_save_current_task(self):
        """Salvează imediat pe disc modificările sarcinii selectate, fără a închide fereastra."""
        idx = self.current_selected_index
        if idx is None or not (0 <= idx < len(self.tasks)):
            messagebox.showinfo("Informație", "Nu este selectată nicio sarcină de salvat.", parent=self)
            return

        self._save_tab2_to_task(idx)
        task = self.tasks[idx]

        # Validare timp (format HH:MM sau HH:MM:SS)
        for tf_name, tf_val in [("From time", task.from_time), ("To time", task.to_time)]:
            if parse_time_to_seconds(tf_val) is None:
                messagebox.showerror("Eroare Validare",
                                     f"Ora introdusă pentru '{task.name}' ({tf_name}: '{tf_val}') nu este validă.\n"
                                     f"Folosiți formatul HH:MM (ex: 09:30) sau HH:MM:SS (ex: 14:12:40).",
                                     parent=self)
                return

        # Avertizări: nicio zi bifată / master oprit (cu reparare automată opțională)
        self._check_runnable_warnings([task])

        # Resetăm last_run_date pentru ca sarcina reconfigurată să poată rula din nou
        task.last_run_date = ""

        # Reîncărcăm formularul (ex: zilele bifate automat) și actualizăm rândul din listă
        self._select_task_tab2(idx)
        self._update_tab2_current_row()
        self._sync_tab1_from_task(task)

        # Persistă IMEDIAT pe disc, fără a închide fereastra
        self.config_obj.enabled = self.enable_global_var.get()
        self.ctrl.schedule_config = self.config_obj.copy()
        self.ctrl.save_schedules_to_disk()
        # Actualizăm și badge-ul 'Scheduler: ON/OFF' din fereastra principală
        try:
            self.parent_app._update_schedule_badge()
        except Exception:
            pass

        self.tab2_save_status_label.config(text=f"✓ Salvat la {datetime.now().strftime('%H:%M:%S')}")
        self.after(4000, lambda: self.tab2_save_status_label.config(text=""))
        self.ctrl.log(f"💾 Sarcina '{task.name}' a fost salvată pe disc ({task.from_time} - {task.to_time}).")

    def move_task_up_tab2(self):
        idx = self.current_selected_index
        if idx is None or idx <= 0:
            return
        self._save_tab2_to_task(idx)
        self.tasks[idx - 1], self.tasks[idx] = self.tasks[idx], self.tasks[idx - 1]
        self._populate_tasks_tree()
        self._select_task_tab2(idx - 1)

    def move_task_down_tab2(self):
        idx = self.current_selected_index
        if idx is None or idx >= len(self.tasks) - 1:
            return
        self._save_tab2_to_task(idx)
        self.tasks[idx + 1], self.tasks[idx] = self.tasks[idx], self.tasks[idx + 1]
        self._populate_tasks_tree()
        self._select_task_tab2(idx + 1)

    # ----- Butoane rapide Tab 2
    def tab2_select_today(self):
        today = datetime.now().strftime("%A")
        for d, var in self.tab2_day_vars.items():
            var.set(d == today)
        self._on_tab2_field_changed()

    def tab2_select_tomorrow(self):
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%A")
        for d, var in self.tab2_day_vars.items():
            var.set(d == tomorrow)
        self._on_tab2_field_changed()

    def tab2_select_all_days(self):
        for var in self.tab2_day_vars.values():
            var.set(True)
        self._on_tab2_field_changed()

    def tab2_clear_days(self):
        for var in self.tab2_day_vars.values():
            var.set(False)
        self._on_tab2_field_changed()

    def tab2_set_spec_today(self):
        self.tab2_spec_date_var.set(datetime.now().strftime("%Y-%m-%d"))
        self.tab2_spec_date_enabled_var.set(True)
        self._on_tab2_field_changed()

    def tab2_set_spec_tomorrow(self):
        self.tab2_spec_date_var.set((datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"))
        self.tab2_spec_date_enabled_var.set(True)
        self._on_tab2_field_changed()

    def browse_task_file_tab2(self):
        fp = filedialog.askopenfilename(
            title="Selectează fișierul JSON cu sarcina",
            filetypes=[["JSON Task Files", "*.json"], ["All Files", "*.*"]],
            initialdir=os.getcwd(),
            parent=self
        )
        if fp:
            rel = os.path.relpath(fp, os.getcwd())
            chosen = rel if not rel.startswith("..") else fp
            self.tab2_task_file_var.set(chosen)
            self.tab2_action_type_var.set("file")
            self._refresh_tab2_files_dropdown()
            self._on_tab2_field_changed()

    def save_steps_as_file_tab2(self):
        idx = self.current_selected_index
        if idx is None or not (0 <= idx < len(self.tasks)):
            return
        task = self.tasks[idx]
        steps = self.ctrl.get_steps_for_task(task)
        if not steps:
            messagebox.showinfo("Informație", "Sarcina nu are pași de salvat.", parent=self)
            return

        fp = filedialog.asksaveasfilename(
            title="Salvează pașii sarcinii ca fișier JSON",
            defaultextension=".json",
            filetypes=[["JSON Task Files", "*.json"], ["All Files", "*.*"]],
            initialdir=os.getcwd(),
            parent=self
        )
        if fp:
            data = {'steps': [asdict(s) for s in steps]}
            with open(fp, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            rel = os.path.relpath(fp, os.getcwd())
            chosen = rel if not rel.startswith("..") else fp
            self.tab2_task_file_var.set(chosen)
            self.tab2_action_type_var.set("file")
            self._refresh_tab2_files_dropdown()
            self._on_tab2_field_changed()
            messagebox.showinfo("Salvat", f"Fișierul a fost salvat și asociat sarcinii:\n{chosen}", parent=self)

    # ======================== SINCRONIZARE TABS & SALVARE ========================

    def _on_tab_changed(self, event):
        # Protecție: nu salvăm nimic dacă evenimentul vine în timpul construirii/încărcării UI-ului
        if self._suppress_events:
            return
        tab_id = self.notebook.select()
        tab_name = self.notebook.tab(tab_id, "text")

        if "Sarcini Multiple" in tab_name:
            # Trecere la Tab 2: Salvează Tab 1 în sarcina activă și reîmprospătează lista
            idx = self.current_selected_index
            if idx is not None and 0 <= idx < len(self.tasks):
                self._save_tab1_to_task(self.tasks[idx])
            self._populate_tasks_tree()
            self._select_task_tab2(idx if idx is not None else (0 if self.tasks else None))
        else:
            # Trecere la Tab 1: Salvează Tab 2 și actualizează formularul simplu
            idx = self.current_selected_index
            if idx is not None and 0 <= idx < len(self.tasks):
                self._save_tab2_to_task(idx)
                self._sync_tab1_from_task(self.tasks[idx])
            else:
                self._sync_tab1_from_task(None)

    def _on_tree_double_click(self, event):
        item = self.task_tree.identify_row(event.y)
        if not item:
            return
        try:
            idx = int(item.split('_')[1])
        except (ValueError, IndexError):
            return
        self.open_task_events_editor(idx)

    def open_task_events_editor(self, idx: Optional[int] = None):
        if idx is None:
            idx = self.current_selected_index
        if idx is None or not (0 <= idx < len(self.tasks)):
            messagebox.showinfo("Informație", "Selectați o sarcină pentru a-i edita evenimentele.", parent=self)
            return

        self._save_tab2_to_task(self.current_selected_index)
        task = self.tasks[idx]

        def on_saved_cb():
            self._update_tab2_current_row()
            self._select_task_tab2(idx)
            self._sync_tab1_from_task(task)

        TaskEventsEditorDialog(self, task, self.ctrl, on_saved_cb)

    def test_current_task(self):
        # Dacă rulează deja un test, al doilea clic pe buton îl oprește imediat
        if self.ctrl.playing:
            self.ctrl.stop()
            return

        tab_id = self.notebook.select()
        tab_name = self.notebook.tab(tab_id, "text")

        idx = self.current_selected_index
        if idx is None or not (0 <= idx < len(self.tasks)):
            messagebox.showinfo("Informație", "Nu este selectată nicio sarcină de testat.", parent=self)
            return

        if self._is_tab1_active():
            self._save_tab1_to_task(self.tasks[idx])
        else:
            self._save_tab2_to_task(idx)

        task = self.tasks[idx]
        self.ctrl.test_play_task(task)

    def _poll_schedule_test_playback(self):
        try:
            if not self.winfo_exists():
                return
            is_playing = getattr(self.ctrl, 'playing', False)
            if hasattr(self, 'tab1_btn_test') and self.tab1_btn_test.winfo_exists():
                self.tab1_btn_test.config(text="⏹ Oprește Testul" if is_playing else "▶ Testează")
            if hasattr(self, 'tab2_btn_test') and self.tab2_btn_test.winfo_exists():
                self.tab2_btn_test.config(text="⏹ Oprește Testul" if is_playing else "▶ Testează Sarcina Acum")
        except Exception:
            pass
        self.after(200, self._poll_schedule_test_playback)

    def on_save(self):
        # Salvează tab-ul activ în sarcina curentă
        idx = self.current_selected_index
        tab_id = self.notebook.select()
        tab_name = self.notebook.tab(tab_id, "text")

        if idx is not None and 0 <= idx < len(self.tasks):
            if self._is_tab1_active():
                self._save_tab1_to_task(self.tasks[idx])
            else:
                self._save_tab2_to_task(idx)

        # Validare timp (format HH:MM sau HH:MM:SS)
        for t in self.tasks:
            if t.time_interval_enabled or t.from_time:
                for tf_name, tf_val in [("From time", t.from_time), ("To time", t.to_time)]:
                    if parse_time_to_seconds(tf_val) is None:
                        messagebox.showerror("Eroare Validare",
                                             f"Ora introdusă pentru '{t.name}' ({tf_name}: '{tf_val}') nu este validă.\n"
                                             f"Folosiți formatul HH:MM (ex: 09:30 sau 17:00) sau HH:MM:SS (ex: 12:16:05 sau 21:00:30).",
                                             parent=self)
                        return
            # Resetăm last_run_date DOAR pentru sarcinile reprogramate (oră / zile / mod schimbate),
            # altfel o sarcină deja rulată azi pornea din nou la simpla apăsare pe 'Salvează'
            if self._orig_sigs.get(t.id) != t.schedule_signature():
                t.last_run_date = ""

        # Avertizări finale: sarcini fără zile bifate / master oprit (cu reparare automată opțională)
        self._check_runnable_warnings(self.tasks)

        self.config_obj.enabled = self.enable_global_var.get()
        self.config_obj.keep_awake = self.keep_awake_var.get()
        self.config_obj.auto_start = self.auto_start_var.get()
        self.config_obj.lock_check = self.lock_check_var.get()
        self.config_obj.capture_screens = self.capture_var.get()
        self.config_obj.tasks = self.tasks
        self.result = self.config_obj
        self.destroy()


# ============================ Mini Mode ============================

class MiniModeWindow(tk.Toplevel):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.title("BEBE v5.5")
        self.resizable(False, False)

        self.ctrl = controller
        self.parent_app = parent

        self.withdraw()
        self.update_idletasks()
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        window_width = 280
        window_height = 80
        x = screen_width - window_width - 10
        y = screen_height - window_height - 70
        self.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self.deiconify()

        self.attributes('-topmost', True)
        self._build_ui()
        self._start_update_loop()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self):
        btn_frame = ttk.Frame(self, padding=5)
        btn_frame.pack(fill=tk.BOTH, expand=True)

        self.btn_record = ttk.Button(btn_frame, text="●", width=3, command=self.toggle_record)
        self.btn_record.grid(row=0, column=0, padx=3, pady=3, sticky='nsew')
        ttk.Label(btn_frame, text="Înregistr.", font=('Arial', 7)).grid(row=1, column=0)

        self.btn_play = ttk.Button(btn_frame, text="▶", width=3, command=self.play_task)
        self.btn_play.grid(row=0, column=1, padx=3, pady=3, sticky='nsew')
        ttk.Label(btn_frame, text="Redă", font=('Arial', 7)).grid(row=1, column=1)

        self.btn_pause = ttk.Button(btn_frame, text="⏸", width=3, command=self.pause_task)
        self.btn_pause.grid(row=0, column=2, padx=3, pady=3, sticky='nsew')
        ttk.Label(btn_frame, text="Pauză", font=('Arial', 7)).grid(row=1, column=2)

        self.btn_stop = ttk.Button(btn_frame, text="⏹", width=3, command=self.stop_task)
        self.btn_stop.grid(row=0, column=3, padx=3, pady=3, sticky='nsew')
        ttk.Label(btn_frame, text="Oprește", font=('Arial', 7)).grid(row=1, column=3)

        for i in range(4):
            btn_frame.grid_columnconfigure(i, weight=1)
        btn_frame.grid_rowconfigure(0, weight=1)

        ToolTip(self.btn_record, "Înregistrează/Oprește înregistrarea (F1)", delay_ms=300)
        ToolTip(self.btn_play, "Rulează taskul (F9)", delay_ms=300)
        ToolTip(self.btn_pause, "Pauză redare (F10)", delay_ms=300)
        ToolTip(self.btn_stop, "Oprește redare/înregistrare (ESC)", delay_ms=300)

    def toggle_record(self):
        if self.ctrl.recording:
            self.ctrl.stop_recording()
        else:
            self.ctrl.start_recording()
        self.parent_app._update_ui_state()

    def play_task(self):
        self.ctrl.play()
        self.parent_app._update_ui_state()

    def pause_task(self):
        self.ctrl.toggle_pause()
        self.parent_app._update_ui_state()

    def stop_task(self):
        self.ctrl.stop()
        self.parent_app._update_ui_state()

    def _start_update_loop(self):
        self._update_buttons()
        self.after(100, self._start_update_loop)

    def _update_buttons(self):
        rec = self.ctrl.recording
        play = self.ctrl.playing
        self.btn_record.config(text="⏺" if rec else "●")
        self.btn_play.config(state='disabled' if (rec or play) else 'normal')
        self.btn_pause.config(state='normal' if play else 'disabled')
        self.btn_stop.config(state='normal' if (rec or play) else 'disabled')

    def on_close(self):
        self.parent_app.mini_mode_var.set(False)
        self.parent_app.mini_window = None
        self.parent_app.deiconify()
        self.parent_app.lift()
        self.parent_app.focus_force()
        self.parent_app.log("🔼 Mini Mode deactivated")
        self.destroy()


# ============================ Logs Window ============================

class LogsWindow(tk.Toplevel):
    def __init__(self, parent, log_text_widget):
        super().__init__(parent)
        self.title("BEBE - Jurnal (Logs)")
        self.geometry("820x520")
        self.log_source = log_text_widget
        self._build_ui()
        self._refresh_logs()
        self.after(1000, self._auto_refresh)

    def _build_ui(self):
        toolbar = ttk.Frame(self); toolbar.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(toolbar, text="📋 Copiază Tot", command=self.copy_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="💾 Salvează în Fișier", command=self.save_to_file).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="🗑 Golește Jurnalul", command=self.clear_logs).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="📝 Deschide în Notepad", command=self.open_notepad).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="🔄 Reîmprospătează", command=self._refresh_logs).pack(side=tk.LEFT, padx=2)

        text_frame = ttk.Frame(self); text_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.text = tk.Text(text_frame, wrap='word')
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _refresh_logs(self):
        content = self.log_source.get('1.0', 'end')
        self.text.delete('1.0', 'end')
        self.text.insert('1.0', content)
        self.text.see('end')

    def _auto_refresh(self):
        if self.winfo_exists():
            self._refresh_logs()
            self.after(1000, self._auto_refresh)

    def copy_all(self):
        content = self.text.get('1.0', 'end-1c')
        self.clipboard_clear()
        self.clipboard_append(content)

    def save_to_file(self):
        fp = filedialog.asksaveasfilename(defaultextension=".txt",
                                          filetypes=[["Fișiere Text","*.txt"], ["Toate Fișierele","*.*"]])
        if fp:
            with open(fp, 'w', encoding='utf-8') as f:
                f.write(self.text.get('1.0', 'end-1c'))

    def clear_logs(self):
        if messagebox.askyesno("Golește Jurnalul", "Ștergeți tot jurnalul afișat?"):
            self.log_source.delete('1.0', 'end')
            self._refresh_logs()

    def open_notepad(self):
        temp_file = os.path.join(os.environ.get('TEMP', '.'), 'bebe_logs.txt')
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(self.text.get('1.0', 'end-1c'))
        subprocess.Popen(['notepad.exe', temp_file])


# ============================ Istoric Execuții Window ============================

class HistoryWindow(tk.Toplevel):
    """Lista tuturor execuțiilor sarcinilor (persistentă în istoric_sarcini.json)."""
    _instance = None

    @classmethod
    def open(cls, parent, controller):
        inst = cls._instance
        if inst is not None:
            try:
                if inst.winfo_exists():
                    inst.deiconify()
                    inst.lift()
                    inst.focus_force()
                    inst.refresh()
                    return inst
            except tk.TclError:
                pass
        cls._instance = cls(parent, controller)
        return cls._instance

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.title("📜 Istoric Execuții Sarcini")
        self.geometry("1150x620")
        self.minsize(800, 400)
        self.ctrl = controller
        self._last_count = -1
        self._rows: Dict[str, dict] = {}
        self._build_ui()
        self.refresh()
        self.after(2000, self._auto_refresh)

    def _build_ui(self):
        top = ttk.Frame(self, padding=6)
        top.pack(fill=tk.X)
        ttk.Label(top, text="Filtru sarcină:").pack(side=tk.LEFT)
        self.filter_var = tk.StringVar(value="(Toate)")
        self.filter_combo = ttk.Combobox(top, textvariable=self.filter_var, width=28, state="readonly")
        self.filter_combo.pack(side=tk.LEFT, padx=4)
        self.filter_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh(force=True))
        ttk.Button(top, text="🔄 Reîmprospătează", command=lambda: self.refresh(force=True)).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="📂 Capturi ecran", command=self.open_captures).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="📝 Jurnal complet (bebe_log.txt)", command=self.open_log_file).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="🗑 Golește istoricul", command=self.clear_history).pack(side=tk.RIGHT, padx=4)

        self.summary = ttk.Label(self, text="", padding=(8, 0), foreground="#4B0082", font=("Arial", 9, "bold"))
        self.summary.pack(fill=tk.X)

        paned = ttk.PanedWindow(self, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        tf = ttk.Frame(paned)
        cols = ("started", "task", "scheduled", "trigger", "status", "steps", "duration")
        self.tree = ttk.Treeview(tf, columns=cols, show="headings", selectmode="browse")
        for c, txt, w, anc in [("started", "Pornită la", 150, 'center'), ("task", "Sarcină", 170, 'w'),
                               ("scheduled", "Programată la", 150, 'center'), ("trigger", "Declanșare", 100, 'center'),
                               ("status", "Status", 230, 'w'), ("steps", "Pași", 70, 'center'),
                               ("duration", "Durată", 80, 'center')]:
            self.tree.heading(c, text=txt)
            self.tree.column(c, width=w, anchor=anc)
        sb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.tag_configure("ok", foreground="#006400")
        self.tree.tag_configure("bad", foreground="#B00000")
        self.tree.tag_configure("warn", foreground="#B36B00")
        self.tree.tag_configure("run", foreground="#0050B0")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", lambda e: self.open_run_captures())
        paned.add(tf, weight=3)

        df = ttk.LabelFrame(paned, text="Detalii execuție (pas cu pas — fereastra în care a nimerit fiecare clic)", padding=4)
        self.details = tk.Text(df, wrap='none', height=10, font=("Consolas", 9))
        dsb = ttk.Scrollbar(df, orient="vertical", command=self.details.yview)
        hsb = ttk.Scrollbar(df, orient="horizontal", command=self.details.xview)
        self.details.configure(yscrollcommand=dsb.set, xscrollcommand=hsb.set)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self.details.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        dsb.pack(side=tk.RIGHT, fill=tk.Y)
        paned.add(df, weight=2)

        ToolTip(self.tree, "Selectați o execuție pentru a vedea detaliile pas cu pas.\n"
                           "Dublu-clic = deschide capturile de ecran ale acelei execuții.")

    @staticmethod
    def _duration(e: dict) -> str:
        try:
            if e.get('started') and e.get('ended'):
                a = datetime.strptime(e['started'], "%Y-%m-%d %H:%M:%S")
                b = datetime.strptime(e['ended'], "%Y-%m-%d %H:%M:%S")
                secs = int((b - a).total_seconds())
                return f"{secs // 60}m {secs % 60:02d}s" if secs >= 60 else f"{secs}s"
        except Exception:
            pass
        return ""

    @staticmethod
    def _tag(status: str) -> str:
        if status.startswith("✅") or status.startswith("🔒→▶"):
            return "ok"
        if status.startswith("⛔") or status.startswith("❌"):
            return "bad"
        if status.startswith("▶"):
            return "run"
        return "warn"

    def refresh(self, force: bool = False):
        entries = self.ctrl.history.snapshot()
        sig = (len(entries), entries[-1].get('status') if entries else None,
               entries[-1].get('steps_done') if entries else None, len(entries[-1].get('details', [])) if entries else 0)
        if not force and sig == self._last_count:
            return
        self._last_count = sig

        names = sorted({e.get('task_name', '') for e in entries if e.get('task_name')})
        self.filter_combo['values'] = ["(Toate)"] + names
        flt = self.filter_var.get()

        sel = self.tree.selection()
        sel_id = sel[0] if sel else None
        self.tree.delete(*self.tree.get_children())
        self._rows = {}
        shown = [e for e in reversed(entries) if flt in ("", "(Toate)") or e.get('task_name') == flt]
        for e in shown:
            rid = e.get('run_id') or uuid.uuid4().hex
            self._rows[rid] = e
            steps = f"{e.get('steps_done', 0)}/{e.get('steps_total', 0)}" if e.get('steps_total') else ""
            self.tree.insert('', 'end', iid=rid, tags=(self._tag(e.get('status', '')),), values=(
                e.get('started') or "—", e.get('task_name', ''), e.get('scheduled_for') or "—",
                e.get('trigger', ''), e.get('status', ''), steps, self._duration(e)))
        ok = sum(1 for e in shown if self._tag(e.get('status', '')) == "ok")
        bad = sum(1 for e in shown if self._tag(e.get('status', '')) == "bad")
        self.summary.config(text=f"Total: {len(shown)} execuții   |   ✅ reușite: {ok}   |   ⛔ ratate / erori: {bad}   |   "
                                 f"Fișier: {self.ctrl.history.filepath}")
        if sel_id and self.tree.exists(sel_id):
            self.tree.selection_set(sel_id)
            self._show_details(sel_id)
        elif shown:
            first = self.tree.get_children()[0]
            self.tree.selection_set(first)
            self._show_details(first)
        else:
            self.details.delete('1.0', 'end')
            self.details.insert('1.0', "Nicio execuție înregistrată încă.")

    def _auto_refresh(self):
        try:
            if self.winfo_exists():
                self.refresh()
                self.after(2000, self._auto_refresh)
        except tk.TclError:
            pass

    def _on_select(self, _):
        sel = self.tree.selection()
        if sel:
            self._show_details(sel[0])

    def _show_details(self, rid: str):
        e = self.ctrl.history.get(rid) or self._rows.get(rid)
        if not e:
            return
        lines = [f"Sarcină: {e.get('task_name')}   |   Status: {e.get('status')}   |   Declanșare: {e.get('trigger')}",
                 f"Programată la: {e.get('scheduled_for') or '—'}   |   Pornită: {e.get('started') or '—'}   |   "
                 f"Terminată: {e.get('ended') or '—'}   |   Pași: {e.get('steps_done', 0)}/{e.get('steps_total', 0)}",
                 "-" * 110]
        lines += e.get('details', [])
        self.details.delete('1.0', 'end')
        self.details.insert('1.0', "\n".join(lines))

    def open_run_captures(self):
        sel = self.tree.selection()
        if not sel:
            return
        folder = os.path.join(CAPTURES_DIR, sel[0])
        if os.path.isdir(folder):
            os.startfile(folder)
        else:
            messagebox.showinfo("Capturi", "Nu există capturi de ecran pentru această execuție.", parent=self)

    def open_captures(self):
        os.makedirs(CAPTURES_DIR, exist_ok=True)
        os.startfile(CAPTURES_DIR)

    def open_log_file(self):
        if os.path.exists(LOG_FILE):
            subprocess.Popen(['notepad.exe', LOG_FILE])
        else:
            messagebox.showinfo("Jurnal", "Jurnalul nu există încă.", parent=self)

    def clear_history(self):
        if messagebox.askyesno("Golește istoricul", "Ștergeți toate înregistrările din istoric?\n"
                                                     "(Capturile de ecran rămân în folderul 'istoric_capturi'.)", parent=self):
            self.ctrl.history.clear()
            self.refresh(force=True)


# ============================ Main App ============================

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("BEBE - Înregistrator Sarcini - Versiunea 5.5")
        self.geometry("1400x720")

        # Culoare fundal mov foarte deschis
        self.configure(bg="#F5E9FF")
        style = ttk.Style(self)
        try:
            style.theme_use('clam')
        except Exception:
            pass
        palette_bg = "#F5E9FF"
        for name in ("TFrame", "TLabelframe", "TLabel", "TLabelframe.Label"):
            style.configure(name, background=palette_bg)

        # Buffer log-uri ascuns
        self.log_text = tk.Text(self)
        self._pending_logs: List[str] = []

        self.ctrl = TaskController(self.log)
        self.mini_window = None
        for line in self._pending_logs:
            self._append_log_line(line)
        self._pending_logs = []

        self._build_menu()
        self._build_ui()
        self._wire_hotkeys()
        self._update_schedule_badge()
        self.after(100, self._poll_ui_queue)
        self.after(800, self._startup_report)

    def _startup_report(self):
        cfg = self.ctrl.schedule_config
        active = [t for t in cfg.tasks if t.enabled]
        self.log(f"🚀 BEBE v5.5 pornit. Jurnal: {LOG_FILE} | Istoric: {HISTORY_FILE}")
        if cfg.enabled:
            self.log(f"🟢 [SCHEDULER] Pornit automat la deschidere ({len(active)} sarcini active).")
        elif active:
            self.log(f"⚠️ [SCHEDULER] Este OPRIT — cele {len(active)} sarcini active NU vor rula până nu apăsați "
                     f"'▶ Activează Scheduler' (sau bifați 'Pornește automat la deschidere' în Schedule Settings).")
        if cfg.enabled and not cfg.keep_awake:
            self.log("⚠️ 'Ține PC-ul treaz' este dezactivat: dacă PC-ul intră în Standby / se blochează, clicurile nu vor nimeri.")

    # ----- Menu
    def _build_menu(self):
        menubar = tk.Menu(self); self.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Fișier", menu=file_menu)
        file_menu.add_command(label="Sarcină Nouă", command=self.new_task, accelerator="Ctrl+N")
        file_menu.add_command(label="Deschide Sarcină...", command=self.load_json, accelerator="Ctrl+O")
        file_menu.add_command(label="Salvează Sarcina", command=self.save_json, accelerator="Ctrl+S")
        file_menu.add_separator()
        file_menu.add_command(label="Setări Programare...", command=self.show_schedule_settings, accelerator="Shift+C")
        file_menu.add_command(label="📜 Istoric Execuții Sarcini...", command=self.show_history)
        file_menu.add_separator()
        file_menu.add_command(label="Ieșire", command=self.quit)

        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Ajutor", menu=help_menu)
        help_menu.add_command(label="Despre", command=self.show_about)

        self.bind_all("<Control-n>", lambda e: self.new_task())
        self.bind_all("<Control-o>", lambda e: self.load_json())
        self.bind_all("<Control-s>", lambda e: self.save_json())
        # Shift+C deschide Schedule doar dacă NU tastăm într-un câmp de text
        # (altfel scrierea literei 'C' mari în orice câmp deschidea fereastra!)
        self.bind_all("<Shift-C>", self._schedule_hotkey)
        self.bind_all("<Shift-c>", self._schedule_hotkey)

    def _schedule_hotkey(self, event):
        w = event.widget
        if isinstance(w, (tk.Entry, ttk.Entry, tk.Text, ttk.Combobox, ttk.Spinbox)):
            return
        self.show_schedule_settings()

    # ----- Hotkeys
    def _wire_hotkeys(self):
        # IMPORTANT: Biblioteca 'keyboard' rulează callback-urile pe propriul thread,
        # iar Tkinter NU este thread-safe! Programăm execuția pe thread-ul UI cu after(0, ...),
        # altfel apăsarea hotkey-urilor putea bloca sau crăpa aplicația aleatoriu.
        try:
            keyboard.add_hotkey('esc', lambda: self.after(0, self.safe_stop))
            keyboard.add_hotkey('f1', lambda: self.after(0, self.toggle_record))
            keyboard.add_hotkey('f9', lambda: self.after(0, self._toggle_play_hotkey))
            keyboard.add_hotkey('f10', lambda: self.after(0, self.ctrl.toggle_pause))
            # NU mai înregistrăm Shift+C ca scurtătură GLOBALĂ: scrierea unui 'C' mare în ORICE aplicație
            # (ex: „Ce mai faci?” în chat) deschidea fereastra de Programare în mijlocul înregistrării!
            # Shift+C funcționează în continuare când fereastra BEBE este activă (bind_all de mai sus).
        except Exception as e:
            print(f"[HOTKEYS] Warning: {e}")

    def safe_stop(self):
        self.ctrl.stop()
        self._update_ui_state()
        self._refresh_events_list()

    def _toggle_play_hotkey(self):
        if self.ctrl.recording:
            self.log("⛔ F9 ignorat: sunteți în înregistrare. Pentru a opri înregistrarea apăsați F1.")
            return
        if self.ctrl.playing:
            self.ctrl.stop()
        else:
            sel = list(self.tree.selection())
            indices = [int(item.split('_')[1]) for item in sel] if sel else None
            self.ctrl.play(indices)
        self._update_ui_state()

    # ----- UI
    def _build_ui(self):
        main = ttk.Frame(self); main.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # Record Frame
        rec_frame = ttk.LabelFrame(main, text="Înregistrare Sarcină", padding=10)
        rec_frame.pack(fill=tk.X, padx=4, pady=4)
        rec_top = ttk.Frame(rec_frame); rec_top.pack(fill=tk.X)

        self.btn_start_rec = ttk.Button(rec_top, text="Începe Înregistrarea", command=self.toggle_record, width=20)
        self.btn_start_rec.pack(side=tk.LEFT, padx=5)
        ToolTip(self.btn_start_rec, "Începe înregistrarea mișcărilor de mouse și tastelor.")

        self.btn_stop_rec = ttk.Button(rec_top, text="Oprește Înregistrarea", command=self.toggle_record,
                                       width=20, state='disabled')
        self.btn_stop_rec.pack(side=tk.LEFT, padx=5)
        ToolTip(self.btn_stop_rec, "Oprește înregistrarea și trimite automat sarcina în Schedule (în așteptare pentru programare)!")

        self.rec_status_label = ttk.Label(rec_top, text="Gata de înregistrare",
                                          foreground="blue", font=("Arial", 10, "bold"))
        self.rec_status_label.pack(side=tk.LEFT, padx=20)

        ttk.Label(rec_frame, text="Scurtături: F1 = Înregistrare Pornit/Oprit, F9 = Redare/Oprire, F10 = Pauză, ESC = OPRIRE, Shift+C = Setări Programare",
                  foreground="gray").pack(pady=(5, 0))
        lbl_f8 = ttk.Label(rec_frame,
                           text="🎯 F8 sau ` ~ (lângă 1) = CLIC pe iconița/butonul de sub mouse, sau CLIC + ENTER pe o casetă de text "
                                "(fără să apese acum)  •  Shift+F8 = doar ENTER  •  Ctrl+F8 = DUBLU-CLIC  •  F7 = doar CLIC",
                           foreground="#008000", font=("Arial", 9, "bold"))
        lbl_f8.pack(pady=(3, 0))
        ToolTip(lbl_f8, "În timpul înregistrării (F1):\n"
                        "• F8 sau ` ~ (tasta de lângă 1) — se uită la cursorul mouse-ului:\n"
                        "    – pe o iconiță / un buton (săgeată sau mânuță) → înregistrează CLIC acolo\n"
                        "      (ex: iconița din bara Total Commander care deschide un program);\n"
                        "    – pe o casetă de text (cursorul „I”) → înregistrează CLIC în casetă + ENTER\n"
                        "      (ex: mesajul scris deja în chat va pleca abia la ora programată).\n"
                        "• Shift+F8 / Shift+` = doar ENTER     • Ctrl+F8 / Ctrl+` = DUBLU-CLIC\n"
                        "• F7 = doar CLIC     • Ctrl+F7 = DUBLU-CLIC\n"
                        "Nimic nu se apasă în timpul înregistrării.\n"
                        "Aceste taste sunt BLOCATE în timpul înregistrării: programul din față nu le primește\n"
                        "(ex: F8 în Total Commander nu mai deschide Ștergerea, iar ` nu apare scris în chat).\n"
                        "Apoi continuați înregistrarea sau o opriți cu F1.")

        # Play Frame
        play_frame = ttk.LabelFrame(main, text="Redare Sarcină", padding=10)
        play_frame.pack(fill=tk.X, padx=4, pady=4)
        play_top = ttk.Frame(play_frame); play_top.pack(fill=tk.X)

        self.btn_play = ttk.Button(play_top, text="▶ Redă", command=self.play_task, width=15)
        self.btn_play.pack(side=tk.LEFT, padx=5)
        ToolTip(self.btn_play, "Rulează evenimentele încărcate în prezent.")

        self.btn_pause = ttk.Button(play_top, text="Pauză (F10)", command=self.pause_task,
                                    width=15, state='disabled')
        self.btn_pause.pack(side=tk.LEFT, padx=5)

        self.btn_stop = ttk.Button(play_top, text="Oprește Redarea (Esc)", command=self.safe_stop,
                                   width=20, state='disabled')
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        self.play_status_label = ttk.Label(play_top, text="Nu rulează nimic",
                                           foreground="green", font=("Arial", 10, "bold"))
        self.play_status_label.pack(side=tk.LEFT, padx=20)

        controls = ttk.Frame(play_frame); controls.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(controls, text="Viteză Redare:").pack(side=tk.LEFT, padx=5)
        self.speed_var = tk.DoubleVar(value=2.0)
        self.speed_slider = ttk.Scale(controls, from_=0.1, to=5.0, variable=self.speed_var,
                                      orient=tk.HORIZONTAL, length=180, command=self.on_speed_change)
        self.speed_slider.pack(side=tk.LEFT, padx=5)
        self.speed_label = ttk.Label(controls, text="2.0x", width=6); self.speed_label.pack(side=tk.LEFT, padx=5)
        # Sincronizăm viteza reală de redare cu valoarea afișată de slider
        # (înainte slider-ul arăta 2.0x dar redarea rula de fapt cu 1.0x)
        self.ctrl.playback_speed = self.speed_var.get()

        self.loop_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(controls, text="Repetă", variable=self.loop_var,
                        command=self.on_loop_change).pack(side=tk.LEFT, padx=10)

        ttk.Label(controls, text="×").pack(side=tk.LEFT)
        self.loop_count_var = tk.IntVar(value=1)
        loop_spin = ttk.Spinbox(controls, from_=1, to=999, width=4, textvariable=self.loop_count_var,
                                command=self.on_loop_count_change)
        loop_spin.pack(side=tk.LEFT, padx=4)

        self.continuous_var = tk.BooleanVar(value=False)
        self.cb_main_cont = ttk.Checkbutton(controls, text="Rulează continuu până la ESC/F9",
                                            variable=self.continuous_var, command=self.on_continuous_change)
        self.cb_main_cont.pack(side=tk.LEFT, padx=10)
        ToolTip(self.cb_main_cont, "Bifați pentru a rula continuu în buclă la playback. Când este bifat, noile sarcini înregistrate se vor trimite în Schedule cu modul continuu.")

        btn_sch_main = ttk.Button(controls, text="Setări Programare (Shift+C)",
                                  command=self.show_schedule_settings)
        btn_sch_main.pack(side=tk.LEFT, padx=10)
        ToolTip(btn_sch_main, "Deschide fereastra Schedule Settings cu cele 2 tab-uri (Programare Simplă și Sarcini Multiple).")

        self.schedule_badge_label = ttk.Label(controls, text="", font=("Arial", 9, "bold"))
        self.schedule_badge_label.pack(side=tk.LEFT, padx=5)

        self.btn_toggle_scheduler = ttk.Button(controls, text="▶ Activează Scheduler",
                                               command=self.toggle_scheduler_global)
        self.btn_toggle_scheduler.pack(side=tk.LEFT, padx=(5, 10))
        ToolTip(self.btn_toggle_scheduler, "Pornește sau oprește monitorizarea sarcinilor programate (Master On/Off).")

        self.mini_mode_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(controls, text="Mod Mini", variable=self.mini_mode_var,
                        command=self.toggle_mini_mode).pack(side=tk.RIGHT, padx=5)

        # Tabs
        tab_control = ttk.Notebook(main); tab_control.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        events_tab = ttk.Frame(tab_control); tab_control.add(events_tab, text="Evenimente")
        self._build_events_tab(events_tab)

        files_tab = ttk.Frame(tab_control); tab_control.add(files_tab, text="Fișiere Sarcini")
        self._build_files_tab(files_tab)

        self._update_ui_state()

    def _build_events_tab(self, parent):
        top_bar = ttk.Frame(parent); top_bar.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(top_bar, text="Evenimente înregistrate", font=("Arial", 10, "bold"))\
            .pack(side=tk.LEFT)

        tree_frame = ttk.Frame(parent); tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.tree = ttk.Treeview(tree_frame, columns=("#", "Time", "Type", "Details"),
                                 show='headings', selectmode='extended')
        self.tree.heading("#", text="#")
        self.tree.heading("Time", text="Timp (s)")
        self.tree.heading("Type", text="Tip")
        self.tree.heading("Details", text="Detalii")
        self.tree.column("#", width=50, anchor='center')
        self.tree.column("Time", width=100, anchor='center')
        self.tree.column("Type", width=150, anchor='w')
        self.tree.column("Details", width=800, anchor='w')
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # Bindings
        self.tree.bind('<Delete>', lambda e: self.delete_selected())
        self.tree.bind('<Double-Button-1>', lambda e: self.edit_selected())
        self.tree.bind('<Control-a>', lambda e: self.select_all())
        self.tree.bind('<Control-A>', lambda e: self.select_all())
        self.tree.bind('<Control-Delete>', lambda e: self.delete_selected())
        self.tree.bind('<Button-3>', self.show_context_menu)
        self._create_context_menu()

        # Toolbar
        sidebar = ttk.Frame(parent); sidebar.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(sidebar, text="▲ Mută Sus", command=self.move_up, width=12).pack(side=tk.LEFT, padx=2)
        ttk.Button(sidebar, text="▼ Mută Jos", command=self.move_down, width=12).pack(side=tk.LEFT, padx=2)
        ttk.Separator(sidebar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        ttk.Button(sidebar, text="✓ Selectează Tot", command=self.select_all, width=15).pack(side=tk.LEFT, padx=2)
        ttk.Button(sidebar, text="Deselectează", command=self.clear_selection, width=12).pack(side=tk.LEFT, padx=2)
        ttk.Separator(sidebar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        ttk.Button(sidebar, text="🗑 Șterge Selectate", command=self.delete_selected, width=17).pack(side=tk.LEFT, padx=2)
        ttk.Button(sidebar, text="✏️ Editează Pasul", command=self.edit_selected, width=14).pack(side=tk.LEFT, padx=2)
        ttk.Button(sidebar, text="➕ Adaugă Pas", command=self.add_step_dialog, width=13).pack(side=tk.LEFT, padx=2)
        ttk.Separator(sidebar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        ttk.Button(sidebar, text="📋 Jurnal", command=self.show_logs, width=10).pack(side=tk.LEFT, padx=2)
        btn_hist = ttk.Button(sidebar, text="📜 Istoric Sarcini", command=self.show_history, width=16)
        btn_hist.pack(side=tk.LEFT, padx=2)
        ToolTip(btn_hist, "Istoricul execuțiilor sarcinilor programate (reușite, amânate, ratate) — persistent pe disc.")

    def _create_context_menu(self):
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="Șterge Evenimentul (Del)", command=self.delete_selected)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Scalează Timpii (Ajustare Viteză)...", command=self.scale_timestamps)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Șterge Toate Evenimentele", command=self.delete_all_events)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Editează Pasul...", command=self.edit_selected)
        self.context_menu.add_command(label="Duplică Pasul", command=self.duplicate_selected)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Selectează Tot (Ctrl+A)", command=self.select_all)

    def show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item and item not in self.tree.selection():
            self.tree.selection_set(item)
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def _build_files_tab(self, parent):
        info = ttk.Label(parent, text="Manager Fișiere Sarcini - Salvați și încărcați mai multe configurații de sarcini", padding=20)
        info.pack()
        files_frame = ttk.Frame(parent); files_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        self.files_list = tk.Listbox(files_frame, height=15)
        self.files_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        btn_frame = ttk.Frame(files_frame); btn_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10)
        ttk.Button(btn_frame, text="Răsfoiește & Încarcă...", command=self.load_json, width=22).pack(pady=5)
        ttk.Button(btn_frame, text="Salvează Ca...", command=self.save_json, width=22).pack(pady=5)
        ttk.Button(btn_frame, text="Reîmprospătează Lista", command=self.refresh_files_list, width=22).pack(pady=5)
        ttk.Button(btn_frame, text="Șterge Fișierul", command=self.delete_task_file, width=22).pack(pady=5)
        self.refresh_files_list()

    # ----- UI helpers
    def _update_ui_state(self):
        rec = self.ctrl.recording
        play = self.ctrl.playing
        paused = self.ctrl.paused
        self.btn_start_rec.config(state='disabled' if rec else 'normal')
        self.btn_stop_rec.config(state='normal' if rec else 'disabled')
        self.rec_status_label.config(text="● Se înregistrează..." if rec else "Gata de înregistrare",
                                     foreground="red" if rec else "blue")
        self.btn_play.config(state='disabled' if (rec or play) else 'normal')
        self.btn_pause.config(state='normal' if play else 'disabled')
        self.btn_stop.config(state='normal' if play else 'disabled')
        self.play_status_label.config(
            text="⏸ Pauză" if paused else ("● Rulează..." if play else "Nu rulează nimic"),
            foreground="orange" if paused else ("red" if play else "green")
        )

    def _refresh_events_list(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        if not self.ctrl.steps:
            return
        first_time = self.ctrl.steps[0].timestamp
        for i, step in enumerate(self.ctrl.steps):
            rel_time = f"{step.get_relative_time(first_time):.3f}"
            self.tree.insert('', 'end', iid=f'step_{i}',
                             values=(i + 1, rel_time, step.kind, step.describe()))

    def _update_schedule_badge(self):
        sch = self.ctrl.schedule_config
        active_t = [t for t in sch.tasks if t.enabled]
        if not sch.enabled:
            self.schedule_badge_label.config(text="📅 Scheduler: OPRIT", foreground="gray")
            if hasattr(self, 'btn_toggle_scheduler'):
                self.btn_toggle_scheduler.config(text="▶ Activează Scheduler")
        else:
            self.schedule_badge_label.config(
                text=f"📅 Scheduler: PORNIT ({len(active_t)} sarcini active)",
                foreground="#008000" if active_t else "#CC8800"
            )
            if hasattr(self, 'btn_toggle_scheduler'):
                self.btn_toggle_scheduler.config(text="⏸ Pauză Scheduler")

    def toggle_scheduler_global(self):
        new_state = not self.ctrl.schedule_config.enabled
        self.ctrl.schedule_config.enabled = new_state
        self.ctrl.save_schedules_to_disk()
        self._update_schedule_badge()
        if new_state:
            active_t = [t for t in self.ctrl.schedule_config.tasks if t.enabled]
            self.log(f"🟢 [SCHEDULER] Master Scheduler ACTIVAT ({len(active_t)} sarcini active în așteptare).")
        else:
            self.log("🔴 [SCHEDULER] Master Scheduler OPRIT (Pauză).")

    def _poll_ui_queue(self):
        try:
            while True:
                kind, payload = self.ctrl.ui_queue.get_nowait()
                if kind == "log":
                    self._append_log_line(payload)
                elif kind == "refresh":
                    self._refresh_events_list()
                elif kind == "state":
                    self._update_ui_state()
        except queue.Empty:
            pass
        self.after(100, self._poll_ui_queue)

    # ----- Control callbacks
    def on_speed_change(self, val):
        speed = float(val)
        self.ctrl.playback_speed = speed
        self.speed_label.config(text=f"{speed:.1f}x")

    def on_loop_change(self):
        enabled = self.loop_var.get()
        self.ctrl.loop_enabled = enabled
        if enabled and self.continuous_var.get():
            messagebox.showwarning("Conflict de Configurare",
                                   "Nu puteți activa simultan 'Repetă' și 'Rulează continuu'.\n\n"
                                   "'Rulează continuu' va fi dezactivat.")
            self.continuous_var.set(False)
            self.ctrl.run_continuously = False

    def on_loop_count_change(self):
        self.ctrl.loop_count = self.loop_count_var.get()

    def on_continuous_change(self):
        enabled = self.continuous_var.get()
        self.ctrl.run_continuously = enabled
        if enabled and self.loop_var.get():
            messagebox.showwarning("Conflict de Configurare",
                                   "Nu puteți activa simultan 'Rulează continuu' și 'Repetă'.\n\n"
                                   "'Repetă' va fi dezactivat.")
            self.loop_var.set(False)
            self.ctrl.loop_enabled = False

    def toggle_record(self):
        if self.ctrl.recording:
            self.ctrl.stop_recording()
        else:
            self.ctrl.start_recording()
        self._update_ui_state()

    def play_task(self):
        sel = list(self.tree.selection())
        indices = [int(item.split('_')[1]) for item in sel] if sel else None
        self.ctrl.play(indices)
        self._update_ui_state()

    def pause_task(self):
        self.ctrl.toggle_pause()
        self._update_ui_state()

    def select_all(self):
        for item in self.tree.get_children():
            self.tree.selection_add(item)

    def clear_selection(self):
        self.tree.selection_remove(*self.tree.selection())

    def delete_selected(self):
        sel = list(self.tree.selection())
        if not sel:
            return
        indices = [int(item.split('_')[1]) for item in sel]
        self.ctrl.delete_indices(indices)
        self._refresh_events_list()

    def move_up(self):
        sel = list(self.tree.selection())
        if not sel: return
        indices = sorted([int(item.split('_')[1]) for item in sel])
        for i in indices:
            if i > 0:
                self.ctrl.steps[i-1], self.ctrl.steps[i] = self.ctrl.steps[i], self.ctrl.steps[i-1]
        self._refresh_events_list()
        for i in [max(0, idx-1) for idx in indices]:
            self.tree.selection_add(f'step_{i}')

    def move_down(self):
        sel = list(self.tree.selection())
        if not sel: return
        indices = sorted([int(item.split('_')[1]) for item in sel], reverse=True)
        for i in indices:
            if i < len(self.ctrl.steps) - 1:
                self.ctrl.steps[i+1], self.ctrl.steps[i] = self.ctrl.steps[i], self.ctrl.steps[i+1]
        self._refresh_events_list()
        for i in [min(len(self.ctrl.steps)-1, idx+1) for idx in indices]:
            self.tree.selection_add(f'step_{i}')

    def edit_selected(self):
        sel = self.tree.selection()
        if not sel or len(sel) != 1:
            messagebox.showinfo("Editare", "Selectați exact un pas pentru editare.")
            return
        idx = int(sel[0].split('_')[1])
        step = self.ctrl.steps[idx]

        dialog = tk.Toplevel(self); dialog.title(f"Editează Pasul #{idx+1}")
        dialog.geometry("600x300"); dialog.transient(self)

        ttk.Label(dialog, text=f"Tip: {step.kind}", font=("Arial", 10, "bold")).pack(pady=10)
        ttk.Label(dialog, text="Argumente (JSON):").pack()
        text = tk.Text(dialog, height=10, width=70); text.pack(padx=10, pady=5)
        text.insert('1.0', json.dumps(step.args, indent=2))

        def save():
            try:
                step.args = json.loads(text.get('1.0', 'end'))
                self._refresh_events_list()
                dialog.destroy()
                self.log(f"✏️ Edited step #{idx+1}")
            except json.JSONDecodeError as e:
                messagebox.showerror("Eroare", f"JSON invalid: {e}")

        ttk.Button(dialog, text="💾 Salvează", command=save).pack(pady=10)

    def add_step_dialog(self):
        dialog = tk.Toplevel(self); dialog.title("Adaugă Pas Nou")
        dialog.geometry("600x400"); dialog.transient(self)

        ttk.Label(dialog, text="Tip Pas:", font=("Arial", 10, "bold")).pack(pady=10)
        step_type = tk.StringVar(value="Wait")
        types = ["Wait", "LaunchPath", "ClickAt", "MoveMouse", "SendKeys", "Hotkey"]
        ttk.Combobox(dialog, textvariable=step_type, values=types, state='readonly', width=30).pack()

        ttk.Label(dialog, text="Argumente (JSON):").pack(pady=10)
        text = tk.Text(dialog, height=12, width=70); text.pack(padx=10, pady=5)
        text.insert('1.0', '{\n  "": ""\n}')

        def add():
            try:
                args = json.loads(text.get('1.0', 'end'))
                step = Step(step_type.get(), args)
                self.ctrl.add_step(step)
                self._refresh_events_list()
                dialog.destroy()
            except json.JSONDecodeError as e:
                messagebox.showerror("Eroare", f"JSON invalid: {e}")

        ttk.Button(dialog, text="➕ Adaugă Pasul", command=add).pack(pady=10)

    def scale_timestamps(self):
        sel = list(self.tree.selection())
        if not sel:
            messagebox.showinfo("Scalează Timpii", "Selectați evenimentele de scalat.")
            return

        dialog = tk.Toplevel(self); dialog.title("Scalează Timpii")
        dialog.geometry("400x200"); dialog.transient(self); dialog.resizable(False, False)

        ttk.Label(dialog, text="Ajustează viteza pentru evenimentele selectate:",
                  font=("Arial", 10, "bold")).pack(pady=15)
        frame = ttk.Frame(dialog); frame.pack(pady=10)

        ttk.Label(frame, text="Multiplicator viteză:").pack(side=tk.LEFT, padx=5)
        speed_var = tk.DoubleVar(value=1.0)
        speed_entry = ttk.Entry(frame, textvariable=speed_var, width=10); speed_entry.pack(side=tk.LEFT, padx=5)
        ttk.Label(frame, text="(0.5 = jumătate de viteză, 2.0 = viteză dublă)").pack(side=tk.LEFT, padx=5)

        def apply_scale():
            try:
                multiplier = speed_var.get()
                if multiplier <= 0:
                    messagebox.showerror("Eroare", "Viteza trebuie să fie mai mare decât 0.")
                    return
                indices = sorted([int(item.split('_')[1]) for item in sel])
                # Scalăm ȘI timestamp-urile (pauzele reale dintre pași vin din timestamp-uri,
                # nu doar din argumentele Wait/MoveMouse — altfel scalarea nu avea efect!)
                base_ts = self.ctrl.steps[indices[0]].timestamp
                for idx in indices:
                    step = self.ctrl.steps[idx]
                    step.timestamp = base_ts + (step.timestamp - base_ts) / multiplier
                    if step.kind == "Wait":
                        cur = step.args.get("seconds", 0)
                        step.args["seconds"] = cur / multiplier
                    elif step.kind == "MoveMouse":
                        cur = step.args.get("duration", 0)
                        step.args["duration"] = cur / multiplier
                self._refresh_events_list()
                self.log(f"⏱️ Scaled {len(indices)} events by {multiplier}x")
                dialog.destroy()
            except ValueError:
                messagebox.showerror("Eroare", "Valoare de viteză invalidă.")

        btn_frame = ttk.Frame(dialog); btn_frame.pack(pady=20)
        ttk.Button(btn_frame, text="Aplică", command=apply_scale, width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Anulează", command=dialog.destroy, width=12).pack(side=tk.LEFT, padx=5)

    def delete_all_events(self):
        if not self.ctrl.steps:
            messagebox.showinfo("Șterge Tot", "Nu există evenimente de șters.")
            return
        count = len(self.ctrl.steps)
        if messagebox.askyesno("Șterge Toate Evenimentele",
                               f"Sigur ștergeți toate cele {count} evenimente?\n\nAcțiunea nu poate fi anulată!"):
            self.ctrl.steps.clear()
            self._refresh_events_list()
            self.log(f"🗑️ Deleted all {count} events")

    def duplicate_selected(self):
        sel = list(self.tree.selection())
        if not sel:
            messagebox.showinfo("Duplicare", "Selectați evenimentele de duplicat.")
            return
        indices = sorted([int(item.split('_')[1]) for item in sel])
        insert_pos = indices[-1] + 1
        duplicated = []
        for idx in indices:
            original = self.ctrl.steps[idx]
            # Păstrăm timestamp-ul ORIGINAL! Cu time.time() (ora curentă), redarea calcula
            # o pauză uriașă înainte de pasul duplicat (diferența până la ora înregistrării).
            dup = Step(kind=original.kind, args=original.args.copy(), timestamp=original.timestamp)
            duplicated.append(dup)
        for i, dup in enumerate(duplicated):
            self.ctrl.steps.insert(insert_pos + i, dup)
        self._refresh_events_list()
        self.log(f"📋 Duplicated {len(duplicated)} events")
        for i in range(len(duplicated)):
            self.tree.selection_add(f'step_{insert_pos + i}')

    # ----- Files & schedule
    def show_logs(self):
        LogsWindow(self, self.log_text)

    def new_task(self):
        if messagebox.askyesno("Sarcină Nouă", "Ștergeți toți pașii și începeți o sarcină nouă?"):
            self.ctrl.steps.clear()
            self._refresh_events_list()
            self.log("📄 New task created")

    def save_json(self):
        fp = filedialog.asksaveasfilename(defaultextension=".json",
                                          filetypes=[["Fișiere Sarcini JSON","*.json"], ["Toate Fișierele","*.*"]],
                                          initialdir=os.getcwd())
        if not fp:
            return
        with open(fp, 'w', encoding='utf-8') as f:
            f.write(self.ctrl.to_json())
        self.log(f"💾 Saved: {fp}")
        self.refresh_files_list()

    def load_json(self):
        fp = filedialog.askopenfilename(filetypes=[["Fișiere Sarcini JSON","*.json"], ["Toate Fișierele","*.*"]],
                                        initialdir=os.getcwd())
        if not fp:
            return
        with open(fp, 'r', encoding='utf-8') as f:
            self.ctrl.load_json(f.read())
        self._refresh_events_list()
        self.log(f"📂 Loaded: {fp}")
        self._update_schedule_badge()

    def refresh_files_list(self):
        if not hasattr(self, 'files_list'):
            return
        self.files_list.delete(0, 'end')
        for f in os.listdir('.'):
            if f.endswith('.json') and f != "schedules.json":
                self.files_list.insert('end', f)

    def load_from_list(self):
        sel = self.files_list.curselection()
        if not sel:
            return
        filename = self.files_list.get(sel[0])
        with open(filename, 'r', encoding='utf-8') as f:
            self.ctrl.load_json(f.read())
        self._refresh_events_list()
        self.log(f"📂 Loaded: {filename}")
        self._update_schedule_badge()

    def delete_task_file(self):
        sel = self.files_list.curselection()
        if not sel:
            return
        filename = self.files_list.get(sel[0])
        if messagebox.askyesno("Ștergere", f"Ștergeți fișierul {filename}?"):
            os.remove(filename)
            self.refresh_files_list()
            self.log(f"🗑 Deleted: {filename}")

    def show_history(self):
        HistoryWindow.open(self, self.ctrl)

    def show_schedule_settings(self):
        # Prevenim deschiderea a două ferestre Schedule simultan (hotkey + buton)
        if getattr(self, '_schedule_dialog', None) is not None and self._schedule_dialog.winfo_exists():
            self._schedule_dialog.lift()
            self._schedule_dialog.focus_force()
            return
        dialog = ScheduleDialog(self, self.ctrl.schedule_config, self.ctrl)
        self._schedule_dialog = dialog
        self.wait_window(dialog)
        self._schedule_dialog = None
        if dialog.result is not None:
            self.ctrl.schedule_config = dialog.result
            self.ctrl.save_schedules_to_disk()
            self._update_schedule_badge()

            active_tasks = [t for t in self.ctrl.schedule_config.tasks if t.enabled]
            if self.ctrl.schedule_config.enabled:
                self.log(f"📅 Scheduler actualizat: {len(active_tasks)} sarcini active programate")
                for t in active_tasks:
                    self.log(f"   • {t.name}: {t.get_time_summary()} | {t.get_days_summary()} | {t.get_action_summary()} (Mod: {t.get_mode_summary()})")
            else:
                self.log("📅 Scheduler este oprit (Global Disabled).")

    def toggle_mini_mode(self):
        enabled = self.mini_mode_var.get()
        if enabled:
            if not self.mini_window or not self.mini_window.winfo_exists():
                self.iconify()
                self.after(200, lambda: self._create_mini_window())
        else:
            if self.mini_window and self.mini_window.winfo_exists():
                self.mini_window.destroy()
                self.mini_window = None
            self.deiconify()
            self.lift()
            self.focus_force()
            self.log("🔼 Mini Mode deactivated")

    def _create_mini_window(self):
        self.mini_window = MiniModeWindow(self, self.ctrl)
        self.log("🔽 Mini Mode activated")

    def show_about(self):
        messagebox.showinfo(
            "Despre BEBE Task Recorder",
            "BEBE Task Recorder v5.5\n\n"
            "Automatizare avansată a sarcinilor și Scheduler pentru sarcini multiple.\n"
            "Programare până la 20 de sarcini independente cu orare,\n"
            "zile, viteze de redare și acțiuni proprii.\n\n"
            "© 2025-2026 - Creat pentru automatizarea fluxului de lucru"
        )

    _log_file_lock = threading.Lock()

    def log(self, msg: str):
        """Thread-safe: poate fi apelat din Scheduler / Playback. Scrie și în bebe_log.txt (persistent)."""
        now = datetime.now()
        line = f"[{now:%H:%M:%S}] {msg}\n"
        try:
            with App._log_file_lock:
                with open(LOG_FILE, 'a', encoding='utf-8') as f:
                    f.write(f"[{now:%Y-%m-%d %H:%M:%S}] {msg}\n")
        except Exception:
            pass
        if threading.current_thread() is threading.main_thread():
            self._append_log_line(line)
        else:
            q = getattr(getattr(self, 'ctrl', None), 'ui_queue', None)
            if q is not None:
                q.put(("log", line))
            else:
                self._pending_logs.append(line)

    def _append_log_line(self, line: str):
        try:
            self.log_text.insert('end', line)
            self.log_text.see('end')
        except Exception:
            pass


# ============================ Main ============================

if __name__ == '__main__':
    try:
        print("\n" + "="*60)
        print("BEBE Task Recorder v5.5 Starting (Multi-Task Scheduler)...")
        print("="*60 + "\n")
        app = App()
        app.mainloop()
    except Exception as e:
        print(f"\n[ERROR] Application crashed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n[APP] Cleaning up...")
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        print("[APP] Shutdown complete")
