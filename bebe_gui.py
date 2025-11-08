#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BEBE Task Recorder - GUI Version
Aplicatie cu interfata grafica pentru inregistrare si redare task-uri
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import time
import json
import sys
import threading
from datetime import datetime
from pathlib import Path
import pyautogui
from pynput import mouse, keyboard
from pynput.keyboard import Key, Controller as KeyboardController
import ctypes

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
    """Reda task-uri"""
    
    def __init__(self):
        self.playing = False
        self.keyboard_controller = KeyboardController()
        
    def play_events(self, events, speed=2.0, loop_count=1, callback=None):
        """Reda evenimente"""
        self.playing = True
        
        for loop in range(loop_count):
            for i, event in enumerate(events):
                if not self.playing:
                    break
                
                if i > 0:
                    delay = (event['timestamp'] - events[i-1]['timestamp']) / speed
                    if delay > 0:
                        time.sleep(delay)
                
                self.execute_event(event, i + 1, len(events), callback)
        
        self.playing = False
    
    def execute_event(self, event, current, total, callback=None):
        """Executa eveniment"""
        try:
            event_type = event['type']
            
            if event_type == 'mouse_move':
                x, y = event['x'], event['y']
                pyautogui.moveTo(x, y, duration=0)
                if callback:
                    callback(f"[{current}/{total}] Mouse Move ({x}, {y})")
            
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
                    callback(f"[{current}/{total}] Mouse {action} {button}")
            
            elif event_type == 'mouse_scroll':
                dy = event['dy']
                pyautogui.scroll(int(dy * 100))
                if callback:
                    callback(f"[{current}/{total}] Scroll")
            
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
                    callback(f"[{current}/{total}] Key Press {key_name}")
            
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
    
    def stop(self):
        """Opreste redarea"""
        self.playing = False


class BebeGUI:
    """Interfata grafica"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("BEBE - Task Recorder")
        self.root.geometry("1000x750")
        self.root.resizable(True, True)  # Permite redimensionare
        self.root.minsize(900, 700)  # Dimensiune minima
        
        # Verifica admin
        if not is_admin():
            if messagebox.askyesno("Privilegii Administrator", 
                "Aplicatia trebuie sa ruleze ca Administrator pentru a inregistra taste.\n\n"
                "Doresti sa repornesti ca Administrator?"):
                run_as_admin()
            else:
                messagebox.showwarning("Atentie", 
                    "Fara privilegii de administrator, nu vei putea inregistra taste din alte aplicatii!")
        
        self.recorder = TaskRecorder(callback=self.add_event_to_list)
        self.player = TaskPlayer()
        self.current_events = []
        self.tasks_dir = Path("tasks")
        self.tasks_dir.mkdir(exist_ok=True)
        
        self.setup_ui()
        
        # Refresh lista task-uri la startup
        self.root.after(100, self.refresh_task_list)
        
    def setup_ui(self):
        """Creeaza interfata"""
        # Frame principal cu grid layout
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Configurare grid pentru root
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        # === SECTIUNE INREGISTRARE ===
        record_frame = ttk.LabelFrame(main_frame, text="Inregistrare Task", padding="10")
        record_frame.pack(fill=tk.X, pady=(0, 10))
        
        btn_frame = ttk.Frame(record_frame)
        btn_frame.pack(fill=tk.X)
        
        self.btn_start = ttk.Button(btn_frame, text="Porneste inregistrarea", 
                                    command=self.start_recording, width=25)
        self.btn_start.pack(side=tk.LEFT, padx=5)
        
        self.btn_stop = ttk.Button(btn_frame, text="Opreste inregistrarea", 
                                   command=self.stop_recording, state=tk.DISABLED, width=25)
        self.btn_stop.pack(side=tk.LEFT, padx=5)
        
        self.lbl_status = ttk.Label(btn_frame, text="Gata pentru inregistrare", 
                                    foreground="blue")
        self.lbl_status.pack(side=tk.LEFT, padx=20)
        
        ttk.Label(record_frame, text="Apasa ESC sau F9 din orice aplicatie pentru a opri inregistrarea", 
                 foreground="gray").pack(pady=5)
        
        # === SECTIUNE REDARE ===
        play_frame = ttk.LabelFrame(main_frame, text="Redare Task", padding="10")
        play_frame.pack(fill=tk.X, pady=(0, 10))
        
        controls_frame = ttk.Frame(play_frame)
        controls_frame.pack(fill=tk.X)
        
        self.btn_play = ttk.Button(controls_frame, text="Reda", 
                                   command=self.play_task, width=15)
        self.btn_play.pack(side=tk.LEFT, padx=5)
        
        self.btn_pause = ttk.Button(controls_frame, text="Pauza", 
                                    command=self.pause_playback, state=tk.DISABLED, width=15)
        self.btn_pause.pack(side=tk.LEFT, padx=5)
        
        self.btn_stop_play = ttk.Button(controls_frame, text="Stop redare", 
                                       command=self.stop_playback, state=tk.DISABLED, width=15)
        self.btn_stop_play.pack(side=tk.LEFT, padx=5)
        
        self.lbl_play_status = ttk.Label(controls_frame, text="Nu se reda nimic", 
                                        foreground="green")
        self.lbl_play_status.pack(side=tk.LEFT, padx=20)
        
        # Setari redare
        settings_frame = ttk.Frame(play_frame)
        settings_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(settings_frame, text="Viteza redare:").pack(side=tk.LEFT, padx=5)
        self.speed_var = tk.DoubleVar(value=2.0)
        self.speed_scale = ttk.Scale(settings_frame, from_=0.5, to=5.0, 
                                     variable=self.speed_var, orient=tk.HORIZONTAL, length=200)
        self.speed_scale.pack(side=tk.LEFT, padx=5)
        self.lbl_speed = ttk.Label(settings_frame, text="2.0x")
        self.lbl_speed.pack(side=tk.LEFT, padx=5)
        
        self.speed_var.trace('w', self.update_speed_label)
        
        self.loop_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(settings_frame, text="Loop", variable=self.loop_var).pack(side=tk.LEFT, padx=20)
        
        # === SECTIUNE EVENIMENTE ===
        events_frame = ttk.LabelFrame(main_frame, text="Evenimente (optimizate cu context)", padding="10")
        events_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Configurare grid pentru main_frame
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(2, weight=1)  # Evenimente frame sa se extinda
        
        # Treeview
        columns = ('#', 'Timp (s)', 'Tip', 'Detalii')
        self.tree = ttk.Treeview(events_frame, columns=columns, show='headings', height=15)
        
        self.tree.heading('#', text='#')
        self.tree.heading('Timp (s)', text='Timp (s)')
        self.tree.heading('Tip', text='Tip')
        self.tree.heading('Detalii', text='Detalii')
        
        self.tree.column('#', width=50)
        self.tree.column('Timp (s)', width=100)
        self.tree.column('Tip', width=150)
        self.tree.column('Detalii', width=500)
        
        scrollbar = ttk.Scrollbar(events_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # === SECTIUNE FISIERE ===
        file_frame = ttk.LabelFrame(main_frame, text="Fisier Task", padding="10")
        file_frame.pack(fill=tk.X, pady=(0, 0))
        
        # Butoane salvare/incarcare - PRIMA LINIE
        btn_frame = ttk.Frame(file_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 10))
        
        btn_save = ttk.Button(btn_frame, text="Salveaza task", 
                             command=self.save_task, width=22)
        btn_save.pack(side=tk.LEFT, padx=5, pady=8)
        
        btn_load_file = ttk.Button(btn_frame, text="Incarca din fisier...", 
                                  command=self.load_task, width=22)
        btn_load_file.pack(side=tk.LEFT, padx=5, pady=8)
        
        self.lbl_file = ttk.Label(btn_frame, text="Niciun fisier incarcat", foreground="gray")
        self.lbl_file.pack(side=tk.LEFT, padx=20, pady=8)
        
        # Dropdown pentru task-uri salvate - A DOUA LINIE
        list_frame = ttk.Frame(file_frame)
        list_frame.pack(fill=tk.X, pady=(0, 0))
        
        ttk.Label(list_frame, text="Task-uri salvate:").pack(side=tk.LEFT, padx=5, pady=5)
        
        self.task_var = tk.StringVar()
        self.task_combo = ttk.Combobox(list_frame, textvariable=self.task_var, 
                                      width=35, state="readonly")
        self.task_combo.pack(side=tk.LEFT, padx=5, pady=8)
        self.task_combo.bind('<<ComboboxSelected>>', self.on_task_selected)
        
        btn_load_selected = ttk.Button(list_frame, text="Incarca task selectat", 
                                      command=self.load_selected_task, width=22)
        btn_load_selected.pack(side=tk.LEFT, padx=5, pady=8)
        
        # Actualizeaza lista de task-uri
        self.refresh_task_list()
    
    def refresh_task_list(self):
        """Actualizeaza lista de task-uri din folderul tasks"""
        try:
            task_files = sorted([f.stem for f in self.tasks_dir.glob("*.json")])
            self.task_combo['values'] = task_files
            if task_files:
                self.task_combo.set("Selecteaza task...")
            else:
                self.task_combo.set("Niciun task salvat")
        except Exception as e:
            print(f"Eroare la refresh lista: {e}")
    
    def on_task_selected(self, event=None):
        """Callback cand se selecteaza un task din dropdown"""
        pass  # Poate fi folosit pentru preview
    
    def load_selected_task(self):
        """Incarca task-ul selectat din dropdown"""
        selected = self.task_var.get()
        if not selected or selected == "Selecteaza task..." or selected == "Niciun task salvat":
            messagebox.showwarning("Atentie", "Selecteaza un task din lista!")
            return
        
        filepath = self.tasks_dir / f"{selected}.json"
        if not filepath.exists():
            messagebox.showerror("Eroare", f"Fisierul {filepath.name} nu exista!")
            self.refresh_task_list()
            return
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.current_events = data['events']
            self.lbl_file.config(text=filepath.name, foreground="blue")
            
            # Afiseaza in treeview
            self.tree.delete(*self.tree.get_children())
            for i, event in enumerate(self.current_events, 1):
                event_type = event['type']
                if event_type == 'mouse_move':
                    details = f"({event['x']}, {event['y']})"
                elif event_type == 'mouse_click':
                    action = "Press" if event['pressed'] else "Release"
                    button = event['button'].replace('Button.', '')
                    details = f"{action} {button} @ ({event['x']}, {event['y']})"
                elif event_type == 'mouse_scroll':
                    direction = "Sus" if event['dy'] > 0 else "Jos"
                    details = f"Scroll {direction}"
                elif event_type == 'key_press':
                    key_display = event['key']
                    if '+' in key_display:
                        parts = key_display.split('+')
                        formatted = ' + '.join(p.capitalize() for p in parts[:-1]) + ' + ' + parts[-1].upper()
                        details = f"Press {formatted}"
                    else:
                        details = f"Press {key_display}"
                elif event_type == 'key_release':
                    key_display = event['key']
                    if '+' in key_display:
                        parts = key_display.split('+')
                        formatted = ' + '.join(p.capitalize() for p in parts[:-1]) + ' + ' + parts[-1].upper()
                        details = f"Release {formatted}"
                    else:
                        details = f"Release {key_display}"
                else:
                    details = str(event)
                
                self.tree.insert('', tk.END, values=(
                    i,
                    f"{event['timestamp']:.3f}",
                    event_type,
                    details
                ))
            
            messagebox.showinfo("Succes", f"Task incarcat: {selected}\n{len(self.current_events)} evenimente")
        except Exception as e:
            messagebox.showerror("Eroare", f"Eroare la incarcare: {e}")
    
    def update_speed_label(self, *args):
        """Actualizeaza label viteza"""
        speed = self.speed_var.get()
        self.lbl_speed.config(text=f"{speed:.1f}x")
    
    def add_event_to_list(self, event_text):
        """Adauga eveniment in lista"""
        # Foloseste root.after pentru thread-safe update
        if len(self.recorder.events) > 0:
            event = self.recorder.events[-1]
            self.root.after(0, self._insert_event, event, event_text)
    
    def _insert_event(self, event, event_text):
        """Insereaza eveniment in treeview (thread-safe)"""
        # Construieste detalii complete
        event_type = event['type']
        if event_type == 'mouse_move':
            details = f"({event['x']}, {event['y']})"
        elif event_type == 'mouse_click':
            action = "Press" if event['pressed'] else "Release"
            button = event['button'].replace('Button.', '')
            details = f"{action} {button} @ ({event['x']}, {event['y']})"
        elif event_type == 'mouse_scroll':
            direction = "Sus" if event['dy'] > 0 else "Jos"
            details = f"Scroll {direction}"
        elif event_type == 'key_press':
            key_display = event['key']
            # Formateaza combinatii frumos
            if '+' in key_display:
                parts = key_display.split('+')
                formatted = ' + '.join(p.capitalize() for p in parts[:-1]) + ' + ' + parts[-1].upper()
                details = f"Press {formatted}"
            else:
                details = f"Press {key_display}"
        elif event_type == 'key_release':
            key_display = event['key']
            # Formateaza combinatii frumos
            if '+' in key_display:
                parts = key_display.split('+')
                formatted = ' + '.join(p.capitalize() for p in parts[:-1]) + ' + ' + parts[-1].upper()
                details = f"Release {formatted}"
            else:
                details = f"Release {key_display}"
        else:
            details = event_text
        
        self.tree.insert('', tk.END, values=(
            len(self.recorder.events),
            f"{event['timestamp']:.3f}",
            event_type,
            details
        ))
        self.tree.yview_moveto(1)  # Scroll la sfarsit
    
    def start_recording(self):
        """Porneste inregistrarea"""
        self.current_events = []
        self.tree.delete(*self.tree.get_children())
        
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.lbl_status.config(text="IN INREGISTRARE... (ESC/F9 pentru stop)", foreground="red")
        
        # Start in thread separat
        def record_thread():
            self.recorder.start_recording()
            while self.recorder.recording and not self.recorder.stop_requested:
                time.sleep(0.1)
            # Actualizeaza GUI dupa stop
            self.root.after(0, self.stop_recording)
        
        threading.Thread(target=record_thread, daemon=True).start()
    
    def stop_recording(self):
        """Opreste inregistrarea"""
        self.current_events = self.recorder.stop_recording()
        
        # Actualizeaza tabelul cu toate evenimentele
        self.tree.delete(*self.tree.get_children())
        for i, event in enumerate(self.current_events, 1):
            event_type = event['type']
            if event_type == 'mouse_move':
                details = f"({event['x']}, {event['y']})"
            elif event_type == 'mouse_click':
                action = "Press" if event['pressed'] else "Release"
                button = event['button'].replace('Button.', '')
                details = f"{action} {button} @ ({event['x']}, {event['y']})"
            elif event_type == 'mouse_scroll':
                direction = "Sus" if event['dy'] > 0 else "Jos"
                details = f"Scroll {direction}"
            elif event_type == 'key_press':
                key_display = event['key']
                # Formateaza combinatii frumos
                if '+' in key_display:
                    parts = key_display.split('+')
                    formatted = ' + '.join(p.capitalize() for p in parts[:-1]) + ' + ' + parts[-1].upper()
                    details = f"Press {formatted}"
                else:
                    details = f"Press {key_display}"
            elif event_type == 'key_release':
                details = f"Release {event['key']}"
            else:
                details = str(event)
            
            self.tree.insert('', tk.END, values=(
                i,
                f"{event['timestamp']:.3f}",
                event_type,
                details
            ))
        
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.lbl_status.config(text=f"Inregistrare completa: {len(self.current_events)} evenimente", 
                              foreground="green")
    
    def play_task(self):
        """Reda task-ul"""
        if not self.current_events:
            messagebox.showwarning("Atentie", "Nu exista task de redat!")
            return
        
        self.btn_play.config(state=tk.DISABLED)
        self.btn_stop_play.config(state=tk.NORMAL)
        self.lbl_play_status.config(text="Redare in curs...", foreground="orange")
        
        speed = self.speed_var.get()
        loop = 999 if self.loop_var.get() else 1
        
        def play_thread():
            self.player.play_events(self.current_events, speed=speed, loop_count=loop,
                                   callback=lambda msg: self.lbl_play_status.config(text=msg))
            self.btn_play.config(state=tk.NORMAL)
            self.btn_stop_play.config(state=tk.DISABLED)
            self.lbl_play_status.config(text="Redare finalizata", foreground="green")
        
        threading.Thread(target=play_thread, daemon=True).start()
    
    def pause_playback(self):
        """Pauza redare"""
        pass  # TODO
    
    def stop_playback(self):
        """Opreste redarea"""
        self.player.stop()
        self.btn_play.config(state=tk.NORMAL)
        self.btn_stop_play.config(state=tk.DISABLED)
        self.lbl_play_status.config(text="Redare oprita", foreground="red")
    
    def save_task(self):
        """Salveaza task"""
        if not self.current_events:
            messagebox.showwarning("Atentie", "Nu exista task de salvat!")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            initialdir=self.tasks_dir
        )
        
        if filename:
            try:
                filepath = Path(filename)
                data = {
                    'version': '1.0',
                    'created': datetime.now().isoformat(),
                    'event_count': len(self.current_events),
                    'events': self.current_events
                }
                
                # Salveaza JSON
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                
                # Salveaza LOG
                log_path = filepath.with_suffix('.log')
                with open(log_path, 'w', encoding='utf-8') as f:
                    f.write(f"BEBE Task Recorder - Log\n")
                    f.write(f"{'='*60}\n")
                    f.write(f"Task: {filepath.name}\n")
                    f.write(f"Creat: {data['created']}\n")
                    f.write(f"Evenimente: {len(self.current_events)}\n")
                    f.write(f"{'='*60}\n\n")
                    
                    for i, event in enumerate(self.current_events, 1):
                        event_type = event['type']
                        timestamp = event['timestamp']
                        
                        if event_type == 'mouse_move':
                            details = f"Mouse Move -> ({event['x']}, {event['y']})"
                        elif event_type == 'mouse_click':
                            action = "Press" if event['pressed'] else "Release"
                            button = event['button'].replace('Button.', '')
                            details = f"Mouse {action} {button} @ ({event['x']}, {event['y']})"
                        elif event_type == 'mouse_scroll':
                            direction = "Sus" if event['dy'] > 0 else "Jos"
                            details = f"Scroll {direction}"
                        elif event_type == 'key_press':
                            details = f"Key Press: {event['key']}"
                        elif event_type == 'key_release':
                            details = f"Key Release: {event['key']}"
                        else:
                            details = str(event)
                        
                        f.write(f"[{i:4d}] {timestamp:8.3f}s - {details}\n")
                
                self.lbl_file.config(text=filepath.name, foreground="blue")
                # Actualizeaza lista de task-uri
                self.refresh_task_list()
                self.task_var.set(filepath.stem)  # Selecteaza task-ul salvat
                
                messagebox.showinfo("Succes", 
                    f"Task salvat: {len(self.current_events)} evenimente\n"
                    f"JSON: {filepath.name}\n"
                    f"LOG: {log_path.name}")
            except Exception as e:
                messagebox.showerror("Eroare", f"Eroare la salvare: {e}")
    
    def load_task(self):
        """Incarca task"""
        filename = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json")],
            initialdir=self.tasks_dir
        )
        
        if filename:
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                self.current_events = data['events']
                filepath = Path(filename)
                self.lbl_file.config(text=filepath.name, foreground="blue")
                
                # Actualizeaza lista si selecteaza task-ul incarcat
                self.refresh_task_list()
                if filepath.parent == self.tasks_dir:
                    self.task_var.set(filepath.stem)
                
                # Afiseaza in treeview
                self.tree.delete(*self.tree.get_children())
                for i, event in enumerate(self.current_events, 1):
                    event_type = event['type']
                    if event_type == 'mouse_move':
                        details = f"({event['x']}, {event['y']})"
                    elif event_type == 'mouse_click':
                        action = "Press" if event['pressed'] else "Release"
                        details = f"{action} {event['button']} @ ({event['x']}, {event['y']})"
                    elif event_type == 'key_press':
                        key_display = event['key']
                        # Formateaza combinatii frumos (ex: ctrl+a -> Ctrl+A)
                        if '+' in key_display:
                            parts = key_display.split('+')
                            formatted = ' + '.join(p.capitalize() for p in parts[:-1]) + ' + ' + parts[-1].upper()
                            details = f"Press {formatted}"
                        else:
                            details = f"Press {key_display}"
                    elif event_type == 'key_release':
                        details = f"Release {event['key']}"
                    else:
                        details = str(event)
                    
                    self.tree.insert('', tk.END, values=(
                        i,
                        f"{event['timestamp']:.3f}",
                        event_type,
                        details
                    ))
                
                messagebox.showinfo("Succes", f"Task incarcat: {len(self.current_events)} evenimente")
            except Exception as e:
                messagebox.showerror("Eroare", f"Eroare la incarcare: {e}")


def main():
    """Functia principala"""
    root = tk.Tk()
    app = BebeGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()

