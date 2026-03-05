"""Claude Code agent launcher and monitor."""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from orchestrator.config import AgentConfig

PR_URL_RE = re.compile(r"https://github\.com/[^\s]+/pull/\d+")


@dataclass
class AgentResult:
    success: bool
    pr_url: str = ""
    output: str = ""
    error: str = ""


async def run_agent(
    prompt: str,
    workspace_path: Path | str,
    agent_config: AgentConfig,
    on_output: callable | None = None,
) -> AgentResult:
    """Launch claude -p in the workspace and monitor output.

    Uses --output-format stream-json for structured monitoring.
    Implements stall detection: kills process if no output for stall_timeout_minutes.
    """
    cmd = [
        "claude", "-p",
        "--model", agent_config.model,
        "--max-budget-usd", str(agent_config.max_budget_usd),
        "--dangerously-skip-permissions",
        "--verbose",
        "--output-format", "stream-json",
    ]

    for tool in agent_config.allowed_tools:
        cmd.extend(["--allowedTools", tool])

    # Clean env: remove CLAUDE_CODE vars to avoid nested session detection
    clean_env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}

    # Pass prompt via stdin (too long for command line arg)
    process = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(workspace_path),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=clean_env,
    )

    # Write prompt to stdin and close it
    process.stdin.write(prompt.encode("utf-8"))
    await process.stdin.drain()
    process.stdin.close()
    await process.stdin.wait_closed()

    output_lines: list[str] = []
    pr_url = ""
    last_output_time = datetime.now()
    stall_timeout = agent_config.stall_timeout_minutes * 60

    async def _watchdog() -> None:
        """Kill the process if stalled."""
        nonlocal last_output_time
        while process.returncode is None:
            await asyncio.sleep(30)
            elapsed = (datetime.now() - last_output_time).total_seconds()
            if elapsed > stall_timeout:
                process.kill()
                return

    watchdog_task = asyncio.create_task(_watchdog())

    try:
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace").strip()
            if not decoded:
                continue

            last_output_time = datetime.now()
            output_lines.append(decoded)

            # Try to extract PR URL from any output
            url_match = PR_URL_RE.search(decoded)
            if url_match:
                pr_url = url_match.group(0)

            # Try to parse as JSON for structured output
            try:
                event = json.loads(decoded)
                if on_output:
                    on_output(event)
            except json.JSONDecodeError:
                if on_output:
                    on_output({"type": "text", "content": decoded})

        await process.wait()
    finally:
        watchdog_task.cancel()
        try:
            await watchdog_task
        except asyncio.CancelledError:
            pass

    stderr_bytes = await process.stderr.read()
    stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""

    full_output = "\n".join(output_lines)

    # Final PR URL search in full output
    if not pr_url:
        url_match = PR_URL_RE.search(full_output)
        if url_match:
            pr_url = url_match.group(0)

    if process.returncode == 0:
        return AgentResult(success=True, pr_url=pr_url, output=full_output)
    else:
        return AgentResult(
            success=False,
            pr_url=pr_url,
            output=full_output,
            error=stderr or f"Process exited with code {process.returncode}",
        )
