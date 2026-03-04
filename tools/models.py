"""Static mappings for Linear integration."""

from dataclasses import dataclass, field
from datetime import date, timedelta

# MoSCoW → Linear priority (1=Urgent, 2=High, 3=Medium, 4=Low, 0=NoPriority)
MOSCOW_TO_PRIORITY: dict[str, int] = {
    "Must": 1,
    "Should": 2,
    "Could": 3,
    "Won't": 4,
}

# Role labels
ROLE_LABELS = [
    "role:PM",
    "role:PA",   # Product Analyst
    "role:UX",   # Designer
    "role:BE",   # Backend
    "role:FE",   # Frontend
    "role:QA",
]

# Component labels
COMPONENT_LABELS = [
    "component:backend",
    "component:ios",
    "component:watchos",
    "component:garmin",
    "component:wearos",
]

ALL_LABELS = ROLE_LABELS + COMPONENT_LABELS

# Workflow states in order
WORKFLOW_STATES = [
    ("Backlog", "backlog"),
    ("Todo", "unstarted"),
    ("In Progress", "started"),
    ("In Review", "started"),
    ("Blocked", "started"),
    ("Done", "completed"),
    ("Cancelled", "canceled"),
]

# Epic → component mapping
EPIC_COMPONENTS: dict[str, str] = {
    "E1": "component:backend",
    "E2": "component:backend",
    "E3": "component:backend",
    "E4": "component:backend",
    "E5": "component:ios",
    "E6": "component:watchos",
    "E7": "component:backend",
}

# Story → role labels mapping
STORY_ROLES: dict[str, list[str]] = {
    "US-01": ["role:BE"],
    "US-02": ["role:BE"],
    "US-03": ["role:BE"],
    "US-04": ["role:BE"],
    "US-05": ["role:BE"],
    "US-06": ["role:BE"],
    "US-07": ["role:BE"],
    "US-08": ["role:BE"],
    "US-09": ["role:BE"],
    "US-10": ["role:BE"],
    "US-11": ["role:BE"],
    "US-12": ["role:BE"],
    "US-13": ["role:BE"],
    "US-14": ["role:BE"],
    "US-15": ["role:FE", "role:UX"],
    "US-16": ["role:FE", "role:UX"],
    "US-17": ["role:FE"],
    "US-18": ["role:FE", "role:UX"],
    "US-19": ["role:FE", "role:UX"],
    "US-20": ["role:FE", "role:UX"],
    "US-21": ["role:FE"],
    "US-22": ["role:FE"],
    "US-23": ["role:BE", "role:FE"],
    "US-24": ["role:BE", "role:FE"],
    "US-25": ["role:FE"],
    "US-26": ["role:FE"],
    "US-27": ["role:FE"],
    "US-28": ["role:FE"],
}

# Story dependencies: story_id → list of stories it depends on (blocked by)
STORY_DEPENDENCIES: dict[str, list[str]] = {
    "US-02": ["US-01"],
    "US-04": ["US-02"],
    "US-05": ["US-02"],
    "US-06": ["US-02"],
    "US-07": ["US-04", "US-05", "US-06"],
    "US-08": ["US-04"],
    "US-09": ["US-07"],
    "US-10": ["US-09"],
    "US-11": ["US-09"],
    "US-12": ["US-10"],
    "US-13": ["US-12"],
    "US-14": ["US-12"],
    "US-15": ["US-02"],
    "US-16": ["US-12", "US-15"],
    "US-17": ["US-16"],
    "US-19": ["US-17"],
    "US-20": ["US-19"],
    "US-21": ["US-19"],
    "US-22": ["US-17"],
    "US-23": ["US-09"],
    "US-24": ["US-23"],
}

# Sprint definitions
@dataclass
class Sprint:
    name: str
    epics: list[str]
    start_date: date
    duration_weeks: int = 2

    @property
    def end_date(self) -> date:
        return self.start_date + timedelta(weeks=self.duration_weeks)


def get_sprints(start: date | None = None) -> list[Sprint]:
    """Generate sprint schedule starting from given date."""
    if start is None:
        # Start next Monday
        today = date.today()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        start = today + timedelta(days=days_until_monday)

    return [
        Sprint("Sprint 1", ["E1", "E2", "E3"], start),
        Sprint("Sprint 2", ["E4", "E5"], start + timedelta(weeks=2)),
        Sprint("Sprint 3", ["E6", "E7"], start + timedelta(weeks=4)),
    ]


# Map epic to sprint
def get_story_sprint(epic_id: str, sprints: list[Sprint]) -> Sprint | None:
    for sprint in sprints:
        if epic_id in sprint.epics:
            return sprint
    return None
