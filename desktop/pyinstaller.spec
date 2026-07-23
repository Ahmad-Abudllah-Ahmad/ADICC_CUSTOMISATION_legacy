# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the OpenConstructionERP backend sidecar.

Builds the FastAPI backend into a single executable that Tauri
launches as a sidecar process.

Usage:
    cd desktop
    pyinstaller pyinstaller.spec
"""

import sys
from pathlib import Path

block_cipher = None

# Paths
ROOT = Path(SPECPATH).parent
BACKEND = ROOT / "backend"
FRONTEND_DIST = ROOT / "frontend" / "dist"
DATA_CATALOG = ROOT / "data" / "catalog"

# Collect all backend module packages for hidden imports
modules_dir = BACKEND / "app" / "modules"
hidden_imports = [
    # Embedded PostgreSQL 16 + its drivers. SQLAlchemy picks the driver from
    # the URL at runtime (create_engine), so PyInstaller's static import graph
    # never sees asyncpg / psycopg2 and would otherwise omit them, leaving the
    # frozen sidecar unable to connect to its own database. pixeltable_pgserver
    # boots the cluster; its bundled PG binaries are collected by the
    # hook-pixeltable_pgserver.py hook on hookspath below.
    "asyncpg",
    "psycopg2",
    "pixeltable_pgserver",
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "app.cli",
    "app.cli_static",
    "app.main",
    "app.config",
    "app.database",
    "app.core",
    "app.core.module_loader",
    "app.core.i18n",
    "app.core.i18n_router",
    "app.core.permissions",
    "app.core.validation",
    "app.core.validation.engine",
    "app.core.validation.rules",
    "app.core.vector",
    "app.core.hooks",
    "app.core.events",
    "app.core.demo_projects",
    "app.core.marketplace",
    # Heavy feature deps imported lazily / dynamically inside service methods,
    # so PyInstaller's static import graph never sees them and would omit the
    # modules from the frozen sidecar - silently breaking the feature on the
    # DESKTOP build only (the wheel works because pip installs them). PyMuPDF
    # exposes both the legacy "fitz" and the modern "pymupdf" import names and
    # the code uses both. lazrs is the LAZ/COPC decompression backend that
    # laspy imports dynamically, so it must be named explicitly or point-cloud
    # LAZ reads fail at runtime. The cv2 / fitz / pymupdf binary payloads are
    # collected by their pyinstaller-hooks-contrib hooks once the module is in
    # the graph.
    "fitz",  # PyMuPDF - PDF vector takeoff, raster render, text extract
    "pymupdf",  # PyMuPDF modern import alias
    "cv2",  # opencv-python-headless - raster room/wall detector
    "laspy",  # LAS/LAZ/COPC point-cloud reader
    "lazrs",  # laspy's LAZ/COPC decompression backend (dynamic import)
    "pypdf",  # PDF stamping / merge (pdf_stamp, property_dev exports)
]

# Auto-discover modules
if modules_dir.is_dir():
    for mod_dir in sorted(modules_dir.iterdir()):
        if mod_dir.is_dir() and (mod_dir / "__init__.py").exists():
            mod_name = mod_dir.name
            hidden_imports.extend([
                f"app.modules.{mod_name}",
                f"app.modules.{mod_name}.models",
                f"app.modules.{mod_name}.schemas",
                f"app.modules.{mod_name}.router",
                f"app.modules.{mod_name}.service",
                f"app.modules.{mod_name}.repository",
                f"app.modules.{mod_name}.manifest",
            ])

# Data files to include
datas = []

# Frontend dist
if FRONTEND_DIST.is_dir():
    datas.append((str(FRONTEND_DIST), "app/_frontend_dist"))

# Translation files, validation rules, etc. from backend
datas.append((str(BACKEND / "app"), "app"))

# Ship pyproject.toml next to the bundled app package. _detect_version()
# reads the version from the source tree first and only falls back to the
# installed-wheel metadata if it cannot find a pyproject. In a frozen build
# there is no source tree, so without this the sidecar would report whatever
# openconstructionerp version happens to be pip-installed on the build
# machine instead of the real product version. Landing it at the bundle root
# (one level above app/) is exactly where _read_pyproject_version walks to.
_pyproject = BACKEND / "pyproject.toml"
if _pyproject.is_file():
    datas.append((str(_pyproject), "."))

a = Analysis(
    [str(BACKEND / "app" / "cli.py")],
    pathex=[str(BACKEND)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    # Local hooks dir holds hook-pixeltable_pgserver.py, which collects the
    # ~40 MB pginstall/ tree (postgres, initdb, pg_ctl + runtime libs) the
    # embedded cluster needs. Without it the sidecar starts then dies with
    # "postgres executable not found".
    hookspath=[str(Path(SPECPATH) / "hooks")],
    hooksconfig={},
    runtime_hooks=[],
    # numpy / pandas / openpyxl / pyarrow are base runtime deps (cost-DB
    # Excel/CSV/Parquet import), so they must NOT be excluded. Only the
    # genuinely-unused heavy science / GUI stacks are dropped to slim the build.
    # The Qt bindings are excluded because the sidecar is a headless HTTP
    # server with no GUI; they are never imported at runtime. The exclusion
    # also avoids PyInstaller's hard abort when a build machine happens to have
    # more than one Qt binding installed (it refuses to bundle both PyQt and
    # PySide), which would otherwise break the build on developer machines that
    # carry a full scientific Python stack.
    excludes=[
        "tkinter",
        "matplotlib",
        "scipy",
        "torch",
        "tensorflow",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
    ],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, cipher=block_cipher)

# Build a SINGLE self-contained executable (onefile), not a onedir folder.
# Tauri ships the sidecar as an externalBin, which must be one standalone file;
# a onedir build (exe + a separate _internal/ folder) cannot be used that way,
# because Tauri copies only the named binary and the sidecar would then fail to
# find its bundled Python runtime and PostgreSQL binaries. Folding a.binaries /
# a.datas / a.zipfiles into EXE produces the single file.
#
# UPX is deliberately off. Compressing the embedded PostgreSQL executables and
# their DLLs risks corrupting them, and UPX-packed binaries frequently trip
# antivirus heuristics, which is the last thing a downloadable installer needs.
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="openconstructionerp-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,  # Keep console for server logging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
