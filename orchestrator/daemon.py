"""Core polling daemon — fetches Linear issues, dispatches agents, manages lifecycle."""

from __future__ import annotations

import asyncio
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

# Add tools/ to path for LinearClient import
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from linear_client import LinearClient, load_state
from models import STORY_DEPENDENCIES

from orchestrator.agent_runner import AgentResult, run_agent
from orchestrator.config import OrchestratorConfig
from orchestrator.prompt import IssueContext, WorkspaceContext, render_prompt
from orchestrator.reviewer import (
    ReviewVerdict,
    cto_evaluate,
    format_review_for_workpad,
    get_pr_diff,
    run_codex_review,
)
from orchestrator.state import OrchestratorStatus, StateManager
from orchestrator.workspace import cleanup_workspace, create_workspace
from orchestrator.workpad import WorkpadManager

logger = logging.getLogger("orchestrator.daemon")

# Regex to extract story identifier from Linear issue identifier (e.g., "TS-42" → look up title for "US-xx")
US_RE = re.compile(r"US-\d+")


class Daemon:
    """Main orchestrator daemon that polls Linear and dispatches agents."""

    def __init__(self, config: OrchestratorConfig) -> None:
        self.config = config
        self.state = StateManager()
        self.client = LinearClient()
        self._shutdown = asyncio.Event()
        self._tasks: set[asyncio.Task] = set()
        self._linear_state: dict = {}
        self._team_id: str = ""
        self._states_map: dict[str, str] = {}  # state_name → state_id

    async def start(self) -> None:
        """Start the polling loop."""
        logger.info("Daemon starting...")
        self._linear_state = await asyncio.to_thread(load_state)
        self._team_id = self._linear_state.get("team_id", "")
        self._states_map = self._linear_state.get("states_map", {})

        if not self._team_id:
            logger.error("No team_id in .linear_state.json. Run linear_sync.py first.")
            return

        logger.info(f"Polling team {self.config.linear.team_key} (id: {self._team_id}) "
                     f"every {self.config.linear.poll_interval_seconds}s")

        while not self._shutdown.is_set():
            try:
                await self._poll_cycle()
            except Exception:
                logger.exception("Error in poll cycle")

            try:
                await asyncio.wait_for(
                    self._shutdown.wait(),
                    timeout=self.config.linear.poll_interval_seconds,
                )
                break  # shutdown was set
            except asyncio.TimeoutError:
                pass  # normal: timeout means we should poll again

        # Wait for active tasks to finish
        if self._tasks:
            logger.info(f"Waiting for {len(self._tasks)} active tasks to complete...")
            await asyncio.gather(*self._tasks, return_exceptions=True)

        logger.info("Daemon stopped.")

    def stop(self) -> None:
        """Signal the daemon to stop gracefully."""
        logger.info("Shutdown requested.")
        self._shutdown.set()

    async def _poll_cycle(self) -> None:
        """Single poll cycle: fetch issues, filter, dispatch."""
        issues = await asyncio.to_thread(self.client.get_issues, self._team_id)

        # Build US-xx → state_name map by extracting US-xx from issue titles
        us_states: dict[str, str] = {}
        for issue in issues:
            us_match = US_RE.search(issue.get("title", ""))
            if us_match:
                us_states[us_match.group(0)] = issue["state"]["name"]

        # Filter for Todo issues
        todo_issues = [i for i in issues if i["state"]["name"] == "Todo"]

        for issue in todo_issues:
            issue_id = issue["id"]

            if self.state.is_tracked(issue_id):
                continue

            if self.state.active_count() >= self.config.agent.max_concurrent:
                break

            if not self._deps_satisfied(issue, us_states):
                logger.debug(f"Skipping {issue['identifier']}: dependencies not met")
                continue

            logger.info(f"Dispatching {issue['identifier']}: {issue['title']}")
            self.state.track(issue_id, issue["identifier"], issue["title"])
            task = asyncio.create_task(self._handle_issue(issue))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    def _deps_satisfied(self, issue: dict, us_states: dict[str, str]) -> bool:
        """Check if all STORY_DEPENDENCIES for this issue's US-xx are Done."""
        title = issue.get("title", "")
        us_match = US_RE.search(title)
        if not us_match:
            return True  # No US-xx in title → no dependencies

        us_id = us_match.group(0)
        deps = STORY_DEPENDENCIES.get(us_id, [])
        if not deps:
            return True

        for dep_us_id in deps:
            dep_state = us_states.get(dep_us_id)
            if dep_state != "Done":
                logger.debug(f"{us_id} blocked by {dep_us_id} (state: {dep_state or 'not found'})")
                return False

        return True

    async def _handle_issue(self, issue: dict) -> None:
        """Handle a single issue: workspace → prompt → agent → review → PR."""
        issue_id = issue["id"]
        identifier = issue["identifier"]
        title = issue["title"]
        description = issue.get("description", "") or ""

        try:
            # Move to In Progress
            self.state.transition(issue_id, OrchestratorStatus.DISPATCHED, started_at=datetime.now())
            in_progress_id = self._states_map.get("In Progress")
            if in_progress_id:
                await asyncio.to_thread(self.client.update_issue, issue_id, stateId=in_progress_id)

            # Create workspace
            workspace_path, branch_name = await asyncio.to_thread(
                create_workspace, self.config.workspace, identifier, title
            )
            self.state.transition(
                issue_id, OrchestratorStatus.RUNNING,
                workspace_path=str(workspace_path), branch_name=branch_name,
            )

            # Create workpad
            workpad = WorkpadManager(self.client, issue_id, self.config.workpad.header)
            await asyncio.to_thread(workpad.init, f"Starting work on {identifier}")
            self.state.transition(issue_id, OrchestratorStatus.RUNNING,
                                  workpad_comment_id=workpad.comment_id)

            # Render prompt
            issue_ctx = IssueContext(
                identifier=identifier,
                title=title,
                description=description,
            )
            workspace_ctx = WorkspaceContext(path=str(workspace_path), branch=branch_name)
            prompt = render_prompt(self.config, issue_ctx, workspace_ctx)

            # Agent run with retry
            result = await self._run_with_retry(issue_id, prompt, workspace_path, workpad)

            if result and result.success and result.pr_url:
                # Code review with Codex
                if self.config.review.enabled:
                    try:
                        self.state.transition(issue_id, OrchestratorStatus.REVIEWING)
                        await asyncio.to_thread(workpad.update, "Running Codex code review...")

                        diff = await asyncio.to_thread(get_pr_diff, workspace_path, self.config.workspace.base_branch)
                        codex_review = await asyncio.to_thread(
                            run_codex_review, diff, self.config.review, title
                        )
                        cto_verdict, cto_reason = cto_evaluate(codex_review, self.config.review)

                        review_text = format_review_for_workpad(codex_review, cto_verdict, cto_reason)
                        await asyncio.to_thread(workpad.update, review_text)

                        self.state.transition(issue_id, OrchestratorStatus.RUNNING,
                                              review_result=cto_verdict.value)

                        if cto_verdict == ReviewVerdict.REQUEST_CHANGES:
                            await asyncio.to_thread(workpad.update, f"Review requested changes: {cto_reason}")
                            logger.warning(f"{identifier}: Codex requested changes — {cto_reason}")

                        elif cto_verdict == ReviewVerdict.NEEDS_HUMAN_REVIEW:
                            await asyncio.to_thread(workpad.update, f"Escalated to human review: {cto_reason}")
                            logger.info(f"{identifier}: Escalated to human review")

                    except Exception:
                        logger.exception(f"{identifier}: Codex review failed, proceeding without review")
                        await asyncio.to_thread(workpad.update, "Codex review failed — skipping")

                # PR created → In Review
                self.state.transition(issue_id, OrchestratorStatus.PR_CREATED, pr_url=result.pr_url)
                in_review_id = self._states_map.get("In Review")
                if in_review_id:
                    await asyncio.to_thread(self.client.update_issue, issue_id, stateId=in_review_id)
                await asyncio.to_thread(workpad.update, f"PR created: {result.pr_url}")
                logger.info(f"{identifier}: PR created → {result.pr_url}")

            else:
                # All retries failed
                self.state.transition(
                    issue_id, OrchestratorStatus.FAILED,
                    error=result.error if result else "No result",
                )
                blocked_id = self._states_map.get("Blocked")
                if blocked_id:
                    await asyncio.to_thread(self.client.update_issue, issue_id, stateId=blocked_id)
                await asyncio.to_thread(
                    workpad.update,
                    f"All retries failed. Error: {result.error if result else 'unknown'}",
                )
                logger.error(f"{identifier}: Failed after all retries")

        except Exception as exc:
            logger.exception(f"{identifier}: Unhandled error")
            self.state.transition(issue_id, OrchestratorStatus.FAILED, error=str(exc))
            blocked_id = self._states_map.get("Blocked")
            if blocked_id:
                try:
                    await asyncio.to_thread(self.client.update_issue, issue_id, stateId=blocked_id)
                except Exception:
                    logger.exception(f"{identifier}: Failed to update Linear state")

    async def _run_with_retry(
        self,
        issue_id: str,
        prompt: str,
        workspace_path: Path,
        workpad: WorkpadManager,
    ) -> AgentResult | None:
        """Run the agent with exponential backoff retry."""
        result = None
        for attempt in range(1, self.config.retry.max_attempts + 1):
            self.state.transition(issue_id, OrchestratorStatus.RUNNING, attempt=attempt)
            await asyncio.to_thread(workpad.update, f"Attempt {attempt}/{self.config.retry.max_attempts}")

            def on_output(event: dict) -> None:
                self.state.transition(issue_id, OrchestratorStatus.RUNNING, last_output_at=datetime.now())

            result = await run_agent(prompt, workspace_path, self.config.agent, on_output)

            if result.success:
                return result

            logger.warning(
                f"Attempt {attempt} failed for {self.state.get(issue_id).identifier}: {result.error[:200]}"
            )
            await asyncio.to_thread(workpad.update, f"Attempt {attempt} failed: {result.error[:200]}")

            if attempt < self.config.retry.max_attempts:
                delay = min(
                    self.config.retry.base_delay_seconds * (2 ** (attempt - 1)),
                    self.config.retry.max_delay_seconds,
                )
                logger.info(f"Retrying in {delay}s...")
                await asyncio.sleep(delay)

        return result
