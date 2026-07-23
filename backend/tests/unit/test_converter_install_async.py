"""Unit tests for the non-blocking converter install + Linux .deb resolution.

Covers the v8.8.0 fix for the user-reported "signal timed out" on a slow
Ubuntu Server: the install endpoint must return immediately (the heavy
download runs in the background and is observed via /install-progress/), the
offline ``.deb`` fallback must build URLs that match the live apt repo, and a
terminal progress record must auto-expire.

These import ``app.modules.takeoff.router`` which pulls the app/database, so
they run on the CI py3.12 image (the local py3.11 dev env can't import them).
"""

from __future__ import annotations

import types

import pytest

from app.modules.takeoff import router as tk


def test_fallback_deb_plan_ifc_matches_published_versions() -> None:
    """The offline fallback must build the exact pool paths the repo serves.

    Regression: the pinned versions drifted (18.4.1.0) behind the published
    18.4.3.0, so an apt-index hiccup built 404 URLs. Keep them in step.
    """
    plan = tk._fallback_deb_plan("ifc", "amd64")
    pkgs = [p for p, _ in plan]
    assert pkgs == ["ddc-ifcconverter", "ddc-deps-kernel", "ddc-deps-ifc", "ddc-thirdparty"]
    rels = dict(plan)
    assert rels["ddc-ifcconverter"] == "pool/main/d/ddc-ifcconverter/ddc-ifcconverter_18.4.3.0_amd64.deb"
    assert rels["ddc-deps-kernel"] == "pool/main/d/ddc-deps-kernel/ddc-deps-kernel_27.2_amd64.deb"
    assert rels["ddc-deps-ifc"] == "pool/main/d/ddc-deps-ifc/ddc-deps-ifc_27.2_amd64.deb"
    assert rels["ddc-thirdparty"] == "pool/main/d/ddc-thirdparty/ddc-thirdparty_18.4.3.0_amd64.deb"


def test_fallback_deb_plan_unknown_converter_raises() -> None:
    with pytest.raises(RuntimeError):
        tk._fallback_deb_plan("nope", "amd64")


def test_parse_apt_packages_and_resolve_deps() -> None:
    """The live-index path: parse a Packages stanza set + resolve ddc-* deps."""
    sample = (
        "Package: ddc-ifcconverter\n"
        "Version: 18.4.3.0\n"
        "Depends: ddc-deps-kernel (>= 27.2), ddc-deps-ifc (>= 27.2), ddc-thirdparty (>= 18.4.3.0)\n"
        "Filename: pool/main/d/ddc-ifcconverter/ddc-ifcconverter_18.4.3.0_amd64.deb\n"
        "\n"
        "Package: ddc-deps-kernel\n"
        "Version: 27.2\n"
        "Depends: libc6 (>= 2.31)\n"
        "Filename: pool/main/d/ddc-deps-kernel/ddc-deps-kernel_27.2_amd64.deb\n"
        "\n"
        "Package: ddc-deps-ifc\n"
        "Version: 27.2\n"
        "Depends: ddc-deps-kernel (>= 27.2)\n"
        "Filename: pool/main/d/ddc-deps-ifc/ddc-deps-ifc_27.2_amd64.deb\n"
        "\n"
        "Package: ddc-thirdparty\n"
        "Version: 18.4.3.0\n"
        "Filename: pool/main/d/ddc-thirdparty/ddc-thirdparty_18.4.3.0_amd64.deb\n"
    )
    index = tk._parse_apt_packages(sample)
    assert set(index) == {"ddc-ifcconverter", "ddc-deps-kernel", "ddc-deps-ifc", "ddc-thirdparty"}
    order = tk._resolve_deb_deps("ddc-ifcconverter", index)
    # root first, deps transitively after; no system deps (libc6) included.
    assert order[0] == "ddc-ifcconverter"
    assert set(order) == {"ddc-ifcconverter", "ddc-deps-kernel", "ddc-deps-ifc", "ddc-thirdparty"}
    assert "libc6" not in order


@pytest.mark.asyncio
async def test_install_converter_returns_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    """The install endpoint must NOT block on the download (the root cause of
    the client-side "signal timed out"). It returns ``async_install`` at once
    and the heavy work runs in a background task."""
    import asyncio

    from app.modules.boq import cad_import

    cid = "ifc"
    tk._INSTALL_TASKS.pop(cid, None)
    tk._clear_install_progress(cid)

    monkeypatch.setattr(cad_import, "find_converter", lambda _ext: None)

    ran = asyncio.Event()

    async def _fake_impl(converter_id: str, force: bool, app: object) -> dict[str, object]:
        ran.set()
        return {"converter_id": converter_id, "installed": True, "path": "/usr/bin/IfcExporter"}

    monkeypatch.setattr(tk, "_install_converter_impl", _fake_impl)

    fake_request = types.SimpleNamespace(app=types.SimpleNamespace(state=types.SimpleNamespace()))
    result = await tk.install_converter(cid, fake_request, "user-1", force=False)

    assert result["async_install"] is True
    assert result["started"] is True
    assert result["installed"] is False

    # The background task eventually runs the (mocked) heavy work to completion.
    await asyncio.wait_for(ran.wait(), timeout=2.0)
    # Let the background wrapper publish its terminal record.
    for _ in range(50):
        prog = await tk.get_install_progress(cid)
        if prog.get("stage") == "done":
            break
        await asyncio.sleep(0.01)
    prog = await tk.get_install_progress(cid)
    assert prog["active"] is True
    assert prog["stage"] == "done"
    assert prog["installed"] is True
    tk._clear_install_progress(cid)
    tk._INSTALL_TASKS.pop(cid, None)


@pytest.mark.asyncio
async def test_install_progress_terminal_record_expires() -> None:
    """A done/error record lingers briefly for the poll, then auto-expires."""
    import time

    cid = "ifc"
    tk._set_install_progress(
        cid,
        stage="done",
        installed=True,
        finished_at=time.time() - (tk._INSTALL_RESULT_TTL_SEC + 10.0),
    )
    prog = await tk.get_install_progress(cid)
    assert prog == {"active": False}
