"""‌⁠‍{{display_name}} module.

Generated from oe-module-template. Edit manifest.py to fill in real
metadata, then build out models / schemas / service / router / tests.

The module loader discovers this package automatically when it lives
under ``backend/app/modules/{{module_short}}/``.
"""


async def on_startup() -> None:
    """‌⁠‍Module startup hook — runs once at app boot.

    Use this to register permissions, subscribe to events, or warm
    in-memory caches. Keep it fast; the loader awaits all modules in
    sequence.
    """
    # Example:
    #   from app.modules.{{module_short}}.permissions import register
    #   register()
    return None
