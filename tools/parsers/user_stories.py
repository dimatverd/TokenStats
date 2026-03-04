"""Parser for user-stories-mvp.md — extracts epics, stories, and acceptance criteria."""

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AcceptanceCriteria:
    story_id: str
    title: str
    gherkin: str


@dataclass
class UserStory:
    id: str
    text: str
    moscow: str
    epic_id: str


@dataclass
class Epic:
    id: str
    name: str
    description: str
    component: str


def parse_epics(content: str) -> list[Epic]:
    """Parse epic table from markdown."""
    epics = []
    # Match rows like: | E1 | Name | Description | Component |
    pattern = re.compile(
        r"^\|\s*(E\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|",
        re.MULTILINE,
    )
    for m in pattern.finditer(content):
        epics.append(Epic(
            id=m.group(1).strip(),
            name=m.group(2).strip(),
            description=m.group(3).strip(),
            component=m.group(4).strip(),
        ))
    return epics


def parse_user_stories(content: str) -> list[UserStory]:
    """Parse user story tables from markdown."""
    stories = []
    # Find epic sections like ### E1 — Name
    epic_pattern = re.compile(r"###\s+(E\d+)\s*[—–-]")
    # Find story rows
    story_pattern = re.compile(
        r"^\|\s*(US-\d+)\s*\|\s*(.+?)\s*\|\s*\*\*(\w+[^*]*)\*\*\s*(?:\(.+?\))?\s*\|",
        re.MULTILINE,
    )

    seen_ids: set[str] = set()

    # Find boundary for "Не входит в MVP" or next major section
    not_mvp_pos = None
    not_mvp_match = re.search(r"###\s+Не входит в MVP", content)
    if not_mvp_match:
        not_mvp_pos = not_mvp_match.start()

    # Split by epic sections
    epic_sections = list(epic_pattern.finditer(content))
    for i, epic_match in enumerate(epic_sections):
        epic_id = epic_match.group(1)
        start = epic_match.start()
        end = epic_sections[i + 1].start() if i + 1 < len(epic_sections) else (not_mvp_pos or len(content))
        section = content[start:end]

        for sm in story_pattern.finditer(section):
            sid = sm.group(1).strip()
            if sid not in seen_ids:
                seen_ids.add(sid)
                stories.append(UserStory(
                    id=sid,
                    text=sm.group(2).strip(),
                    moscow=sm.group(3).strip(),
                    epic_id=epic_id,
                ))

    # Also parse "Не входит в MVP" section
    if not_mvp_match:
        section = content[not_mvp_match.start():]
        for sm in story_pattern.finditer(section):
            story_id = sm.group(1).strip()
            if story_id not in seen_ids:
                seen_ids.add(story_id)
                moscow = sm.group(3).strip()
                epic_id = _story_to_epic(story_id)
                stories.append(UserStory(
                    id=story_id,
                    text=sm.group(2).strip(),
                    moscow=moscow,
                    epic_id=epic_id,
                ))

    return stories


def _story_to_epic(story_id: str) -> str:
    """Map story ID to epic based on numbering convention."""
    num = int(story_id.split("-")[1])
    if num <= 3:
        return "E1"
    elif num <= 8:
        return "E2"
    elif num <= 11:
        return "E3"
    elif num <= 14:
        return "E4"
    elif num <= 18:
        return "E5"
    elif num <= 22:
        return "E6"
    elif num <= 24:
        return "E7"
    else:
        # Won't stories (25-28) — map to closest relevant epic
        mapping = {"US-25": "E6", "US-26": "E6", "US-27": "E5", "US-28": "E6"}
        return mapping.get(story_id, "E7")


def parse_acceptance_criteria(content: str) -> list[AcceptanceCriteria]:
    """Parse acceptance criteria (Gherkin blocks) from markdown."""
    criteria = []
    # Match sections like ### US-01: Title followed by ```gherkin ... ```
    pattern = re.compile(
        r"###\s+(US-\d+):\s*(.+?)\n\s*```gherkin\n(.*?)```",
        re.DOTALL,
    )
    for m in pattern.finditer(content):
        criteria.append(AcceptanceCriteria(
            story_id=m.group(1).strip(),
            title=m.group(2).strip(),
            gherkin=m.group(3).strip(),
        ))
    return criteria


def parse_file(path: Path) -> tuple[list[Epic], list[UserStory], list[AcceptanceCriteria]]:
    """Parse the full user stories file."""
    content = path.read_text(encoding="utf-8")
    return parse_epics(content), parse_user_stories(content), parse_acceptance_criteria(content)
