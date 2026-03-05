"""Codex code review integration.

Uses Codex CLI (codex exec) to perform code review on PRs.
Runs on ChatGPT Plus subscription tokens — no separate API billing.
The orchestrator (Claude as CTO) evaluates Codex findings and makes decisions.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from orchestrator.config import ReviewConfig

# Codex CLI binary — check common install locations
_CODEX_PATHS = [
    "codex",
    "/tmp/node-v22.14.0-darwin-arm64/bin/codex",
]


def _find_codex() -> str:
    """Find codex binary on PATH or known locations."""
    for p in _CODEX_PATHS:
        if shutil.which(p):
            return p
        if Path(p).exists():
            return p
    raise FileNotFoundError("codex CLI not found. Install: npm install -g @openai/codex")


class ReviewVerdict(Enum):
    APPROVE = "approve"
    REQUEST_CHANGES = "request_changes"
    NEEDS_HUMAN_REVIEW = "needs_human_review"


@dataclass
class ReviewFinding:
    severity: str  # "critical", "major", "minor", "suggestion"
    category: str  # "security", "bug", "performance", "style", "architecture"
    file: str
    line: int | None
    description: str
    suggestion: str = ""


@dataclass
class CodexReviewResult:
    verdict: ReviewVerdict
    summary: str
    findings: list[ReviewFinding] = field(default_factory=list)
    raw_response: str = ""
    confidence: float = 0.0


REVIEW_PROMPT = """\
You are a senior code reviewer. Review the provided git diff carefully.

Analyze for:
1. **Bugs**: Logic errors, off-by-one, null/None handling, race conditions
2. **Security**: Injection, auth bypass, secret exposure, unsafe deserialization
3. **Performance**: N+1 queries, unnecessary allocations, missing indexes
4. **Architecture**: SOLID violations, tight coupling, missing error handling
5. **Style**: Naming, dead code, missing types (only if significant)

Output your review in this exact format:

CONFIDENCE: <0.0-1.0 how confident you are in the review>
VERDICT: <APPROVE|REQUEST_CHANGES|NEEDS_HUMAN_REVIEW>
SUMMARY: <1-3 sentence overall assessment>

FINDINGS:
- severity: <critical|major|minor|suggestion>
  category: <security|bug|performance|style|architecture>
  file: <filename>
  line: <line number or null>
  description: <what's wrong>
  suggestion: <how to fix>

If there are no findings, write FINDINGS: none

Focus on substance. Ignore formatting nitpicks unless they affect readability significantly.

Here is the diff:

```diff
{diff}
```\
"""


def get_pr_diff(workspace_path: Path | str, base_branch: str = "main") -> str:
    """Get the git diff of current branch against base."""
    result = subprocess.run(
        ["git", "diff", f"{base_branch}...HEAD"],
        cwd=str(workspace_path),
        capture_output=True,
        text=True,
    )
    return result.stdout


def _parse_findings(text: str) -> list[ReviewFinding]:
    """Parse findings from Codex response text."""
    findings = []
    if "FINDINGS: none" in text or "FINDINGS:\nnone" in text:
        return findings

    current: dict = {}
    in_findings = False

    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("FINDINGS:"):
            in_findings = True
            continue
        if not in_findings:
            continue

        if line.startswith("- severity:"):
            if current:
                findings.append(ReviewFinding(**current))
            current = {"severity": line.split(":", 1)[1].strip()}
        elif line.startswith("category:"):
            current["category"] = line.split(":", 1)[1].strip()
        elif line.startswith("file:"):
            current["file"] = line.split(":", 1)[1].strip()
        elif line.startswith("line:"):
            val = line.split(":", 1)[1].strip()
            try:
                current["line"] = int(val) if val not in ("null", "None", "") else None
            except ValueError:
                current["line"] = None
        elif line.startswith("description:"):
            current["description"] = line.split(":", 1)[1].strip()
        elif line.startswith("suggestion:"):
            current["suggestion"] = line.split(":", 1)[1].strip()

    if current and "severity" in current and "description" in current:
        current.setdefault("category", "style")
        current.setdefault("file", "unknown")
        current.setdefault("line", None)
        findings.append(ReviewFinding(**current))

    return findings


def _parse_verdict(text: str) -> ReviewVerdict:
    """Extract verdict from response."""
    for line in text.split("\n"):
        if line.strip().startswith("VERDICT:"):
            val = line.split(":", 1)[1].strip().upper()
            if "REQUEST" in val:
                return ReviewVerdict.REQUEST_CHANGES
            if "HUMAN" in val:
                return ReviewVerdict.NEEDS_HUMAN_REVIEW
            if "APPROVE" in val:
                return ReviewVerdict.APPROVE
    return ReviewVerdict.NEEDS_HUMAN_REVIEW


def _parse_confidence(text: str) -> float:
    """Extract confidence score from response."""
    for line in text.split("\n"):
        if line.strip().startswith("CONFIDENCE:"):
            try:
                return float(line.split(":", 1)[1].strip())
            except ValueError:
                return 0.0
    return 0.0


def _parse_summary(text: str) -> str:
    """Extract summary from response."""
    for line in text.split("\n"):
        if line.strip().startswith("SUMMARY:"):
            return line.split(":", 1)[1].strip()
    return ""


MAX_DIFF_CHARS = 60_000


def run_codex_review(
    diff: str,
    review_config: ReviewConfig,
    issue_title: str = "",
) -> CodexReviewResult:
    """Run code review via Codex CLI (uses ChatGPT Plus subscription tokens).

    Calls `codex exec --full-auto` with the review prompt.
    """
    if not diff.strip():
        return CodexReviewResult(
            verdict=ReviewVerdict.APPROVE,
            summary="No changes to review.",
            confidence=1.0,
        )

    truncated = False
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n... [truncated]"
        truncated = True

    prompt = REVIEW_PROMPT.format(diff=diff)
    if issue_title:
        prompt = f"PR: {issue_title}\n\n" + prompt

    try:
        codex_bin = _find_codex()
        result = subprocess.run(
            [codex_bin, "exec", "--full-auto", prompt],
            capture_output=True,
            text=True,
            timeout=120,
        )
        raw = result.stdout.strip()
    except FileNotFoundError as exc:
        return CodexReviewResult(
            verdict=ReviewVerdict.NEEDS_HUMAN_REVIEW,
            summary=f"Codex CLI not found: {exc}",
            confidence=0.0,
            raw_response=str(exc),
        )
    except subprocess.TimeoutExpired:
        return CodexReviewResult(
            verdict=ReviewVerdict.NEEDS_HUMAN_REVIEW,
            summary="Codex review timed out (120s)",
            confidence=0.0,
        )
    except Exception as exc:
        return CodexReviewResult(
            verdict=ReviewVerdict.NEEDS_HUMAN_REVIEW,
            summary=f"Codex review failed: {exc}",
            confidence=0.0,
            raw_response=str(exc),
        )

    review = CodexReviewResult(
        verdict=_parse_verdict(raw),
        summary=_parse_summary(raw),
        findings=_parse_findings(raw),
        raw_response=raw,
        confidence=_parse_confidence(raw),
    )

    if truncated:
        review = CodexReviewResult(
            verdict=review.verdict,
            summary=review.summary + " (diff was truncated)",
            findings=review.findings,
            raw_response=review.raw_response,
            confidence=max(review.confidence - 0.1, 0.0),
        )

    return review


def cto_evaluate(
    review: CodexReviewResult,
    review_config: ReviewConfig,
) -> tuple[ReviewVerdict, str]:
    """CTO (orchestrator) evaluates Codex review findings and makes final decision.

    Rules:
    - If Codex confidence >= auto_approve_threshold and verdict is APPROVE → auto-approve
    - If any finding has a category in require_human_review_labels → escalate to human
    - If critical/major findings → REQUEST_CHANGES
    - Otherwise → trust Codex verdict
    """
    if not review.findings and review.confidence >= review_config.auto_approve_threshold:
        return ReviewVerdict.APPROVE, "Codex review passed. No issues found."

    escalation_categories = set(review_config.require_human_review_labels)
    for finding in review.findings:
        if finding.category in escalation_categories:
            return (
                ReviewVerdict.NEEDS_HUMAN_REVIEW,
                f"Escalating to human: {finding.category} finding in {finding.file} — {finding.description}",
            )

    critical = [f for f in review.findings if f.severity in ("critical", "major")]
    if critical:
        descriptions = "; ".join(f"[{f.severity}] {f.file}: {f.description}" for f in critical[:3])
        return ReviewVerdict.REQUEST_CHANGES, f"Codex found issues: {descriptions}"

    if review.verdict == ReviewVerdict.APPROVE and review.confidence >= review_config.auto_approve_threshold:
        return ReviewVerdict.APPROVE, f"Codex approved with {len(review.findings)} minor notes."

    return review.verdict, review.summary


def format_review_for_workpad(review: CodexReviewResult, cto_verdict: ReviewVerdict, cto_reason: str) -> str:
    """Format review results for the Linear workpad comment."""
    lines = [
        "### Code Review (Codex CLI)",
        f"**Codex verdict**: {review.verdict.value} (confidence: {review.confidence:.0%})",
        f"**CTO decision**: {cto_verdict.value}",
        f"**Reason**: {cto_reason}",
        "",
    ]

    if review.findings:
        lines.append("**Findings:**")
        for f in review.findings:
            emoji = {"critical": "🔴", "major": "🟠", "minor": "🟡", "suggestion": "💡"}.get(f.severity, "•")
            lines.append(f"- {emoji} [{f.severity}] `{f.file}`: {f.description}")
            if f.suggestion:
                lines.append(f"  → {f.suggestion}")
        lines.append("")

    if review.summary:
        lines.append(f"**Summary**: {review.summary}")

    return "\n".join(lines)
