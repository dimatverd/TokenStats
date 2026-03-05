"""Typed configuration parsed from WORKFLOW.md YAML front matter."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class LinearConfig:
    poll_interval_seconds: int = 30
    team_key: str = "TS"


@dataclass(frozen=True)
class AgentConfig:
    model: str = "sonnet"
    max_budget_usd: float = 5.0
    max_concurrent: int = 1
    stall_timeout_minutes: int = 10
    allowed_tools: list[str] = field(default_factory=lambda: [
        "Bash(git:*)",
        "Bash(python:*)",
        "Bash(pip:*)",
        "Bash(pytest:*)",
        "Bash(ruff:*)",
        "Bash(gh:*)",
        "Read",
        "Write",
        "Edit",
        "Glob",
        "Grep",
    ])


@dataclass(frozen=True)
class WorkspaceConfig:
    root: str = "~/.tokenstats-workspaces"
    repo_url: str = "https://github.com/dimatverd/TokenStats.git"
    base_branch: str = "main"
    cleanup_after_merge: bool = True


@dataclass(frozen=True)
class RetryConfig:
    max_attempts: int = 3
    base_delay_seconds: int = 30
    max_delay_seconds: int = 300


@dataclass(frozen=True)
class WorkpadConfig:
    header: str = "## 🤖 Orchestrator Workpad"


@dataclass(frozen=True)
class ReviewConfig:
    """Configuration for Codex code review integration."""
    enabled: bool = True
    model: str = "o3"
    max_tokens: int = 4096
    auto_approve_threshold: float = 0.8
    require_human_review_labels: list[str] = field(default_factory=lambda: [
        "security",
        "architecture",
        "breaking-change",
    ])


@dataclass(frozen=True)
class OrchestratorConfig:
    linear: LinearConfig = field(default_factory=LinearConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    workspace: WorkspaceConfig = field(default_factory=WorkspaceConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    workpad: WorkpadConfig = field(default_factory=WorkpadConfig)
    review: ReviewConfig = field(default_factory=ReviewConfig)
    template: str = ""


_FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def _build_config(raw: dict) -> OrchestratorConfig:
    """Build OrchestratorConfig from raw YAML dict."""
    linear = LinearConfig(**raw.get("linear", {}))
    agent_raw = raw.get("agent", {})
    if "allowed_tools" in agent_raw and isinstance(agent_raw["allowed_tools"], list):
        agent = AgentConfig(**agent_raw)
    else:
        agent = AgentConfig(**{k: v for k, v in agent_raw.items() if k != "allowed_tools"})
    workspace = WorkspaceConfig(**raw.get("workspace", {}))
    retry = RetryConfig(**raw.get("retry", {}))
    workpad = WorkpadConfig(**raw.get("workpad", {}))
    review = ReviewConfig(**raw.get("review", {}))
    return OrchestratorConfig(
        linear=linear,
        agent=agent,
        workspace=workspace,
        retry=retry,
        workpad=workpad,
        review=review,
    )


def load_config(workflow_path: Path | str) -> OrchestratorConfig:
    """Parse WORKFLOW.md and return typed config + template string."""
    text = Path(workflow_path).read_text()
    match = _FRONT_MATTER_RE.match(text)
    if not match:
        raise ValueError(f"No YAML front matter found in {workflow_path}")
    yaml_str, template_str = match.group(1), match.group(2)
    raw = yaml.safe_load(yaml_str) or {}
    config = _build_config(raw)
    # Inject template via object.__setattr__ since frozen
    object.__setattr__(config, "template", template_str.strip())
    return config
