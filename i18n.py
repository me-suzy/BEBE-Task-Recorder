#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Internationalization (i18n) support for BEBE Task Recorder
Sistem de traduceri pentru interfață
"""

# Dicționar de strings pentru traduceri
STRINGS = {
    'ro': {
        # Window title
        'window_title': "BEBE - Task Recorder",
        
        # Admin messages
        'admin_title': "Privilegii Administrator",
        'admin_message': "Aplicatia trebuie sa ruleze ca Administrator pentru a inregistra taste.\n\nDoresti sa repornesti ca Administrator?",
        'admin_warning_title': "Atentie",
        'admin_warning_message': "Fara privilegii de administrator, nu vei putea inregistra taste din alte aplicatii!",
        
        # Recording section
        'record_section': "Inregistrare Task",
        'start_recording': "Porneste inregistrarea",
        'stop_recording': "Opreste inregistrarea",
        'ready_for_recording': "Gata pentru inregistrare",
        'recording_instruction': "Apasa ESC sau F9 din orice aplicatie pentru a opri inregistrarea",
        'recording_status': "IN INREGISTRARE... (ESC/F9 pentru stop)",
        'recording_complete': "Inregistrare completa: {len} evenimente",
        
        # Playback section
        'play_section': "Redare Task",
        'play': "Reda",
        'pause': "Pauza",
        'stop_playback': "Stop redare",
        'nothing_playing': "Nu se reda nimic",
        'playback_speed': "Viteza redare:",
        'playback_in_progress': "Redare in curs...",
        'playback_completed': "Redare finalizata",
        'playback_stopped': "Redare oprita",
        'loop': "Loop",
        'run_until_stop': "Ruleaza continuu pana la ESC/F9",
        'schedule_settings': "Setari programare",
        
        # Events section
        'events_section': "Evenimente (optimizate cu context)",
        'col_number': "#",
        'col_time': "Timp (s)",
        'col_type': "Tip",
        'col_details': "Detalii",
        
        # File section
        'file_section': "Fisier Task",
        'save_task': "Salveaza task",
        'save_task_as_exe': "Salveaza task ca EXE",
        'load_from_file': "Incarca din fisier...",
        'no_file_loaded': "Niciun fisier incarcat",
        'saved_tasks': "Task-uri salvate:",
        'load_selected_task': "Incarca task selectat",
        'select_task': "Selecteaza task...",
        'no_tasks_saved': "Niciun task salvat",
        
        # Messages
        'no_task_to_play': "Nu exista task de redat!",
        'no_task_to_save': "Nu exista task de salvat!",
        'select_task_from_list': "Selecteaza un task din lista!",
        'file_not_found': "Fisierul {filename} nu exista!",
        'success': "Succes",
        'task_loaded': "Task incarcat: {name}\n{len} evenimente",
        'error': "Eroare",
        'error_loading': "Eroare la incarcare: {error}",
        'task_saved': "Task salvat: {len} evenimente\nJSON: {json_name}\nLOG: {log_name}",
        'task_exe_saved': "Executabil creat: {exe_name}\nLOG: {log_name}",
        'error_saving': "Eroare la salvare: {error}",
        'error_exe_build': "Eroare la generarea executabilului: {error}",
        'error_pyinstaller': "PyInstaller nu este instalat! Instaleaza-l cu 'pip install pyinstaller'",
        'error_exe_unavailable': "Functia 'Save Task as EXE' este disponibila DOAR cand aplicatia ruleaza din surse Python.\n\nPentru a folosi aceasta functie:\n1. Deschide Command Prompt ca Administrator\n2. Ruleaza: python bebe_gui.py\n3. Apoi poti salva task-uri ca EXE\n\nExecutabilul BEBE curent poate salva doar task-uri JSON.",
        'building_exe': "Se genereaza executabilul... Aceasta poate dura cateva minute.",
        
        # Error types
        'error_json_parse': "Eroare la parsarea JSON: {error}",
        'error_permission': "Eroare de permisiuni: Nu ai drepturi de scriere in acest folder!",
        'error_file_io': "Eroare I/O: Nu s-a putut citi/scrie fisierul!",
        'error_invalid_format': "Format invalid: Fisierul nu contine date valide!",
        
        # Scheduling
        'schedule_title': "Setari Programare",
        'schedule_enable': "Activeaza programare",
        'schedule_days': "Zile:",
        'schedule_time_interval': "Interval Orar (Optional)",
        'schedule_enable_time_interval': "Activeaza interval orar",
        'schedule_time_from': "De la ora:",
        'schedule_time_to': "Pana la ora:",
        'schedule_time_info': "💡 Interval peste miezul noptii: Ex: 21:00 - 03:00 (9 PM - 3 AM)",
        'schedule_days_monday': "Luni",
        'schedule_days_tuesday': "Marti",
        'schedule_days_wednesday': "Miercuri",
        'schedule_days_thursday': "Joi",
        'schedule_days_friday': "Vineri",
        'schedule_days_saturday': "Sambata",
        'schedule_days_sunday': "Duminica",
        'schedule_save': "Salveaza",
        'schedule_cancel': "Anuleaza",
        'schedule_invalid_time': "Ora de inceput trebuie sa fie inainte de ora de sfarsit!",
        'schedule_invalid_time_format': "Format timp invalid! Foloseste HH:MM (ex: 09:00 sau 21:00)",
        'schedule_no_days': "Selecteaza cel putin o zi!",
        
        # Progress
        'progress_playing': "Redare: {current}/{total} ({percent}%)",
    },
    'en': {
        # Window title
        'window_title': "BEBE - Task Recorder",
        
        # Admin messages
        'admin_title': "Administrator Privileges",
        'admin_message': "The application must run as Administrator to record keystrokes.\n\nDo you want to restart as Administrator?",
        'admin_warning_title': "Attention",
        'admin_warning_message': "Without administrator privileges, you will not be able to record keystrokes from other applications!",
        
        # Recording section
        'record_section': "Record Task",
        'start_recording': "Start Recording",
        'stop_recording': "Stop Recording",
        'ready_for_recording': "Ready for Recording",
        'recording_instruction': "Press ESC or F9 from any application to stop recording",
        'recording_status': "RECORDING... (ESC/F9 to stop)",
        'recording_complete': "Recording Complete: {len} events",
        
        # Playback section
        'play_section': "Play Task",
        'play': "Play",
        'pause': "Pause",
        'stop_playback': "Stop Playback",
        'nothing_playing': "Nothing is Playing",
        'playback_speed': "Playback Speed:",
        'playback_in_progress': "Playback in Progress...",
        'playback_completed': "Playback Completed",
        'playback_stopped': "Playback Stopped",
        'loop': "Loop",
        'run_until_stop': "Run continuously until ESC/F9",
        'schedule_settings': "Schedule Settings",
        
        # Events section
        'events_section': "Events (Optimized with Context)",
        'col_number': "#",
        'col_time': "Time (s)",
        'col_type': "Type",
        'col_details': "Details",
        
        # File section
        'file_section': "Task File",
        'save_task': "Save Task",
        'save_task_as_exe': "Save Task as EXE",
        'load_from_file': "Load from File...",
        'no_file_loaded': "No File Loaded",
        'saved_tasks': "Saved Tasks:",
        'load_selected_task': "Load Selected Task",
        'select_task': "Select Task...",
        'no_tasks_saved': "No Tasks Saved",
        
        # Messages
        'no_task_to_play': "No task to play!",
        'no_task_to_save': "No task to save!",
        'select_task_from_list': "Select a task from the list!",
        'file_not_found': "The file {filename} does not exist!",
        'success': "Success",
        'task_loaded': "Task Loaded: {name}\n{len} events",
        'error': "Error",
        'error_loading': "Error Loading: {error}",
        'task_saved': "Task Saved: {len} events\nJSON: {json_name}\nLOG: {log_name}",
        'task_exe_saved': "Executable created: {exe_name}\nLOG: {log_name}",
        'error_saving': "Error Saving: {error}",
        'error_exe_build': "Error creating executable: {error}",
        'error_pyinstaller': "PyInstaller is not installed! Install it with 'pip install pyinstaller'",
        'error_exe_unavailable': "The 'Save Task as EXE' feature is ONLY available when running from Python sources.\n\nTo use this feature:\n1. Open Command Prompt as Administrator\n2. Run: python bebe_gui.py\n3. Then you can save tasks as EXE\n\nThe current BEBE executable can only save tasks as JSON.",
        'building_exe': "Generating executable... This may take a few minutes.",
        
        # Error types
        'error_json_parse': "JSON Parse Error: {error}",
        'error_permission': "Permission Error: You do not have write permissions in this folder!",
        'error_file_io': "I/O Error: Could not read/write file!",
        'error_invalid_format': "Invalid Format: File does not contain valid data!",
        
        # Scheduling
        'schedule_title': "Schedule Settings",
        'schedule_enable': "Enable Schedule",
        'schedule_days': "Days:",
        'schedule_time_interval': "Time Interval (Optional)",
        'schedule_enable_time_interval': "Enable time interval",
        'schedule_time_from': "From time:",
        'schedule_time_to': "To time:",
        'schedule_time_info': "💡 Overnight interval: Ex: 21:00 - 03:00 (9 PM - 3 AM)",
        'schedule_days_monday': "Monday",
        'schedule_days_tuesday': "Tuesday",
        'schedule_days_wednesday': "Wednesday",
        'schedule_days_thursday': "Thursday",
        'schedule_days_friday': "Friday",
        'schedule_days_saturday': "Saturday",
        'schedule_days_sunday': "Sunday",
        'schedule_save': "Save",
        'schedule_cancel': "Cancel",
        'schedule_invalid_time': "Start time must be before end time!",
        'schedule_invalid_time_format': "Invalid time format! Use HH:MM (ex: 09:00 or 21:00)",
        'schedule_no_days': "Select at least one day!",
        
        # Progress
        'progress_playing': "Playing: {current}/{total} ({percent}%)",
    }
}


class I18n:
    """Manager pentru traduceri"""
    
    def __init__(self, language='ro'):
        """
        Initializează managerul de traduceri
        
        Args:
            language: Codul limbii ('ro' sau 'en')
        """
        self.language = language
        self.strings = STRINGS.get(language, STRINGS['ro'])
    
    def get(self, key, **kwargs):
        """
        Obține string tradus
        
        Args:
            key: Cheia string-ului
            **kwargs: Parametri pentru formatare (ex: {len}, {name})
        
        Returns:
            String tradus și formatat
        """
        string = self.strings.get(key, key)
        try:
            return string.format(**kwargs)
        except KeyError:
            # Dacă lipsesc parametri, returnează string-ul fără formatare
            return string
    
    def set_language(self, language):
        """Schimbă limba"""
        if language in STRINGS:
            self.language = language
            self.strings = STRINGS[language]
            return True
        return False


# Instanță globală - setată la engleză pentru utilizare globală
_i18n = I18n('en')


def get_string(key, **kwargs):
    """Funcție helper pentru a obține string tradus"""
    return _i18n.get(key, **kwargs)


def set_language(language):
    """Funcție helper pentru a schimba limba"""
    return _i18n.set_language(language)


def get_current_language():
    """Returnează limba curentă"""
    return _i18n.language

