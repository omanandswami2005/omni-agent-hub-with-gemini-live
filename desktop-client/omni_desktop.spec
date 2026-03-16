# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Omni Desktop Client.

Build with:
    uv run pyinstaller omni_desktop.spec
"""

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# Collect every module under src.* automatically (handles dynamic imports and plugins)
src_submodules = collect_submodules("src")

# Resolve the src directory path
src_path = str(Path("src").resolve())

a = Analysis(
    ["entry.py"],
    pathex=[str(Path(".").resolve())],
    binaries=[],
    datas=[
        # Bundle the entire src package so plugin discovery works at runtime
        ("src", "src"),
    ],
    hiddenimports=src_submodules + [
        # PyQt6 modules
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "PyQt6.sip",
        # qasync
        "qasync",
        # Audio / screen capture
        "sounddevice",
        "mss",
        "PIL",
        "PIL.Image",
        # pydantic
        "pydantic",
        "pydantic_settings",
        # websockets
        "websockets",
        "websockets.legacy",
        "websockets.legacy.client",
        # typer / rich
        "typer",
        "rich",
        "rich.console",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "pytest_asyncio",
        "pytest_mock",
        "_pytest",
    ],
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
    name="OmniDesktop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # No console window — GUI app (set True to debug)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,              # Set to "icon.ico" if you add an icon file
    # Produce a single-file executable
    onefile=True,
)
