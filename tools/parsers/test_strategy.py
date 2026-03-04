"""Parser for test-strategy.md — extracts test cases from markdown tables."""

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TestCase:
    id: str
    section: str
    name: str
    steps: str
    expected: str


def parse_test_cases(content: str) -> list[TestCase]:
    """Parse all test case tables from the test strategy document."""
    cases = []
    current_section = ""

    # Track section headers (## or ###)
    lines = content.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]

        # Update section header
        header_match = re.match(r"^#{2,3}\s+\d+\.\d+\s+(.+)", line)
        if header_match:
            current_section = header_match.group(1).strip()

        # Parse table rows with test IDs
        # Format: | ID | Name | Steps | Expected |
        row_match = re.match(
            r"^\|\s*([A-Z]{1,5}-\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|",
            line,
        )
        if row_match:
            cases.append(TestCase(
                id=row_match.group(1).strip(),
                section=current_section,
                name=row_match.group(2).strip(),
                steps=row_match.group(3).strip(),
                expected=row_match.group(4).strip(),
            ))

        i += 1

    return cases


def parse_file(path: Path) -> list[TestCase]:
    """Parse the test strategy file."""
    content = path.read_text(encoding="utf-8")
    return parse_test_cases(content)


# Map test case prefixes to related user stories
TEST_PREFIX_TO_STORIES: dict[str, list[str]] = {
    "UP": ["US-09", "US-10", "US-11"],     # Unit Provider → E3
    "UC": ["US-10"],                         # Unit Cache → US-10
    "UJ": ["US-02", "US-03"],               # Unit JWT → E1
    "UE": ["US-07"],                         # Unit Encryption → US-07
    "IA": ["US-01", "US-02", "US-04", "US-05", "US-06", "US-12"],  # Integration API
    "ID": ["US-04", "US-07"],               # Integration DB
    "E2E": ["US-12"],                        # E2E
    "SEC": ["US-07", "US-02"],              # Security
    "AW": ["US-19", "US-20", "US-21", "US-22"],  # Apple Watch
    "GR": ["US-25"],                         # Garmin
    "WO": ["US-26"],                         # Wear OS
    "LT": ["US-10", "US-12"],              # Load test
}


def get_related_stories(test_id: str) -> list[str]:
    """Get user story IDs related to a test case."""
    prefix = re.match(r"([A-Z]+)", test_id)
    if prefix:
        return TEST_PREFIX_TO_STORIES.get(prefix.group(1), [])
    return []
