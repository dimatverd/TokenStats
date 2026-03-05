"""Tests for Codex code review integration."""

from orchestrator.config import ReviewConfig
from orchestrator.reviewer import (
    CodexReviewResult,
    ReviewFinding,
    ReviewVerdict,
    _parse_confidence,
    _parse_findings,
    _parse_summary,
    _parse_verdict,
    cto_evaluate,
    format_review_for_workpad,
)

SAMPLE_RESPONSE = """\
CONFIDENCE: 0.85
VERDICT: REQUEST_CHANGES
SUMMARY: Found a potential SQL injection in the query builder.

FINDINGS:
- severity: critical
  category: security
  file: backend/app/db.py
  line: 42
  description: Raw string interpolation in SQL query
  suggestion: Use parameterized queries instead
- severity: minor
  category: style
  file: backend/app/main.py
  line: 10
  description: Unused import
  suggestion: Remove unused import
"""


def test_parse_verdict() -> None:
    assert _parse_verdict(SAMPLE_RESPONSE) == ReviewVerdict.REQUEST_CHANGES
    assert _parse_verdict("VERDICT: APPROVE") == ReviewVerdict.APPROVE
    assert _parse_verdict("VERDICT: NEEDS_HUMAN_REVIEW") == ReviewVerdict.NEEDS_HUMAN_REVIEW
    assert _parse_verdict("no verdict") == ReviewVerdict.NEEDS_HUMAN_REVIEW  # default


def test_parse_confidence() -> None:
    assert _parse_confidence(SAMPLE_RESPONSE) == 0.85
    assert _parse_confidence("no confidence") == 0.0


def test_parse_summary() -> None:
    assert "SQL injection" in _parse_summary(SAMPLE_RESPONSE)


def test_parse_findings() -> None:
    findings = _parse_findings(SAMPLE_RESPONSE)
    assert len(findings) == 2
    assert findings[0].severity == "critical"
    assert findings[0].category == "security"
    assert findings[0].file == "backend/app/db.py"
    assert findings[0].line == 42
    assert findings[1].severity == "minor"


def test_parse_findings_none() -> None:
    assert _parse_findings("FINDINGS: none") == []


def test_cto_evaluate_approve_high_confidence() -> None:
    review = CodexReviewResult(
        verdict=ReviewVerdict.APPROVE,
        summary="All good",
        findings=[],
        confidence=0.9,
    )
    config = ReviewConfig()
    verdict, reason = cto_evaluate(review, config)
    assert verdict == ReviewVerdict.APPROVE


def test_cto_evaluate_escalate_security() -> None:
    review = CodexReviewResult(
        verdict=ReviewVerdict.REQUEST_CHANGES,
        summary="Security issue",
        findings=[
            ReviewFinding(
                severity="critical",
                category="security",
                file="test.py",
                line=1,
                description="SQL injection",
            )
        ],
        confidence=0.9,
    )
    config = ReviewConfig()
    verdict, reason = cto_evaluate(review, config)
    assert verdict == ReviewVerdict.NEEDS_HUMAN_REVIEW
    assert "security" in reason


def test_cto_evaluate_request_changes_critical() -> None:
    review = CodexReviewResult(
        verdict=ReviewVerdict.REQUEST_CHANGES,
        summary="Bug found",
        findings=[
            ReviewFinding(
                severity="critical",
                category="bug",
                file="test.py",
                line=1,
                description="Off-by-one error",
            )
        ],
        confidence=0.8,
    )
    config = ReviewConfig()
    verdict, reason = cto_evaluate(review, config)
    assert verdict == ReviewVerdict.REQUEST_CHANGES


def test_format_review_for_workpad() -> None:
    review = CodexReviewResult(
        verdict=ReviewVerdict.APPROVE,
        summary="Clean code",
        findings=[
            ReviewFinding(
                severity="minor",
                category="style",
                file="test.py",
                line=5,
                description="Could use better naming",
                suggestion="Rename to descriptive_name",
            )
        ],
        confidence=0.9,
    )
    text = format_review_for_workpad(review, ReviewVerdict.APPROVE, "Looks good")
    assert "Codex CLI" in text
    assert "APPROVE" in text.lower() or "approve" in text
    assert "Could use better naming" in text
