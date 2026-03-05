"""Tests for orchestrator config parsing."""

import textwrap
from pathlib import Path

import pytest

from orchestrator.config import OrchestratorConfig, load_config


@pytest.fixture
def workflow_file(tmp_path: Path) -> Path:
    content = textwrap.dedent("""\
    ---
    linear:
      poll_interval_seconds: 60
      team_key: "TEST"
    agent:
      model: "opus"
      max_budget_usd: 10.0
      max_concurrent: 3
      stall_timeout_minutes: 15
    workspace:
      root: "/tmp/test-workspaces"
      repo_url: "https://github.com/test/repo.git"
      base_branch: "develop"
    retry:
      max_attempts: 5
      base_delay_seconds: 10
      max_delay_seconds: 120
    review:
      enabled: true
      model: "o3"
      auto_approve_threshold: 0.9
    ---

    Hello {{ issue.identifier }}, this is a template.
    """)
    p = tmp_path / "WORKFLOW.md"
    p.write_text(content)
    return p


@pytest.fixture
def minimal_workflow(tmp_path: Path) -> Path:
    content = textwrap.dedent("""\
    ---
    linear:
      team_key: "TS"
    ---

    Simple template.
    """)
    p = tmp_path / "WORKFLOW.md"
    p.write_text(content)
    return p


def test_load_config_full(workflow_file: Path) -> None:
    config = load_config(workflow_file)
    assert config.linear.poll_interval_seconds == 60
    assert config.linear.team_key == "TEST"
    assert config.agent.model == "opus"
    assert config.agent.max_budget_usd == 10.0
    assert config.agent.max_concurrent == 3
    assert config.agent.stall_timeout_minutes == 15
    assert config.workspace.root == "/tmp/test-workspaces"
    assert config.workspace.repo_url == "https://github.com/test/repo.git"
    assert config.workspace.base_branch == "develop"
    assert config.retry.max_attempts == 5
    assert config.retry.base_delay_seconds == 10
    assert config.retry.max_delay_seconds == 120
    assert config.review.enabled is True
    assert config.review.model == "o3"
    assert config.review.auto_approve_threshold == 0.9
    assert "{{ issue.identifier }}" in config.template


def test_load_config_defaults(minimal_workflow: Path) -> None:
    config = load_config(minimal_workflow)
    assert config.linear.poll_interval_seconds == 30
    assert config.linear.team_key == "TS"
    assert config.agent.model == "sonnet"
    assert config.agent.max_budget_usd == 5.0
    assert config.agent.max_concurrent == 1
    assert config.workspace.base_branch == "main"
    assert config.retry.max_attempts == 3
    assert config.review.enabled is True
    assert config.template == "Simple template."


def test_load_config_no_front_matter(tmp_path: Path) -> None:
    p = tmp_path / "BAD.md"
    p.write_text("No front matter here.")
    with pytest.raises(ValueError, match="No YAML front matter"):
        load_config(p)


def test_config_is_frozen(minimal_workflow: Path) -> None:
    config = load_config(minimal_workflow)
    with pytest.raises(AttributeError):
        config.linear = None
