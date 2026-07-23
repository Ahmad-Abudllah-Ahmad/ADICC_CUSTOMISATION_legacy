# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""DB-free tests for the off-site production stage machine.

These exercise the pure ordering rules in ``app.modules.prefab.guard`` with no
database, session or fixtures - they prove the one guarantee the module exists
for: a unit can never be dispatched, delivered or installed until it has passed
QA, and stages only ever advance forward.

Coverage
--------
* the seven canonical stages advance one step at a time, cleanly
* backward and no-op advances are rejected
* the QA gate blocks every pre-QA -> post-QA jump, and allows post-QA moves
* ``next_stage`` walks the chain and stops at the terminal stage
* ``allowed_targets`` from a pre-QA stage never leaks a post-QA stage
"""

from __future__ import annotations

import pytest

from app.modules.prefab.guard import (
    POST_QA_STAGES,
    STAGE_ORDER,
    PrefabStage,
    PrefabStageMachine,
    has_passed_qa,
    is_known_stage,
    next_stage,
    stage_index,
)

MACHINE = PrefabStageMachine()

# The seven stages in order, spelled out so the test pins the exact contract
# rather than re-deriving it from the code under test.
EXPECTED_ORDER = (
    "design",
    "approved_for_production",
    "in_production",
    "qa",
    "dispatched",
    "delivered",
    "installed",
)

POST_QA = ("dispatched", "delivered", "installed")
PRE_QA = ("design", "approved_for_production", "in_production")


def test_stage_order_matches_contract() -> None:
    assert STAGE_ORDER == EXPECTED_ORDER
    assert set(POST_QA) == POST_QA_STAGES


def test_single_step_advance_walks_the_whole_chain() -> None:
    for src, dst in zip(EXPECTED_ORDER, EXPECTED_ORDER[1:], strict=False):
        ok, reason = MACHINE.can_advance(src, dst)
        assert ok, f"{src} -> {dst} should be allowed, got: {reason}"


def test_no_op_advance_is_rejected() -> None:
    ok, reason = MACHINE.can_advance("qa", "qa")
    assert not ok
    assert "already" in reason.lower()


@pytest.mark.parametrize(
    ("src", "dst"),
    [
        ("qa", "in_production"),
        ("installed", "delivered"),
        ("dispatched", "qa"),
        ("delivered", "design"),
    ],
)
def test_backward_advance_is_rejected(src: str, dst: str) -> None:
    ok, reason = MACHINE.can_advance(src, dst)
    assert not ok
    assert "backward" in reason.lower()


@pytest.mark.parametrize("dst", POST_QA)
@pytest.mark.parametrize("src", PRE_QA)
def test_qa_gate_blocks_every_pre_qa_to_post_qa_jump(src: str, dst: str) -> None:
    """The core guarantee: nothing ships or installs before it clears QA."""
    ok, reason = MACHINE.can_advance(src, dst)
    assert not ok, f"{src} -> {dst} must be blocked by the QA gate"
    assert "qa" in reason.lower()


@pytest.mark.parametrize("dst", POST_QA)
def test_qa_gate_opens_once_the_unit_has_reached_qa(dst: str) -> None:
    ok, reason = MACHINE.can_advance("qa", dst)
    assert ok, f"qa -> {dst} should pass once QA is reached, got: {reason}"


def test_post_qa_stages_can_move_among_themselves() -> None:
    assert MACHINE.can_advance("dispatched", "delivered")[0]
    assert MACHINE.can_advance("dispatched", "installed")[0]
    assert MACHINE.can_advance("delivered", "installed")[0]


def test_design_cannot_jump_straight_to_installed() -> None:
    ok, reason = MACHINE.can_advance("design", "installed")
    assert not ok
    assert "qa" in reason.lower()


@pytest.mark.parametrize(
    ("src", "dst"),
    [("nonsense", "qa"), ("qa", "shipped"), ("", "qa"), ("qa", "")],
)
def test_unknown_stage_is_rejected_cleanly(src: str, dst: str) -> None:
    ok, reason = MACHINE.can_advance(src, dst)
    assert not ok
    assert "unknown" in reason.lower()


def test_case_insensitive() -> None:
    assert MACHINE.can_advance("DESIGN", "Approved_For_Production")[0]


def test_next_stage_walks_and_terminates() -> None:
    assert next_stage("design") == "approved_for_production"
    assert next_stage("qa") == "dispatched"
    assert next_stage("installed") is None
    assert next_stage("nonsense") is None


def test_has_passed_qa() -> None:
    assert not has_passed_qa("design")
    assert not has_passed_qa("in_production")
    assert has_passed_qa("qa")
    assert has_passed_qa("dispatched")
    assert has_passed_qa("installed")


def test_stage_index_and_known() -> None:
    assert stage_index("design") == 0
    assert stage_index(PrefabStage.INSTALLED.value) == len(EXPECTED_ORDER) - 1
    assert stage_index("nope") == -1
    assert is_known_stage("qa")
    assert not is_known_stage("nope")


def test_allowed_targets_from_pre_qa_excludes_post_qa() -> None:
    # From in_production the only reachable next step is qa; no post-QA stage
    # should be reachable because the gate is closed until QA is passed.
    targets = MACHINE.allowed_targets("in_production")
    assert "qa" in targets
    assert not (set(targets) & set(POST_QA)), targets


def test_allowed_targets_from_qa_includes_post_qa() -> None:
    targets = set(MACHINE.allowed_targets("qa"))
    assert {"dispatched", "delivered", "installed"} <= targets


def test_installed_is_terminal() -> None:
    assert MACHINE.allowed_targets("installed") == []
