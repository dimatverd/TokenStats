"""Tests for daemon dispatch logic."""

import textwrap
from pathlib import Path

import pytest

from orchestrator.config import load_config
from orchestrator.daemon import Daemon
from orchestrator.state import OrchestratorStatus


@pytest.fixture
def config(tmp_path: Path):
    content = textwrap.dedent("""\
    ---
    linear:
      poll_interval_seconds: 5
      team_key: "TS"
    agent:
      max_concurrent: 2
    review:
      enabled: false
    ---

    Template {{ issue.identifier }}
    """)
    p = tmp_path / "WORKFLOW.md"
    p.write_text(content)
    return load_config(p)


def test_daemon_init(config) -> None:
    daemon = Daemon(config)
    assert daemon.state.active_count() == 0
    assert daemon.config.linear.team_key == "TS"


def test_deps_satisfied_no_deps(config) -> None:
    daemon = Daemon(config)
    issue = {"identifier": "TS-1", "title": "No US reference"}
    assert daemon._deps_satisfied(issue, {})


def test_deps_satisfied_no_us_in_title(config) -> None:
    daemon = Daemon(config)
    issue = {"identifier": "TS-36", "title": "[QA] Unit-тесты провайдеров"}
    assert daemon._deps_satisfied(issue, {})


def test_deps_satisfied_all_done(config) -> None:
    daemon = Daemon(config)
    issue = {"identifier": "TS-5", "title": "[US-02] Some task"}
    us_states = {"US-01": "Done"}
    assert daemon._deps_satisfied(issue, us_states)


def test_deps_blocked_not_done(config) -> None:
    daemon = Daemon(config)
    issue = {"identifier": "TS-5", "title": "[US-02] Some task"}
    us_states = {"US-01": "In Progress"}
    assert not daemon._deps_satisfied(issue, us_states)


def test_deps_blocked_missing(config) -> None:
    daemon = Daemon(config)
    issue = {"identifier": "TS-5", "title": "[US-02] Some task"}
    us_states = {}  # US-01 not found at all
    assert not daemon._deps_satisfied(issue, us_states)


def test_deps_multi_dependency(config) -> None:
    daemon = Daemon(config)
    # US-07 depends on US-04, US-05, US-06
    issue = {"identifier": "TS-10", "title": "[US-07] Aggregation"}
    us_states = {"US-04": "Done", "US-05": "Done", "US-06": "Done"}
    assert daemon._deps_satisfied(issue, us_states)

    us_states["US-05"] = "In Progress"
    assert not daemon._deps_satisfied(issue, us_states)


def test_max_concurrent_respected(config) -> None:
    daemon = Daemon(config)
    daemon.state.track("id-1", "TS-1")
    daemon.state.transition("id-1", OrchestratorStatus.RUNNING)
    daemon.state.track("id-2", "TS-2")
    daemon.state.transition("id-2", OrchestratorStatus.RUNNING)

    assert daemon.state.active_count() == 2
    assert daemon.state.active_count() >= config.agent.max_concurrent


def test_already_tracked_skipped(config) -> None:
    daemon = Daemon(config)
    daemon.state.track("id-1", "TS-1")
    assert daemon.state.is_tracked("id-1")
