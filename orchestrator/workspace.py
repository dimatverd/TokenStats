"""Per-issue workspace isolation via git clone."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from orchestrator.config import WorkspaceConfig


def slug_from_identifier(identifier: str, title: str) -> str:
    """Generate a branch-safe slug from issue identifier and title.

    Example: slug_from_identifier("TS-42", "OAuth Login Flow") → "ts-42-oauth-login-flow"
    """
    raw = f"{identifier}-{title}"
    slug = raw.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:60]


def create_workspace(config: WorkspaceConfig, identifier: str, title: str) -> tuple[Path, str]:
    """Clone the repo into a fresh workspace dir and create a feature branch.

    Returns (workspace_path, branch_name).
    """
    slug = slug_from_identifier(identifier, title)
    branch_name = slug
    root = Path(config.root).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    workspace_dir = root / slug

    if workspace_dir.exists():
        shutil.rmtree(workspace_dir)

    subprocess.run(
        [
            "git", "clone",
            "--depth=1",
            f"--branch={config.base_branch}",
            config.repo_url,
            str(workspace_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    subprocess.run(
        ["git", "checkout", "-b", branch_name],
        cwd=workspace_dir,
        check=True,
        capture_output=True,
        text=True,
    )

    return workspace_dir, branch_name


def cleanup_workspace(path: Path | str) -> None:
    """Remove a workspace directory."""
    p = Path(path)
    if p.exists():
        shutil.rmtree(p)
