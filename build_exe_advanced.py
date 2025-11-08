#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build script pentru BEBE Task Recorder
Creeaza executabil cu privilegii de administrator
"""

import os
import sys
import subprocess
from pathlib import Path

def check_pyinstaller():
    """Verifica daca PyInstaller este instalat"""
    try:
        import PyInstaller
        print("[OK] PyInstaller este instalat")
        return True
    except ImportError:
        print("[INFO] Instalez PyInstaller...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
            print("[OK] PyInstaller instalat cu succes")
            return True
        except subprocess.CalledProcessError:
            print("[EROARE] Nu am putut instala PyInstaller!")
            return False

def build_exe():
    """Construieste executabilul"""
    print("\n" + "="*60)
    print("BEBE Task Recorder - Build Executable")
    print("="*60 + "\n")
    
    if not check_pyinstaller():
        return False
    
    # Creeaza directoare
    Path("build").mkdir(exist_ok=True)
    Path("dist").mkdir(exist_ok=True)
    Path("tasks").mkdir(exist_ok=True)
    
    # Verifica daca exista manifest
    manifest_path = Path("admin_manifest.xml")
    if not manifest_path.exists():
        print("[EROARE] admin_manifest.xml nu exista!")
        return False
    
    print("[INFO] Construiesc executabilul cu privilegii de administrator...")
    print("-" * 60)
    
    # Verifica daca exista .spec file
    spec_path = Path("BEBE_Task_Recorder.spec")
    if spec_path.exists():
        print("[INFO] Folosesc fisierul .spec existent...")
        cmd = [
            "pyinstaller",
            "--clean",
            str(spec_path)
        ]
    else:
        print("[INFO] Creez executabil cu parametri directi...")
        # Comanda PyInstaller cu uac-admin
        cmd = [
            "pyinstaller",
            "--onefile",                    # Un singur fisier executabil
            "--windowed",                   # Fara consola (GUI)
            "--name", "BEBE_Task_Recorder", # Nume executabil
            "--add-data", "tasks;tasks",   # Include folderul tasks
            "--uac-admin",                  # CERE AUTOMAT PRIVILEGII DE ADMINISTRATOR
            "--clean",                      # Curata build-urile vechi
            "bebe_gui.py"
        ]
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=False)
        print("\n" + "="*60)
        print("BUILD COMPLET CU SUCCES!")
        print("="*60)
        print(f"\nExecutabilul se afla in: dist\\BEBE_Task_Recorder.exe")
        print("\nAcest .exe va cere automat privilegii de administrator!")
        print("Cand il pornesti, Windows va afisa UAC prompt.\n")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n[EROARE] Build esuat: {e}")
        return False

if __name__ == "__main__":
    success = build_exe()
    if not success:
        sys.exit(1)

