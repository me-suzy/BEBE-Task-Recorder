# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['bebe_gui.py', 'i18n.py'],
    pathex=[],
    binaries=[],
    datas=[('tasks', 'tasks')],
    hiddenimports=[
        'i18n',
        'PyInstaller',
        'PyInstaller.__main__',
        'PyInstaller.building',
        'PyInstaller.building.build_main',
        'PyInstaller.compat',
        'PyInstaller.hooks',
        'PyInstaller.utils',
        'PyInstaller.utils.hooks',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='BEBE_Task_Recorder',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    upx_dir='upx-5.0.2-win64',  # Calea catre UPX
    runtime_tmpdir=None,
    console=False,  # Fara consola (GUI)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    manifest='admin_manifest.xml',  # MANIFEST DE ADMINISTRATOR
    uac_admin=True,  # CERE AUTOMAT PRIVILEGII DE ADMINISTRATOR
)

