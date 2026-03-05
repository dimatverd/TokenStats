"""Persistent Linear comment (workpad) for issue progress tracking."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

# Add tools/ to path for LinearClient import
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from linear_client import LinearClient


class WorkpadManager:
    """Manages a persistent comment on a Linear issue as a workpad."""

    def __init__(self, client: LinearClient, issue_id: str, header: str = "## 🤖 Orchestrator Workpad") -> None:
        self.client = client
        self.issue_id = issue_id
        self.header = header
        self.comment_id: str | None = None
        self._entries: list[str] = []

    def init(self, message: str) -> str:
        """Create the initial workpad comment. Returns comment ID."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        body = f"{self.header}\n\n`{timestamp}` — {message}"
        self._entries.append(f"`{timestamp}` — {message}")
        result = self.client.create_comment(self.issue_id, body)
        self.comment_id = result["id"]
        return self.comment_id

    def update(self, message: str) -> None:
        """Append a timestamped entry to the workpad comment."""
        if not self.comment_id:
            self.init(message)
            return
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._entries.append(f"`{timestamp}` — {message}")
        body = self.header + "\n\n" + "\n".join(self._entries)
        self.client.update_comment(self.comment_id, body)
