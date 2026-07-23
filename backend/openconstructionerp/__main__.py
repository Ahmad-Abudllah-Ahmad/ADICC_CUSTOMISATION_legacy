"""``python -m openconstructionerp`` entry point.

Delegates to the same ``main`` the ``openconstructionerp`` console script uses,
so this module form is a drop-in, PATH-independent way to launch the app.
"""

from __future__ import annotations

from openconstructionerp import main

if __name__ == "__main__":
    main()
