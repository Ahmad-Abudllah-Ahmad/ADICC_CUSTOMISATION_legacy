"""Guard: the desktop PyInstaller lock must carry every base runtime dep.

The desktop build installs dependencies from ``requirements-desktop.lock`` and
then runs ``pip install -e . --no-deps``, so anything missing from the lock is
simply absent from the frozen sidecar. A stale lock once shipped without PyMuPDF
/ OpenCV / laspy / lazrs / pypdf (PDF takeoff, raster room detection, point-cloud
reads, PDF stamping) and with pandas 3.x even though ``pyproject.toml`` caps it
below 3.0 - silently breaking those features on the desktop channel only, while
the wheel kept working. This test fails fast if the lock drifts away from the
declared base dependencies again.

It is a pure file-parsing test (no application import), so it runs anywhere the
test suite is collected.
"""

import re
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
_LOCK = _BACKEND / "requirements-desktop.lock"

# Base deps whose absence silently breaks a desktop-only feature. Each is an
# unconditional (non-optional, non-platform-gated) dependency declared in
# pyproject.toml that is imported by application code.
_REQUIRED_BASE_DEPS = (
    "pymupdf",
    "opencv-python-headless",
    "laspy",
    "lazrs",
    "pypdf",
    "pandas",
)


def _lock_versions() -> dict[str, str]:
    """Map normalised distribution name -> pinned version from the lock."""
    versions: dict[str, str] = {}
    for line in _LOCK.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Za-z0-9._-]+)==([^\s;]+)", line)
        if match:
            versions[match.group(1).lower()] = match.group(2)
    return versions


def test_required_base_deps_present_in_desktop_lock() -> None:
    versions = _lock_versions()
    missing = [dep for dep in _REQUIRED_BASE_DEPS if dep.lower() not in versions]
    assert not missing, (
        "requirements-desktop.lock is missing base deps imported by the app: "
        f"{missing}. Regenerate with: uv pip compile pyproject.toml --universal "
        "--python-version 3.12 -o requirements-desktop.lock"
    )


def test_pandas_pinned_below_3_in_desktop_lock() -> None:
    versions = _lock_versions()
    pandas_version = versions.get("pandas")
    assert pandas_version is not None, "pandas missing from requirements-desktop.lock"
    major = int(pandas_version.split(".")[0])
    assert major < 3, (
        f"requirements-desktop.lock pins pandas {pandas_version}; pyproject.toml "
        "caps it <3 (pandas 3.0 changed string-column type inference). Regenerate "
        "the lock so it respects the cap."
    )
