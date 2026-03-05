"""In-memory state machine for orchestrator issue tracking."""

from __future__ import annotations

import enum
import threading
from dataclasses import dataclass, field
from datetime import datetime


class OrchestratorStatus(enum.Enum):
    QUEUED = "queued"
    DISPATCHED = "dispatched"
    RUNNING = "running"
    REVIEWING = "reviewing"
    PR_CREATED = "pr_created"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class IssueState:
    issue_id: str
    identifier: str
    title: str = ""
    status: OrchestratorStatus = OrchestratorStatus.QUEUED
    workspace_path: str = ""
    branch_name: str = ""
    pr_url: str = ""
    agent_pid: int | None = None
    attempt: int = 0
    last_output_at: datetime | None = None
    error: str = ""
    workpad_comment_id: str = ""
    review_result: str = ""
    started_at: datetime | None = None


class StateManager:
    """Thread-safe in-memory state tracker for orchestrated issues."""

    def __init__(self) -> None:
        self._states: dict[str, IssueState] = {}
        self._lock = threading.Lock()

    def track(self, issue_id: str, identifier: str, title: str = "") -> IssueState:
        """Start tracking an issue. Returns existing state if already tracked."""
        with self._lock:
            if issue_id in self._states:
                return self._states[issue_id]
            state = IssueState(issue_id=issue_id, identifier=identifier, title=title)
            self._states[issue_id] = state
            return state

    def transition(self, issue_id: str, new_status: OrchestratorStatus, **kwargs: object) -> IssueState:
        """Transition an issue to a new status, updating any extra fields."""
        with self._lock:
            state = self._states[issue_id]
            state.status = new_status
            for key, value in kwargs.items():
                if hasattr(state, key):
                    setattr(state, key, value)
            return state

    def get(self, issue_id: str) -> IssueState | None:
        with self._lock:
            return self._states.get(issue_id)

    def active_count(self) -> int:
        """Count issues that are currently being processed."""
        active = {OrchestratorStatus.DISPATCHED, OrchestratorStatus.RUNNING, OrchestratorStatus.REVIEWING}
        with self._lock:
            return sum(1 for s in self._states.values() if s.status in active)

    def all_states(self) -> list[IssueState]:
        with self._lock:
            return list(self._states.values())

    def is_tracked(self, issue_id: str) -> bool:
        with self._lock:
            return issue_id in self._states

    def remove(self, issue_id: str) -> None:
        with self._lock:
            self._states.pop(issue_id, None)
