"""CLI entry point for the orchestrator daemon."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from orchestrator.config import load_config
from orchestrator.daemon import Daemon
from orchestrator.status import live_dashboard, print_status

PID_FILE = Path("/tmp/tokenstats-orchestrator.pid")
DEFAULT_WORKFLOW = Path(__file__).parent.parent / "WORKFLOW.md"


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_run(args: argparse.Namespace) -> None:
    """Start the orchestrator daemon."""
    _setup_logging(args.verbose)
    logger = logging.getLogger("orchestrator")

    workflow_path = Path(args.workflow).resolve()
    if not workflow_path.exists():
        logger.error(f"WORKFLOW.md not found: {workflow_path}")
        sys.exit(1)

    config = load_config(workflow_path)
    daemon = Daemon(config)

    # Write PID file
    PID_FILE.write_text(str(os.getpid()))

    loop = asyncio.new_event_loop()

    def _shutdown_handler(sig: int, frame: object) -> None:
        logger.info(f"Received signal {sig}, shutting down...")
        daemon.stop()

    signal.signal(signal.SIGINT, _shutdown_handler)
    signal.signal(signal.SIGTERM, _shutdown_handler)

    try:
        loop.run_until_complete(daemon.start())
    finally:
        PID_FILE.unlink(missing_ok=True)
        loop.close()


def cmd_status(args: argparse.Namespace) -> None:
    """Show current daemon status."""
    if not PID_FILE.exists():
        print("Daemon is not running.")
        sys.exit(1)

    pid = int(PID_FILE.read_text().strip())
    try:
        os.kill(pid, 0)  # Check if process exists
        print(f"Daemon is running (PID: {pid})")
    except OSError:
        print(f"Daemon PID file exists but process {pid} is not running.")
        PID_FILE.unlink(missing_ok=True)
        sys.exit(1)


def cmd_stop(args: argparse.Namespace) -> None:
    """Stop the daemon gracefully."""
    if not PID_FILE.exists():
        print("Daemon is not running (no PID file).")
        sys.exit(1)

    pid = int(PID_FILE.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"Sent SIGTERM to daemon (PID: {pid})")
    except OSError as e:
        print(f"Failed to stop daemon: {e}")
        PID_FILE.unlink(missing_ok=True)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="orchestrator",
        description="TokenStats orchestrator daemon — automated Linear→Claude Code pipeline",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--workflow", default=str(DEFAULT_WORKFLOW),
        help="Path to WORKFLOW.md (default: project root)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Start the orchestrator daemon")
    run_parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    subparsers.add_parser("status", help="Show daemon status")
    subparsers.add_parser("stop", help="Stop the daemon gracefully")

    args = parser.parse_args()

    commands = {
        "run": cmd_run,
        "status": cmd_status,
        "stop": cmd_stop,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
