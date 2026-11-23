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

    def copy(self, new_id: bool = True):
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

    def copy(self):
        return ScheduleConfig(
            enabled=self.enabled,
            tasks=[t.copy(new_id=False) for t in self.tasks]
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
            return f"Wait {self.args.get('seconds', 0)} s"
        if self.kind == "LaunchPath":
            return f"Launch '{self.args.get('path', '')}' {self.args.get('args','')}"
        if self.kind == "ClickAt":
            return f"Click at ({self.args.get('x')}, {self.args.get('y')}) btn={self.args.get('button','left')}"
        if self.kind == "MoveMouse":
            return f"Move to ({self.args.get('x')}, {self.args.get('y')}) dur={self.args.get('duration',0)}"
        if self.kind == "SendKeys":
            txt = self.args.get('text','')
            return f"Type: '{txt[:40]}{'...' if len(txt) > 40 else ''}'"
        if self.kind == "Hotkey":
            return f"Hotkey: {' + '.join(self.args.get('combo', []))}"
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
    def __init__(self, controller):
        self.ctrl = controller
        self.running = False
        self._thread = None
        self.active_task_id: Optional[str] = None
        self._last_checked_minute = None
        self.user_stopped = False
        self._gap_skip_logged = set()

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

    def _scheduler_loop(self):
        while self.running:
            try:
                if self.ctrl.schedule_config.enabled:
                    self._check_and_run_tasks()
            except Exception as e:
                print(f"[SCHEDULER] Error in loop: {e}")

            time.sleep(0.5)

    def _check_and_run_tasks(self):
        now = datetime.now()
        current_day = now.strftime("%A")
        current_time_hm = now.strftime("%H:%M")
        current_time_hms = now.strftime("%H:%M:%S")
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
                            self.ctrl.stop()
                            self.active_task_id = None
            return

        # Playback-ul nu mai este activ
        self.active_task_id = None

        # Dacă utilizatorul a oprit manual sarcina în acest minut, așteptăm minutul următor
        if self.user_stopped and self._last_checked_minute == current_time_hm:
            return

        # 2. Căutare sarcină eligibilă pentru rulare
        for task in self.ctrl.schedule_config.tasks:
            # Sarcina trebuie să fie explicit bifată ca Activă
            if not task.enabled:
                continue

            # Verificare Zile / Dată:
            # Dacă sarcina este pe bază de dată specifică:
            if task.specific_date_enabled and task.specific_date:
                if task.specific_date != current_date:
                    continue
            else:
                # IMPORTANT: Dacă nu este bifată nicio zi din săptămână, sarcina NU are voie să ruleze!
                if not task.days:
                    continue
                if current_day not in task.days:
                    continue

            # Verificare mod de rulare și trigger
            trigger = False
            cur_key = f"{current_date} {current_time_hm}"
            same_instant = times_are_same_instant(task.from_time, task.to_time)

            if same_instant:
                # From = To: rulează o SINGURĂ DATĂ la acea secundă, complet, chiar dacă playback-ul durează mai mult
                if not is_time_matched(current_time_hm, current_time_hms, cur_secs, task.from_time):
                    continue
                if task.last_run_date == current_date:
                    continue
                trigger = True

            elif task.run_mode == "continuous":
                # Rulare continuă: trebuie să fie în intervalul orar (dacă este activat)
                if task.time_interval_enabled:
                    if not is_time_in_range(cur_secs, task.from_time, task.to_time):
                        continue
                trigger = True

            elif task.run_mode == "repeat":
                # Repetă la fiecare X minute în interiorul intervalului orar
                if task.time_interval_enabled:
                    if not is_time_in_range(cur_secs, task.from_time, task.to_time):
                        continue
                repeat_secs = max(1, task.repeat_minutes) * 60
                if (time.time() - task.last_run_timestamp) < repeat_secs:
                    continue
                trigger = True

            elif task.run_mode == "loop":
                # Declanșare la ora fixată (from_time) și rulare de N ori
                if not is_time_matched(current_time_hm, current_time_hms, cur_secs, task.from_time):
                    continue
                if task.last_run_minute == cur_key:
                    continue
                trigger = True

            else:
                # "once" - O singură dată la ora fixată (from_time)
                # IMPORTANT: O sarcină 'o singură dată' se declanșează strict când ceasul ajunge la ora/secunda fixată (from_time)!
                # NICIODATĂ retroactiv la o oră arbitrară din zi când se deschide programul!
                if not is_time_matched(current_time_hm, current_time_hms, cur_secs, task.from_time):
                    continue
                if task.last_run_date == current_date:
                    continue
                trigger = True

            if trigger:
                conflict = earlier_task_within_gap(
                    task, self.ctrl.schedule_config.tasks, current_day, current_date
                )
                if conflict:
                    skip_key = (task.id, current_date, current_time_hm)
                    if skip_key not in self._gap_skip_logged:
                        self._gap_skip_logged.add(skip_key)
                        self.ctrl.log(
                            f"⏭️ [SCHEDULER] Sarcina '{task.name}' ({task.from_time}) NU rulează: "
                            f"este la mai puțin de {MIN_TASK_GAP_SECONDS}s de '{conflict.name}' ({conflict.from_time})."
                        )
                    if same_instant or task.run_mode in ("once", "loop"):
                        task.last_run_date = current_date
                        task.last_run_minute = cur_key
                    continue

                if same_instant or task.run_mode == "once":
                    task.last_run_date = current_date
                elif task.run_mode == "loop":
                    task.last_run_minute = cur_key
                elif task.run_mode == "repeat":
                    task.last_run_timestamp = time.time()

                self.user_stopped = False
                self._last_checked_minute = current_time_hm
                self.active_task_id = task.id
                self._execute_scheduled_task(task, force_once=same_instant)
                break  # Rulăm o singură sarcină odată

    def _execute_scheduled_task(self, task: ScheduledTask, force_once: bool = False):
        steps = self.ctrl.get_steps_for_task(task)
        if not steps:
            self.ctrl.log(f"⚠️ [SCHEDULER] Sarcina '{task.name}' nu are pași de executat!")
            self.active_task_id = None
            return

        is_cont = (task.run_mode == "continuous") and not force_once
        if force_once:
            mode_desc = "O singură dată (From = To)"
        else:
            mode_desc = "Continuu în interval" if is_cont else ("O singură dată" if task.run_mode == "once" else task.get_mode_summary())
        self.ctrl.log(f"⏰ [SCHEDULER] S-a declanșat sarcina: '{task.name}' ({len(steps)} pași, Mod: {mode_desc}, Viteză: {task.playback_speed}x)")
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
        else: # "once" sau "repeat"
            self.ctrl.run_continuously = False
            self.ctrl.loop_enabled = False
            self.ctrl.loop_count = 1

        self.ctrl.play()
        self.ctrl.ui_queue.put(("state", None))


# ============================ Controller ============================

class TaskController:
    def __init__(self, log_fn):
        self.steps: List[Step] = []
        self.log = log_fn
        self.schedule_config = ScheduleConfig()

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
        self.play()
        self.ui_queue.put(("state", None))

    # ----- Persistence: schedules.json
    def save_schedules_to_disk(self, filepath="schedules.json"):
        try:
            data = {
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
                ]
            }
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"[CTRL] Schedules saved to {filepath} ({len(self.schedule_config.tasks)} tasks)")
        except Exception as e:
            print(f"[CTRL] Failed to save schedules to {filepath}: {e}")

    def load_schedules_from_disk(self, filepath="schedules.json") -> bool:
        if not os.path.exists(filepath):
            return False
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                obj = json.load(f)
            # Scheduler-ul pornește ÎNTOTDEAUNA OPRIT (OFF) la pornirea aplicației
            # pentru a permite utilizatorului să vadă și configureze programul fără surprize
            self.schedule_config.enabled = False
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
                    to_time=t_data.get('to_time', '17:00')
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

        def on_click(x, y, button, pressed):
            if not self.recording:
                return
            if pressed:
                self.add_step(Step("ClickAt", {"x": x, "y": y, "button": str(button).split(".")[-1]}))
                self.ui_queue.put(("refresh", None))

        def on_press(key):
            if not self.recording:
                return
            try:
                if hasattr(key, 'char') and key.char:
                    self.add_step(Step("SendKeys", {"text": key.char}))
                else:
                    name = str(key).replace('Key.', '')
                    # Nu înregistrăm tastele de control ale aplicației (F1=Record, ESC=Stop etc.),
                    # altfel la redare scriptul s-ar opri singur apăsându-le!
                    if name in ('f1', 'esc', 'f9', 'f10'):
                        return
                    self.add_step(Step("Hotkey", {"combo": [name]}))
                self.ui_queue.put(("refresh", None))
            except Exception as e:
                print(f"[CTRL] Error recording key: {e}")

        self._mouse_listener = mouse.Listener(on_click=on_click)
        self._kb_listener = kb.Listener(on_press=on_press)
        self._mouse_listener.start()
        self._kb_listener.start()
        print("[CTRL] Mouse and keyboard listeners started")

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
        if not self.steps:
            self.log("ℹ️ No steps to play.")
            return

        self.playing = True
        self.paused = False

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
                        time.sleep(delay)
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

                self.log("✅ Playback completed")
            except Exception as e:
                self.log(f"❌ Playback error: {e}")
            finally:
                self.playing = False
                self.paused = False
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

        def adjusted_sleep(seconds):
            time.sleep(seconds / max(0.01, self.playback_speed))

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
            pyautogui.click(a.get("x", 0), a.get("y", 0), button=a.get("button", "left"))
        elif k == "SendKeys":
            text = a.get("text", "")
            interval = float(a.get("interval", 0)) / max(0.01, self.playback_speed)
            if interval == 0 and len(text) > 1:
                interval = 0.01 / max(0.01, self.playback_speed)
            pyautogui.typewrite(text, interval=interval)
        elif k == "Hotkey":
            combo = a.get("combo", [])
            if combo:
                pyautogui.hotkey(*combo)


# ============================ Schedule Settings Window (Tabs) ============================

class ScheduleDialog(tk.Toplevel):
    def __init__(self, parent, schedule_config: ScheduleConfig, controller: TaskController):
        super().__init__(parent)
        self.title("Schedule Settings")
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
        self.notebook.add(self.tab1_frame, text="📅 Programare Simplă (Single Task)")
        self._build_tab1_ui(self.tab1_frame)

        # Tab 2: Sarcini Multiple & Manager
        self.tab2_frame = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(self.tab2_frame, text="📋 Sarcini Multiple & Manager (Multi-Task)")
        self._build_tab2_ui(self.tab2_frame)

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    # ======================== TAB 1: FORMULAR SIMPLU ========================

    def _build_tab1_ui(self, parent):
        # 1. Activare generală
        top_box = ttk.Frame(parent)
        top_box.pack(fill=tk.X, pady=(0, 10))

        cb_enable = ttk.Checkbutton(top_box, text="Enable Schedule", variable=self.enable_global_var)
        cb_enable.pack(side=tk.LEFT)
        ToolTip(cb_enable, "Comutator General: Bifați pentru a porni Scheduler-ul automat. Dacă este debifat, nicio sarcină nu va rula automat.")

        self.tab1_task_indicator = ttk.Label(top_box, text="", font=("Arial", 9, "bold"), foreground="#4B0082")
        self.tab1_task_indicator.pack(side=tk.RIGHT)
        ToolTip(self.tab1_task_indicator, "Indică sarcina activă ale cărei setări sunt afișate în acest formular.")

        # 2. Zile (Days)
        lbl_days = ttk.Label(parent, text="Days:")
        lbl_days.pack(anchor='w', pady=(0, 5))

        days_frame = ttk.LabelFrame(parent, padding=12)
        days_frame.pack(fill=tk.X, pady=(0, 12))

        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        for i, day in enumerate(days):
            var = self.tab1_day_vars[day]
            row = i // 2
            col = i % 2
            cb = ttk.Checkbutton(days_frame, text=day, variable=var, command=self._on_tab1_fields_changed)
            cb.grid(row=row, column=col, sticky='w', padx=15, pady=4)
            ToolTip(cb, f"Bifați dacă doriți ca sarcina să se execute în ziua de {day}.\nIMPORTANT: Dacă nicio zi nu este bifată, sarcina NU va rula!")

        btn_days_row = ttk.Frame(days_frame)
        btn_days_row.grid(row=4, column=0, columnspan=2, pady=(10, 0))

        btn_today = ttk.Button(btn_days_row, text="📅 Select Today", command=self.tab1_select_today)
        btn_today.pack(side=tk.LEFT, padx=5)
        ToolTip(btn_today, "Selectează doar ziua de AZI.")

        btn_tomorrow = ttk.Button(btn_days_row, text="📅 Select Tomorrow (Mâine)", command=self.tab1_select_tomorrow)
        btn_tomorrow.pack(side=tk.LEFT, padx=5)
        ToolTip(btn_tomorrow, "Selectează doar ziua de MÂINE.")

        btn_all_days = ttk.Button(btn_days_row, text="✓ All Days", command=self.tab1_select_all_days)
        btn_all_days.pack(side=tk.LEFT, padx=5)
        ToolTip(btn_all_days, "Selectează toate zilele din săptămână.")

        btn_clear_days = ttk.Button(btn_days_row, text="✕ Clear Days", command=self.tab1_clear_days)
        btn_clear_days.pack(side=tk.LEFT, padx=5)
        ToolTip(btn_clear_days, "Deselectează toate zilele.")

        # 3. Interval Orar (Time Interval)
        lbl_ti = ttk.Label(parent, text="Time Interval (Optional)")
        lbl_ti.pack(anchor='w', pady=(5, 5))

        time_frame = ttk.LabelFrame(parent, padding=12)
        time_frame.pack(fill=tk.X, pady=(0, 15))

        cb_time_enable = ttk.Checkbutton(time_frame, text="Enable time interval",
                                         variable=self.tab1_interval_enabled_var,
                                         command=self._on_tab1_time_enable_change)
        cb_time_enable.pack(anchor='w', pady=(0, 8))
        ToolTip(cb_time_enable, "Bifați pentru a restrânge execuția la un anumit interval orar.")

        from_frame = ttk.Frame(time_frame); from_frame.pack(fill=tk.X, pady=3)
        ttk.Label(from_frame, text="From time:", width=12).pack(side=tk.LEFT)
        self.tab1_from_entry = ttk.Entry(from_frame, textvariable=self.tab1_from_time_var, width=12)
        self.tab1_from_entry.pack(side=tk.LEFT, padx=5)
        self.tab1_from_entry.bind("<KeyRelease>", lambda e: self._on_tab1_fields_changed())
        ToolTip(self.tab1_from_entry, "Ora de început (format HH:MM sau HH:MM:SS, ex: 12:16 sau 12:16:05, AM/PM).")
        ttk.Label(from_frame, text="(ex: 21:00 sau 21:16:05 for 9 PM, 09:16:05 for 9 AM)", foreground="gray").pack(side=tk.LEFT, padx=5)

        to_frame = ttk.Frame(time_frame); to_frame.pack(fill=tk.X, pady=3)
        ttk.Label(to_frame, text="To time:", width=12).pack(side=tk.LEFT)
        self.tab1_to_entry = ttk.Entry(to_frame, textvariable=self.tab1_to_time_var, width=12)
        self.tab1_to_entry.pack(side=tk.LEFT, padx=5)
        self.tab1_to_entry.bind("<KeyRelease>", lambda e: self._on_tab1_fields_changed())
        ToolTip(self.tab1_to_entry, "Ora de sfârșit (format HH:MM sau HH:MM:SS, ex: 12:16 sau 12:16:05, AM/PM).")
        ttk.Label(to_frame, text="(ex: 08:00 sau 08:16:05 for 8 AM, 20:16:05 for 8 PM)", foreground="gray").pack(side=tk.LEFT, padx=5)

        lbl_overnight = ttk.Label(time_frame, text="⏰ Overnight interval: Ex: 21:00 - 03:00 sau 21:00:00 - 03:00:00",
                                  foreground="blue", font=("Arial", 9))
        lbl_overnight.pack(anchor='w', pady=(6, 4))
        ToolTip(lbl_overnight, "Sunt acceptate și intervale peste noapte (ex: 21:00 - 03:00 sau 21:00:30 - 03:00:15).")

        lbl_same = ttk.Label(
            time_frame,
            text="If From time = To time (ex: 14:03:03 – 14:03:03) the task runs ONCE at that second, even if playback lasts longer. "
                 "Tasks need at least 30 seconds between From times, otherwise the later task will not run.",
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
            text="Run continuously in interval (Rulează continuu în interval)",
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

        btn_new_task = ttk.Button(btn_bar, text="➕ New Task", width=14, command=self.tab1_new_task)
        btn_new_task.pack(side=tk.LEFT, padx=5)
        ToolTip(btn_new_task, "Resetează formularul pentru o sarcină nouă, păstrând în memoria Scheduler-ului sarcina curentă.")

        btn_save_as_new = ttk.Button(btn_bar, text="💾 Salvează ca sarcină nouă", width=26, command=self.tab1_save_as_new_task)
        btn_save_as_new.pack(side=tk.LEFT, padx=5)
        ToolTip(btn_save_as_new, "Salvează setările curente ca o sarcină nouă în lista de Sarcini Multiple (Tab 2).")

        btn_save = ttk.Button(btn_bar, text="Save", width=12, command=self.on_save)
        btn_save.pack(side=tk.RIGHT, padx=5)
        ToolTip(btn_save, "Salvează toate sarcinile pe disc și închide fereastra.")

        btn_cancel = ttk.Button(btn_bar, text="Cancel", width=12, command=self.destroy)
        btn_cancel.pack(side=tk.RIGHT, padx=5)
        ToolTip(btn_cancel, "Închide fereastra fără a salva modificările recente.")

        btn_test = ttk.Button(btn_bar, text="▶ Test Play", width=12, command=self.test_current_task)
        btn_test.pack(side=tk.RIGHT, padx=5)
        ToolTip(btn_test, "Rulează imediat pașii acestei sarcini pentru a verifica dacă funcționează.")

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
        ToolTip(btn_save, "Salvează lista de sarcini (adăugare, redenumire, ștergere, activare, duplicare) pe disc și închide fereastra.")

        btn_cancel = ttk.Button(bottom_bar, text="✕ Anulează", width=12, command=self.destroy)
        btn_cancel.pack(side=tk.LEFT, padx=4)
        ToolTip(btn_cancel, "Închide fereastra fără salvare.")

        btn_test = ttk.Button(bottom_bar, text="▶ Testează Sarcina Acum", width=25, command=self.test_current_task)
        btn_test.pack(side=tk.RIGHT, padx=4)
        ToolTip(btn_test, "Rulează imediat pașii sarcinii selectate pentru verificare.")

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
                                "Shift+Click / Ctrl+Click = selectați mai multe sarcini (pentru ștergere).\n"
                                "Trageți cu mouse-ul (Drag & Drop) o sarcină pentru a o muta în ordinea dorită.")

        self.task_tree.bind("<<TreeviewSelect>>", self._on_tree_select)
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

        r_file = ttk.Radiobutton(action_lf, text="Rulează un fișier de sarcini (.json) salvat:",
                                 variable=self.tab2_action_type_var, value="file", command=self._on_tab2_field_changed)
        r_file.pack(anchor='w')
        ToolTip(r_file, "Încarcă și rulează pașii dintr-un fișier .json salvat pe disc.")

        file_row = ttk.Frame(action_lf); file_row.pack(fill=tk.X, pady=(2, 4), padx=20)
        self.tab2_file_combo = ttk.Combobox(file_row, textvariable=self.tab2_task_file_var, width=32)
        self.tab2_file_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.tab2_file_combo.bind("<<ComboboxSelected>>", lambda e: self._on_tab2_field_changed())
        ToolTip(self.tab2_file_combo, "Alegeți un fișier .json din directorul curent.")

        btn_browse = ttk.Button(file_row, text="📂 Browse...", width=11, command=self.browse_task_file_tab2)
        btn_browse.pack(side=tk.LEFT, padx=3)
        ToolTip(btn_browse, "Răsfoiește computerul pentru a alege orice fișier .json.")

        btn_save_steps = ttk.Button(file_row, text="💾 Salvează ca fișier...", command=self.save_steps_as_file_tab2)
        btn_save_steps.pack(side=tk.LEFT, padx=2)
        ToolTip(btn_save_steps, "Exportă pașii acestei sarcini într-un fișier nou .json.")

        r_curr = ttk.Radiobutton(action_lf, text="Rulează evenimentele încărcate în prezent în aplicație (Current Events)",
                                 variable=self.tab2_action_type_var, value="current", command=self._on_tab2_field_changed)
        r_curr.pack(anchor='w')
        ToolTip(r_curr, "Execută pașii aflați în memoria ecranului principal.")

        self._refresh_tab2_files_dropdown()

        # 3. Mod de Rulare & Viteză
        mode_lf = ttk.LabelFrame(self.tab2_details_lf, text="⚡ Mod de Rulare & Viteză Playback", padding=6)
        mode_lf.pack(fill=tk.X, pady=5)

        m_row2 = ttk.Frame(mode_lf); m_row2.pack(fill=tk.X, pady=2)
        r_once = ttk.Radiobutton(m_row2, text="O singură dată la începutul intervalului (Run Once per day)",
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
        ttk.Label(m_row4, text="ori consecutiv (Loop count)").pack(side=tk.LEFT)

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
        cb_spec = ttk.Checkbutton(spec_box, text="Rulează doar la data specifică (One-time):",
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

        cb_ti2 = ttk.Checkbutton(time_lf, text="Enable time interval for this task",
                                 variable=self.tab2_interval_enabled_var,
                                 command=self._on_tab2_time_enable_change)
        cb_ti2.pack(anchor='w', pady=(0, 3))
        ToolTip(cb_ti2, "Bifați pentru a impune orele de început (From time) și sfârșit (To time).")

        from_row = ttk.Frame(time_lf); from_row.pack(fill=tk.X, pady=2)
        ttk.Label(from_row, text="From time:", width=12).pack(side=tk.LEFT)
        self.tab2_from_entry = ttk.Entry(from_row, textvariable=self.tab2_from_time_var, width=12)
        self.tab2_from_entry.pack(side=tk.LEFT, padx=5)
        self.tab2_from_entry.bind("<KeyRelease>", lambda e: self._on_tab2_field_changed())
        self.tab2_from_entry.bind("<FocusOut>", lambda e: self._on_tab2_field_changed())
        ToolTip(self.tab2_from_entry, "Ora de început (format HH:MM sau HH:MM:SS, ex: 12:16 sau 12:16:05, AM/PM).")
        ttk.Label(from_row, text="(ex: 09:00 or 09:16:05 for AM, 21:16:05 for PM)", foreground="gray").pack(side=tk.LEFT, padx=5)

        to_row = ttk.Frame(time_lf); to_row.pack(fill=tk.X, pady=2)
        ttk.Label(to_row, text="To time:", width=12).pack(side=tk.LEFT)
        self.tab2_to_entry = ttk.Entry(to_row, textvariable=self.tab2_to_time_var, width=12)
        self.tab2_to_entry.pack(side=tk.LEFT, padx=5)
        self.tab2_to_entry.bind("<KeyRelease>", lambda e: self._on_tab2_field_changed())
        self.tab2_to_entry.bind("<FocusOut>", lambda e: self._on_tab2_field_changed())
        ToolTip(self.tab2_to_entry, "Ora de sfârșit (format HH:MM sau HH:MM:SS, ex: 12:16 sau 12:16:05, AM/PM).")
        ttk.Label(to_row, text="(ex: 17:00 or 17:16:05 for PM, 08:16:05 for AM)", foreground="gray").pack(side=tk.LEFT, padx=5)

        ttk.Label(time_lf, text="⏰ Overnight interval: Ex: 21:00 - 03:00 or 21:00:00 - 03:00:00",
                  foreground="#00008B", font=("Arial", 8)).pack(anchor='w', pady=(3, 0))
        lbl_same2 = ttk.Label(
            time_lf,
            text="If From time = To time the task runs ONCE at that second (full playback). "
                 "Minimum 30 seconds between tasks' From times, otherwise the later task will not run.",
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

    def test_current_task(self):
        tab_id = self.notebook.select()
        tab_name = self.notebook.tab(tab_id, "text")

        idx = self.current_selected_index
        if idx is None or not (0 <= idx < len(self.tasks)):
            messagebox.showinfo("Informație", "Nu este selectată nicio sarcină de testat.", parent=self)
            return

        if "Single Task" in tab_name:
            self._save_tab1_to_task(self.tasks[idx])
        else:
            self._save_tab2_to_task(idx)

        task = self.tasks[idx]
        self.ctrl.test_play_task(task)

    def on_save(self):
        # Salvează tab-ul activ în sarcina curentă
        idx = self.current_selected_index
        tab_id = self.notebook.select()
        tab_name = self.notebook.tab(tab_id, "text")

        if idx is not None and 0 <= idx < len(self.tasks):
            if "Single Task" in tab_name:
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
            # Resetăm last_run_date pentru ca sarcinile reconfigurate să poată rula
            t.last_run_date = ""

        # Avertizări finale: sarcini fără zile bifate / master oprit (cu reparare automată opțională)
        self._check_runnable_warnings(self.tasks)

        self.config_obj.enabled = self.enable_global_var.get()
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
        ttk.Label(btn_frame, text="Record", font=('Arial', 7)).grid(row=1, column=0)

        self.btn_play = ttk.Button(btn_frame, text="▶", width=3, command=self.play_task)
        self.btn_play.grid(row=0, column=1, padx=3, pady=3, sticky='nsew')
        ttk.Label(btn_frame, text="Play", font=('Arial', 7)).grid(row=1, column=1)

        self.btn_pause = ttk.Button(btn_frame, text="⏸", width=3, command=self.pause_task)
        self.btn_pause.grid(row=0, column=2, padx=3, pady=3, sticky='nsew')
        ttk.Label(btn_frame, text="Pause", font=('Arial', 7)).grid(row=1, column=2)

        self.btn_stop = ttk.Button(btn_frame, text="⏹", width=3, command=self.stop_task)
        self.btn_stop.grid(row=0, column=3, padx=3, pady=3, sticky='nsew')
        ttk.Label(btn_frame, text="Stop", font=('Arial', 7)).grid(row=1, column=3)

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
        self.title("BEBE - Logs")
        self.geometry("820x520")
        self.log_source = log_text_widget
        self._build_ui()
        self._refresh_logs()
        self.after(1000, self._auto_refresh)

    def _build_ui(self):
        toolbar = ttk.Frame(self); toolbar.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(toolbar, text="📋 Copy All", command=self.copy_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="💾 Save to File", command=self.save_to_file).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="🗑 Clear Logs", command=self.clear_logs).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="📝 Open in Notepad", command=self.open_notepad).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="🔄 Refresh", command=self._refresh_logs).pack(side=tk.LEFT, padx=2)

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
                                          filetypes=[["Text Files","*.txt"], ["All Files","*.*"]])
        if fp:
            with open(fp, 'w', encoding='utf-8') as f:
                f.write(self.text.get('1.0', 'end-1c'))

    def clear_logs(self):
        if messagebox.askyesno("Clear Logs", "Clear all logs?"):
            self.log_source.delete('1.0', 'end')
            self._refresh_logs()

    def open_notepad(self):
        temp_file = os.path.join(os.environ.get('TEMP', '.'), 'bebe_logs.txt')
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(self.text.get('1.0', 'end-1c'))
        subprocess.Popen(['notepad.exe', temp_file])


# ============================ Main App ============================

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("BEBE - Task Recorder - Version 5.5")
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

        self.ctrl = TaskController(self.log)
        self.mini_window = None

        self._build_menu()
        self._build_ui()
        self._wire_hotkeys()
        self._update_schedule_badge()
        self.after(100, self._poll_ui_queue)

    # ----- Menu
    def _build_menu(self):
        menubar = tk.Menu(self); self.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New Task", command=self.new_task, accelerator="Ctrl+N")
        file_menu.add_command(label="Open Task...", command=self.load_json, accelerator="Ctrl+O")
        file_menu.add_command(label="Save Task", command=self.save_json, accelerator="Ctrl+S")
        file_menu.add_separator()
        file_menu.add_command(label="Schedule Settings...", command=self.show_schedule_settings, accelerator="Shift+C")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit)

        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.show_about)

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
            keyboard.add_hotkey('shift+c', lambda: self.after(0, self.show_schedule_settings))
        except Exception as e:
            print(f"[HOTKEYS] Warning: {e}")

    def safe_stop(self):
        self.ctrl.stop()
        self._update_ui_state()
        self._refresh_events_list()

    def _toggle_play_hotkey(self):
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
        rec_frame = ttk.LabelFrame(main, text="Record Task", padding=10)
        rec_frame.pack(fill=tk.X, padx=4, pady=4)
        rec_top = ttk.Frame(rec_frame); rec_top.pack(fill=tk.X)

        self.btn_start_rec = ttk.Button(rec_top, text="Start Recording", command=self.toggle_record, width=20)
        self.btn_start_rec.pack(side=tk.LEFT, padx=5)
        ToolTip(self.btn_start_rec, "Începe înregistrarea mișcărilor de mouse și tastelor.")

        self.btn_stop_rec = ttk.Button(rec_top, text="Stop Recording", command=self.toggle_record,
                                       width=20, state='disabled')
        self.btn_stop_rec.pack(side=tk.LEFT, padx=5)
        ToolTip(self.btn_stop_rec, "Oprește înregistrarea și trimite automat sarcina în Schedule (în așteptare pentru programare)!")

        self.rec_status_label = ttk.Label(rec_top, text="Ready for Recording",
                                          foreground="blue", font=("Arial", 10, "bold"))
        self.rec_status_label.pack(side=tk.LEFT, padx=20)

        ttk.Label(rec_frame, text="Hotkeys: F1 = Record On/Off, F9 = Play/Stop, F10 = Pause, ESC = STOP, Shift+C = Schedule Settings",
                  foreground="gray").pack(pady=(5, 0))

        # Play Frame
        play_frame = ttk.LabelFrame(main, text="Play Task", padding=10)
        play_frame.pack(fill=tk.X, padx=4, pady=4)
        play_top = ttk.Frame(play_frame); play_top.pack(fill=tk.X)

        self.btn_play = ttk.Button(play_top, text="Play", command=self.play_task, width=15)
        self.btn_play.pack(side=tk.LEFT, padx=5)
        ToolTip(self.btn_play, "Rulează evenimentele încărcate în prezent.")

        self.btn_pause = ttk.Button(play_top, text="Pause (F10)", command=self.pause_task,
                                    width=15, state='disabled')
        self.btn_pause.pack(side=tk.LEFT, padx=5)

        self.btn_stop = ttk.Button(play_top, text="Stop Playback (Esc)", command=self.safe_stop,
                                   width=20, state='disabled')
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        self.play_status_label = ttk.Label(play_top, text="Nothing is Playing",
                                           foreground="green", font=("Arial", 10, "bold"))
        self.play_status_label.pack(side=tk.LEFT, padx=20)

        controls = ttk.Frame(play_frame); controls.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(controls, text="Playback Speed:").pack(side=tk.LEFT, padx=5)
        self.speed_var = tk.DoubleVar(value=2.0)
        self.speed_slider = ttk.Scale(controls, from_=0.1, to=5.0, variable=self.speed_var,
                                      orient=tk.HORIZONTAL, length=180, command=self.on_speed_change)
        self.speed_slider.pack(side=tk.LEFT, padx=5)
        self.speed_label = ttk.Label(controls, text="2.0x", width=6); self.speed_label.pack(side=tk.LEFT, padx=5)
        # Sincronizăm viteza reală de redare cu valoarea afișată de slider
        # (înainte slider-ul arăta 2.0x dar redarea rula de fapt cu 1.0x)
        self.ctrl.playback_speed = self.speed_var.get()

        self.loop_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(controls, text="Loop", variable=self.loop_var,
                        command=self.on_loop_change).pack(side=tk.LEFT, padx=10)

        ttk.Label(controls, text="×").pack(side=tk.LEFT)
        self.loop_count_var = tk.IntVar(value=1)
        loop_spin = ttk.Spinbox(controls, from_=1, to=999, width=4, textvariable=self.loop_count_var,
                                command=self.on_loop_count_change)
        loop_spin.pack(side=tk.LEFT, padx=4)

        self.continuous_var = tk.BooleanVar(value=False)
        self.cb_main_cont = ttk.Checkbutton(controls, text="Run continuously until ESC/F9",
                                            variable=self.continuous_var, command=self.on_continuous_change)
        self.cb_main_cont.pack(side=tk.LEFT, padx=10)
        ToolTip(self.cb_main_cont, "Bifați pentru a rula continuu în buclă la playback. Când este bifat, noile sarcini înregistrate se vor trimite în Schedule cu modul continuu.")

        btn_sch_main = ttk.Button(controls, text="Schedule Settings (Shift+C)",
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
        ttk.Checkbutton(controls, text="Mini Mode", variable=self.mini_mode_var,
                        command=self.toggle_mini_mode).pack(side=tk.RIGHT, padx=5)

        # Tabs
        tab_control = ttk.Notebook(main); tab_control.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        events_tab = ttk.Frame(tab_control); tab_control.add(events_tab, text="Events")
        self._build_events_tab(events_tab)

        files_tab = ttk.Frame(tab_control); tab_control.add(files_tab, text="Task Files")
        self._build_files_tab(files_tab)

        self._update_ui_state()

    def _build_events_tab(self, parent):
        top_bar = ttk.Frame(parent); top_bar.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(top_bar, text="Events (Optimized with Context)", font=("Arial", 10, "bold"))\
            .pack(side=tk.LEFT)

        tree_frame = ttk.Frame(parent); tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.tree = ttk.Treeview(tree_frame, columns=("#", "Time", "Type", "Details"),
                                 show='headings', selectmode='extended')
        self.tree.heading("#", text="#")
        self.tree.heading("Time", text="Time (s)")
        self.tree.heading("Type", text="Type")
        self.tree.heading("Details", text="Details")
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
        ttk.Button(sidebar, text="▲ Move Up", command=self.move_up, width=12).pack(side=tk.LEFT, padx=2)
        ttk.Button(sidebar, text="▼ Move Down", command=self.move_down, width=12).pack(side=tk.LEFT, padx=2)
        ttk.Separator(sidebar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        ttk.Button(sidebar, text="✓ Select All", command=self.select_all, width=12).pack(side=tk.LEFT, padx=2)
        ttk.Button(sidebar, text="Clear Selection", command=self.clear_selection, width=12).pack(side=tk.LEFT, padx=2)
        ttk.Separator(sidebar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        ttk.Button(sidebar, text="🗑 Delete Selected", command=self.delete_selected, width=17).pack(side=tk.LEFT, padx=2)
        ttk.Button(sidebar, text="✏️ Edit Step", command=self.edit_selected, width=14).pack(side=tk.LEFT, padx=2)
        ttk.Button(sidebar, text="➕ Add Step", command=self.add_step_dialog, width=12).pack(side=tk.LEFT, padx=2)
        ttk.Separator(sidebar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        ttk.Button(sidebar, text="📋 Logs", command=self.show_logs, width=10).pack(side=tk.LEFT, padx=2)

    def _create_context_menu(self):
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="Delete Event (Del)", command=self.delete_selected)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Scale Timestamps (Speed Adjust)...", command=self.scale_timestamps)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Delete All Events", command=self.delete_all_events)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Edit Step...", command=self.edit_selected)
        self.context_menu.add_command(label="Duplicate Step", command=self.duplicate_selected)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Select All (Ctrl+A)", command=self.select_all)

    def show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item and item not in self.tree.selection():
            self.tree.selection_set(item)
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def _build_files_tab(self, parent):
        info = ttk.Label(parent, text="Task Files Manager - Save and load multiple task configurations", padding=20)
        info.pack()
        files_frame = ttk.Frame(parent); files_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        self.files_list = tk.Listbox(files_frame, height=15)
        self.files_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        btn_frame = ttk.Frame(files_frame); btn_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10)
        ttk.Button(btn_frame, text="Browse & Load...", command=self.load_json, width=15).pack(pady=5)
        ttk.Button(btn_frame, text="Save As...", command=self.save_json, width=15).pack(pady=5)
        ttk.Button(btn_frame, text="Refresh List", command=self.refresh_files_list, width=15).pack(pady=5)
        ttk.Button(btn_frame, text="Delete File", command=self.delete_task_file, width=15).pack(pady=5)
        self.refresh_files_list()

    # ----- UI helpers
    def _update_ui_state(self):
        rec = self.ctrl.recording
        play = self.ctrl.playing
        paused = self.ctrl.paused
        self.btn_start_rec.config(state='disabled' if rec else 'normal')
        self.btn_stop_rec.config(state='normal' if rec else 'disabled')
        self.rec_status_label.config(text="● Recording..." if rec else "Ready for Recording",
                                     foreground="red" if rec else "blue")
        self.btn_play.config(state='disabled' if (rec or play) else 'normal')
        self.btn_pause.config(state='normal' if play else 'disabled')
        self.btn_stop.config(state='normal' if play else 'disabled')
        self.play_status_label.config(
            text="⏸ Paused" if paused else ("● Playing..." if play else "Nothing is Playing"),
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
            self.schedule_badge_label.config(text="📅 Scheduler: OFF", foreground="gray")
            if hasattr(self, 'btn_toggle_scheduler'):
                self.btn_toggle_scheduler.config(text="▶ Activează Scheduler")
        else:
            self.schedule_badge_label.config(
                text=f"📅 Scheduler: ON ({len(active_t)} active tasks)",
                foreground="#008000" if active_t else "#CC8800"
            )
            if hasattr(self, 'btn_toggle_scheduler'):
                self.btn_toggle_scheduler.config(text="⏸ Pauză Scheduler")

    def toggle_scheduler_global(self):
        new_state = not self.ctrl.schedule_config.enabled
        self.ctrl.schedule_config.enabled = new_state
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
                if kind == "refresh":
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
            messagebox.showwarning("Configuration Conflict",
                                   "You cannot enable both 'Loop' and 'Run continuously' at the same time.\n\n"
                                   "'Run continuously' will be disabled.")
            self.continuous_var.set(False)
            self.ctrl.run_continuously = False

    def on_loop_count_change(self):
        self.ctrl.loop_count = self.loop_count_var.get()

    def on_continuous_change(self):
        enabled = self.continuous_var.get()
        self.ctrl.run_continuously = enabled
        if enabled and self.loop_var.get():
            messagebox.showwarning("Configuration Conflict",
                                   "You cannot enable both 'Run continuously' and 'Loop' at the same time.\n\n"
                                   "'Loop' will be disabled.")
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
            messagebox.showinfo("Edit", "Please select exactly one step to edit")
            return
        idx = int(sel[0].split('_')[1])
        step = self.ctrl.steps[idx]

        dialog = tk.Toplevel(self); dialog.title(f"Edit Step #{idx+1}")
        dialog.geometry("600x300"); dialog.transient(self)

        ttk.Label(dialog, text=f"Type: {step.kind}", font=("Arial", 10, "bold")).pack(pady=10)
        ttk.Label(dialog, text="Arguments (JSON):").pack()
        text = tk.Text(dialog, height=10, width=70); text.pack(padx=10, pady=5)
        text.insert('1.0', json.dumps(step.args, indent=2))

        def save():
            try:
                step.args = json.loads(text.get('1.0', 'end'))
                self._refresh_events_list()
                dialog.destroy()
                self.log(f"✏️ Edited step #{idx+1}")
            except json.JSONDecodeError as e:
                messagebox.showerror("Error", f"Invalid JSON: {e}")

        ttk.Button(dialog, text="Save", command=save).pack(pady=10)

    def add_step_dialog(self):
        dialog = tk.Toplevel(self); dialog.title("Add New Step")
        dialog.geometry("600x400"); dialog.transient(self)

        ttk.Label(dialog, text="Step Type:", font=("Arial", 10, "bold")).pack(pady=10)
        step_type = tk.StringVar(value="Wait")
        types = ["Wait", "LaunchPath", "ClickAt", "MoveMouse", "SendKeys", "Hotkey"]
        ttk.Combobox(dialog, textvariable=step_type, values=types, state='readonly', width=30).pack()

        ttk.Label(dialog, text="Arguments (JSON):").pack(pady=10)
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
                messagebox.showerror("Error", f"Invalid JSON: {e}")

        ttk.Button(dialog, text="Add Step", command=add).pack(pady=10)

    def scale_timestamps(self):
        sel = list(self.tree.selection())
        if not sel:
            messagebox.showinfo("Scale Timestamps", "Please select events to scale")
            return

        dialog = tk.Toplevel(self); dialog.title("Scale Timestamps")
        dialog.geometry("400x200"); dialog.transient(self); dialog.resizable(False, False)

        ttk.Label(dialog, text="Adjust playback speed for selected events:",
                  font=("Arial", 10, "bold")).pack(pady=15)
        frame = ttk.Frame(dialog); frame.pack(pady=10)

        ttk.Label(frame, text="Speed multiplier:").pack(side=tk.LEFT, padx=5)
        speed_var = tk.DoubleVar(value=1.0)
        speed_entry = ttk.Entry(frame, textvariable=speed_var, width=10); speed_entry.pack(side=tk.LEFT, padx=5)
        ttk.Label(frame, text="(0.5 = half speed, 2.0 = double speed)").pack(side=tk.LEFT, padx=5)

        def apply_scale():
            try:
                multiplier = speed_var.get()
                if multiplier <= 0:
                    messagebox.showerror("Error", "Speed must be greater than 0")
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
                messagebox.showerror("Error", "Invalid speed value")

        btn_frame = ttk.Frame(dialog); btn_frame.pack(pady=20)
        ttk.Button(btn_frame, text="Apply", command=apply_scale, width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy, width=12).pack(side=tk.LEFT, padx=5)

    def delete_all_events(self):
        if not self.ctrl.steps:
            messagebox.showinfo("Delete All", "No events to delete")
            return
        count = len(self.ctrl.steps)
        if messagebox.askyesno("Delete All Events",
                               f"Are you sure you want to delete all {count} events?\n\nThis cannot be undone!"):
            self.ctrl.steps.clear()
            self._refresh_events_list()
            self.log(f"🗑️ Deleted all {count} events")

    def duplicate_selected(self):
        sel = list(self.tree.selection())
        if not sel:
            messagebox.showinfo("Duplicate", "Please select events to duplicate")
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
        if messagebox.askyesno("New Task", "Clear all steps and start new task?"):
            self.ctrl.steps.clear()
            self._refresh_events_list()
            self.log("📄 New task created")

    def save_json(self):
        fp = filedialog.asksaveasfilename(defaultextension=".json",
                                          filetypes=[["JSON Task Files","*.json"], ["All Files","*.*"]],
                                          initialdir=os.getcwd())
        if not fp:
            return
        with open(fp, 'w', encoding='utf-8') as f:
            f.write(self.ctrl.to_json())
        self.log(f"💾 Saved: {fp}")
        self.refresh_files_list()

    def load_json(self):
        fp = filedialog.askopenfilename(filetypes=[["JSON Task Files","*.json"], ["All Files","*.*"]],
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
        if messagebox.askyesno("Delete", f"Delete {filename}?"):
            os.remove(filename)
            self.refresh_files_list()
            self.log(f"🗑 Deleted: {filename}")

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
            "About BEBE Task Recorder",
            "BEBE Task Recorder v5.5\n\n"
            "Advanced task automation and Multi-Task Scheduler.\n"
            "Programare până la 20 de sarcini independente cu orare,\n"
            "zile, viteze de redare și acțiuni proprii.\n\n"
            "© 2025-2026 - Created for workflow automation"
        )

    def log(self, msg: str):
        ts = time.strftime('%H:%M:%S')
        self.log_text.insert('end', f"[{ts}] {msg}\n")
        self.log_text.see('end')


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
