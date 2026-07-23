"""‌⁠‍{{display_name}} module manifest.

Edit the placeholders below. The ``make module-new`` target drops
this package into ``backend/app/modules/{{module_short}}/`` (note:
short name, no ``oe_`` prefix — matches the existing core modules).
"""

from app.core.module_loader import ModuleManifest

manifest = ModuleManifest(
    name="{{module_name}}",
    version="0.1.0",
    display_name="{{display_name}}",
    description="TODO: one-sentence description of what this module does.",
    author="{{author}}",
    category="community",  # one of: core, integration, regional, community
    depends=[],            # e.g. ["oe_projects", "oe_boq"]
    optional_depends=[],   # soft dependencies — present-if-installed
    auto_install=False,    # set True to enable on first boot
    enabled=True,
)
