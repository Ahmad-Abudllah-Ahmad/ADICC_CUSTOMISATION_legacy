"""‌⁠‍{{display_name}} smoke test.

Move this file into ``backend/tests/unit/`` (rename if it collides)
once the scaffold lands in ``backend/app/modules/{{module_short}}/``.
The default test only exercises the Pydantic schemas, so no DB is
required — perfect for a brand-new module skeleton.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError


def test_manifest_is_well_formed() -> None:
    """‌⁠‍Manifest imports, has a sane name, and declares a version."""
    from app.modules.{{module_short}} import manifest as manifest_mod

    m = manifest_mod.manifest
    assert m.name == "{{module_name}}"
    assert m.version
    assert m.display_name


def test_item_create_requires_name() -> None:
    from app.modules.{{module_short}}.schemas import ItemCreate

    with pytest.raises(ValidationError):
        ItemCreate(project_id=uuid4())  # type: ignore[call-arg]


def test_item_create_accepts_valid_payload() -> None:
    from app.modules.{{module_short}}.schemas import ItemCreate

    payload = ItemCreate(name="Demo", project_id=uuid4())
    assert payload.name == "Demo"
    assert payload.description == ""
