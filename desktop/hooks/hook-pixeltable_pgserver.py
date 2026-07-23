# PyInstaller hook for pixeltable-pgserver.
#
# The desktop sidecar runs the whole app on an embedded PostgreSQL 16 cluster
# booted from this package's bundled binaries. The binaries live in a
# ``pginstall/`` directory next to the Python module (``bin/`` holds
# postgres, initdb, pg_ctl, ...; ``lib/`` and ``share/`` hold the runtime
# support files). PyInstaller does not see these because they are plain data
# next to the package rather than imported modules, so without this hook the
# frozen sidecar starts, tries to spawn postgres, and dies with "postgres
# executable not found". Collecting the full pginstall tree fixes that.
#
# The subtlety is the executable bit. PyInstaller only marks entries collected
# as ``binaries`` executable on extraction; ``datas`` come out non-executable.
# On Windows that does not matter (the OS ignores the bit), but on Linux and
# macOS the extracted postgres / initdb / pg_ctl must be runnable or the
# cluster never starts. So the hook is platform-aware.

import os
import sys

from PyInstaller.utils.hooks import collect_data_files

_all = collect_data_files("pixeltable_pgserver", include_py_files=False)

if sys.platform == "win32":
    # Windows ignores the executable bit, so plain data collection preserves the
    # pginstall tree without dragging the PG executables through PE import
    # analysis (which can duplicate or misplace their runtime DLLs).
    datas = _all
    binaries = []
else:
    # On Linux and macOS the extracted postgres / initdb / pg_ctl must be
    # runnable. PyInstaller sets the executable bit only on ``binaries``, so
    # route the bin/ executables and the .so / .dylib shared libraries through
    # binaries and keep the rest (share/, timezone data, ...) as data. The dest
    # dirs from collect_data_files preserve the pginstall/... layout pg_ctl
    # expects, for both lists.
    binaries = []
    datas = []
    for src, dest in _all:
        norm = dest.replace("\\", "/")
        base = os.path.basename(src)
        is_executable = (
            norm.endswith("/bin")
            or src.endswith((".so", ".dylib"))
            or ".so." in base  # versioned shared objects, e.g. libssl.so.3
        )
        (binaries if is_executable else datas).append((src, dest))

hiddenimports = ["pixeltable_pgserver"]
