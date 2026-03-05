"""Jinja2 prompt renderer for agent instructions."""

from __future__ import annotations

from dataclasses import dataclass, field

from jinja2 import Environment

from orchestrator.config import OrchestratorConfig


@dataclass
class IssueContext:
    identifier: str
    title: str
    description: str = ""
    acceptance_criteria: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)


@dataclass
class WorkspaceContext:
    path: str
    branch: str


_env = Environment(autoescape=False)


def render_prompt(
    config: OrchestratorConfig,
    issue: IssueContext,
    workspace: WorkspaceContext,
) -> str:
    """Render the WORKFLOW.md template with issue and workspace context."""
    template = _env.from_string(config.template)
    return template.render(
        issue=issue,
        workspace=workspace,
        config=config,
    )
