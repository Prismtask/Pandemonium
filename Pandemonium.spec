# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Code\\Pandemonium\\pandemonium\\resources\\enemies\\enemies_data', 'pandemonium/resources/enemies/enemies_data'), ('C:\\Code\\Pandemonium\\pandemonium\\resources\\skill_book', 'pandemonium/resources/skill_book'), ('C:\\Code\\Pandemonium\\pandemonium\\gui', 'pandemonium/gui'), ('C:\\Code\\Pandemonium\\pandemonium\\resources\\family_scenes.yaml', 'pandemonium/resources')],
    hiddenimports=['tkinter', 'tkinter.ttk', 'tkinter.font', 'tkinter.messagebox', 'yaml'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Pandemonium',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Pandemonium',
)
