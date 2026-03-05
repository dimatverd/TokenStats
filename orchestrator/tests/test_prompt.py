"""Tests for prompt rendering."""

import textwrap
from pathlib import Path

import pytest

from orchestrator.config import load_config
from orchestrator.prompt import IssueContext, WorkspaceContext, render_prompt


@pytest.fixture
def config(tmp_path: Path):
    content = textwrap.dedent("""\
    ---
    linear:
      team_key: "TS"
    ---

    Task: {{ issue.identifier }} — {{ issue.title }}
    Description: {{ issue.description }}
    Branch: {{ workspace.branch }}
    Path: {{ workspace.path }}
    {% if issue.acceptance_criteria %}AC:{% for ac in issue.acceptance_criteria %}
    - {{ ac }}{% endfor %}{% endif %}
    """)
    p = tmp_path / "WORKFLOW.md"
    p.write_text(content)
    return load_config(p)


def test_render_basic(config) -> None:
    issue = IssueContext(
        identifier="TS-42",
        title="Add OAuth login",
        description="Implement OAuth2 flow",
    )
    workspace = WorkspaceContext(path="/tmp/ws/ts-42", branch="ts-42-add-oauth-login")
    result = render_prompt(config, issue, workspace)

    assert "TS-42" in result
    assert "Add OAuth login" in result
    assert "Implement OAuth2 flow" in result
    assert "ts-42-add-oauth-login" in result
    assert "/tmp/ws/ts-42" in result


def test_render_with_acceptance_criteria(config) -> None:
    issue = IssueContext(
        identifier="TS-10",
        title="Test",
        description="Desc",
        acceptance_criteria=["Criteria 1", "Criteria 2"],
    )
    workspace = WorkspaceContext(path="/tmp/ws", branch="ts-10-test")
    result = render_prompt(config, issue, workspace)

    assert "AC:" in result
    assert "Criteria 1" in result
    assert "Criteria 2" in result


def test_render_without_acceptance_criteria(config) -> None:
    issue = IssueContext(identifier="TS-10", title="Test", description="Desc")
    workspace = WorkspaceContext(path="/tmp/ws", branch="ts-10-test")
    result = render_prompt(config, issue, workspace)

    assert "AC:" not in result
