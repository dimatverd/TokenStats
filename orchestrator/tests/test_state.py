"""Tests for state machine."""

from orchestrator.state import IssueState, OrchestratorStatus, StateManager


def test_track_new_issue() -> None:
    sm = StateManager()
    state = sm.track("id-1", "TS-1", "Title")
    assert state.issue_id == "id-1"
    assert state.identifier == "TS-1"
    assert state.status == OrchestratorStatus.QUEUED


def test_track_dedup() -> None:
    sm = StateManager()
    s1 = sm.track("id-1", "TS-1")
    s2 = sm.track("id-1", "TS-1")
    assert s1 is s2


def test_transition() -> None:
    sm = StateManager()
    sm.track("id-1", "TS-1")
    state = sm.transition("id-1", OrchestratorStatus.RUNNING, attempt=2)
    assert state.status == OrchestratorStatus.RUNNING
    assert state.attempt == 2


def test_active_count() -> None:
    sm = StateManager()
    sm.track("id-1", "TS-1")
    sm.track("id-2", "TS-2")
    sm.track("id-3", "TS-3")

    sm.transition("id-1", OrchestratorStatus.RUNNING)
    sm.transition("id-2", OrchestratorStatus.DISPATCHED)
    # id-3 stays QUEUED

    assert sm.active_count() == 2


def test_active_count_includes_reviewing() -> None:
    sm = StateManager()
    sm.track("id-1", "TS-1")
    sm.transition("id-1", OrchestratorStatus.REVIEWING)
    assert sm.active_count() == 1


def test_get() -> None:
    sm = StateManager()
    assert sm.get("nonexistent") is None
    sm.track("id-1", "TS-1")
    assert sm.get("id-1") is not None


def test_all_states() -> None:
    sm = StateManager()
    sm.track("id-1", "TS-1")
    sm.track("id-2", "TS-2")
    assert len(sm.all_states()) == 2


def test_is_tracked() -> None:
    sm = StateManager()
    assert not sm.is_tracked("id-1")
    sm.track("id-1", "TS-1")
    assert sm.is_tracked("id-1")


def test_remove() -> None:
    sm = StateManager()
    sm.track("id-1", "TS-1")
    sm.remove("id-1")
    assert not sm.is_tracked("id-1")
    assert sm.active_count() == 0


def test_transition_with_kwargs() -> None:
    sm = StateManager()
    sm.track("id-1", "TS-1")
    state = sm.transition(
        "id-1", OrchestratorStatus.PR_CREATED,
        pr_url="https://github.com/test/pull/1",
        branch_name="ts-1-feature",
    )
    assert state.pr_url == "https://github.com/test/pull/1"
    assert state.branch_name == "ts-1-feature"
