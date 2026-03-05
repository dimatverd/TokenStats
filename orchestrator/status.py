"""Terminal dashboard for orchestrator status."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime

from orchestrator.state import IssueState, OrchestratorStatus, StateManager

# ANSI colors
RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"
DIM = "\033[2m"

STATUS_COLORS = {
    OrchestratorStatus.QUEUED: DIM,
    OrchestratorStatus.DISPATCHED: CYAN,
    OrchestratorStatus.RUNNING: YELLOW,
    OrchestratorStatus.REVIEWING: MAGENTA,
    OrchestratorStatus.PR_CREATED: GREEN,
    OrchestratorStatus.FAILED: RED,
    OrchestratorStatus.BLOCKED: RED,
}


def _duration(state: IssueState) -> str:
    if not state.started_at:
        return "-"
    delta = datetime.now() - state.started_at
    minutes = int(delta.total_seconds() // 60)
    seconds = int(delta.total_seconds() % 60)
    return f"{minutes}m{seconds:02d}s"


def _last_output(state: IssueState) -> str:
    if not state.last_output_at:
        return "-"
    delta = datetime.now() - state.last_output_at
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s ago"
    return f"{secs // 60}m ago"


def render_table(state_manager: StateManager) -> str:
    """Render a status table as a string."""
    states = state_manager.all_states()
    if not states:
        return f"{DIM}No issues tracked.{RESET}"

    lines = [
        f"{BOLD}{'Issue':<12} {'Status':<14} {'Att':>3} {'Duration':>10} {'Last Output':>12} {'PR/Error'}{RESET}",
        "─" * 80,
    ]

    for s in sorted(states, key=lambda x: x.identifier):
        color = STATUS_COLORS.get(s.status, RESET)
        status_str = s.status.value
        pr_or_error = s.pr_url or s.error[:40] if s.error else ""
        lines.append(
            f"{color}{s.identifier:<12} {status_str:<14} {s.attempt:>3} "
            f"{_duration(s):>10} {_last_output(s):>12} {pr_or_error}{RESET}"
        )

    lines.append("")
    active = state_manager.active_count()
    lines.append(f"{DIM}Active: {active} | Total: {len(states)}{RESET}")
    return "\n".join(lines)


def print_status(state_manager: StateManager) -> None:
    """Print the status table to stdout."""
    print(render_table(state_manager))


async def live_dashboard(state_manager: StateManager, refresh_interval: float = 2.0) -> None:
    """Continuously refresh the status dashboard."""
    try:
        while True:
            os.system("clear" if os.name != "nt" else "cls")
            print(f"{BOLD}TokenStats Orchestrator{RESET}")
            print(f"{DIM}{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{RESET}")
            print()
            print_status(state_manager)
            await asyncio.sleep(refresh_interval)
    except asyncio.CancelledError:
        pass
