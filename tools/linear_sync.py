#!/usr/bin/env python3
"""CLI for syncing TokenStats project data to Linear.

Usage:
    python linear_sync.py init              # Create team, project, labels, cycles, workflow
    python linear_sync.py sync              # Create epics, stories, QA issues, relations
    python linear_sync.py move US-XX "State"  # Move issue to a workflow state
    python linear_sync.py comment US-XX "msg" # Add comment to an issue
    python linear_sync.py status            # Print all issues with statuses
"""

import sys
from datetime import date

from config import (
    TEAM_KEY,
    TEAM_NAME,
    PROJECT_NAME,
    USER_STORIES_PATH,
    TEST_STRATEGY_PATH,
)
from linear_client import LinearClient, load_state, save_state
from models import (
    ALL_LABELS,
    COMPONENT_LABELS,
    EPIC_COMPONENTS,
    MOSCOW_TO_PRIORITY,
    ROLE_LABELS,
    STORY_DEPENDENCIES,
    STORY_ROLES,
    WORKFLOW_STATES,
    get_sprints,
    get_story_sprint,
)
from parsers.user_stories import parse_file as parse_stories_file
from parsers.test_strategy import parse_file as parse_tests_file, get_related_stories


# Label colors
LABEL_COLORS = {
    "role:PM": "#F59E0B",
    "role:PA": "#8B5CF6",
    "role:UX": "#EC4899",
    "role:BE": "#3B82F6",
    "role:FE": "#10B981",
    "role:QA": "#EF4444",
    "component:backend": "#6366F1",
    "component:ios": "#0EA5E9",
    "component:watchos": "#F97316",
    "component:garmin": "#14B8A6",
    "component:wearos": "#A855F7",
}

STATE_COLORS = {
    "Backlog": "#bec2c8",
    "Todo": "#e2e2e2",
    "In Progress": "#f2c94c",
    "In Review": "#5e6ad2",
    "Blocked": "#eb5757",
    "Done": "#5e6ad2",
    "Cancelled": "#95a2b3",
}


def cmd_init():
    """Create team, project, labels, cycles, and workflow states in Linear."""
    client = LinearClient()
    state = load_state()

    # 1. Find or create team
    if "team_id" not in state:
        teams = client.get_teams()
        team = next((t for t in teams if t["key"] == TEAM_KEY), None)
        if not team:
            print(f"Creating team {TEAM_NAME} ({TEAM_KEY})...")
            team = client.create_team(TEAM_NAME, TEAM_KEY)
        state["team_id"] = team["id"]
        save_state(state)
        print(f"  Team: {team['name']} [{team['id'][:8]}]")
    else:
        print(f"  Team: already exists [{state['team_id'][:8]}]")

    team_id = state["team_id"]

    # 2. Workflow states
    if "states" not in state:
        print("Setting up workflow states...")
        existing = client.get_workflow_states(team_id)
        existing_names = {s["name"] for s in existing}
        states_map = {s["name"]: s["id"] for s in existing}

        for i, (name, stype) in enumerate(WORKFLOW_STATES):
            if name not in existing_names:
                color = STATE_COLORS.get(name, "#6B7280")
                ws = client.create_workflow_state(team_id, name, stype, i, color)
                states_map[name] = ws["id"]
                print(f"  Created state: {name} ({stype})")
            else:
                print(f"  State exists: {name}")

        state["states"] = states_map
        save_state(state)
    else:
        print(f"  Workflow states: already configured ({len(state['states'])} states)")

    # 3. Labels
    if "labels" not in state:
        print("Creating labels...")
        existing = client.get_labels(team_id)
        existing_names = {l["name"] for l in existing}
        labels_map = {l["name"]: l["id"] for l in existing}

        for label in ALL_LABELS:
            if label not in existing_names:
                color = LABEL_COLORS.get(label, "#6B7280")
                l = client.create_label(team_id, label, color)
                labels_map[label] = l["id"]
                print(f"  Created label: {label}")
            else:
                print(f"  Label exists: {label}")

        state["labels"] = labels_map
        save_state(state)
    else:
        print(f"  Labels: already configured ({len(state['labels'])} labels)")

    # 4. Project
    if "project_id" not in state:
        projects = client.get_projects()
        project = next((p for p in projects if p["name"] == PROJECT_NAME), None)
        if not project:
            print(f"Creating project {PROJECT_NAME}...")
            project = client.create_project(PROJECT_NAME, [team_id])
        state["project_id"] = project["id"]
        print(f"  Project: {project['name']} [{project['id'][:8]}]")
    else:
        print(f"  Project: already exists [{state['project_id'][:8]}]")

    # 5. Cycles (sprints)
    if "cycles" not in state:
        print("Creating cycles (sprints)...")
        existing = client.get_cycles(team_id)
        existing_names = {c["name"] for c in existing}
        cycles_map = {c["name"]: c["id"] for c in existing}

        for sprint in get_sprints():
            if sprint.name not in existing_names:
                cycle = client.create_cycle(
                    team_id,
                    sprint.name,
                    sprint.start_date.isoformat(),
                    sprint.end_date.isoformat(),
                )
                cycles_map[sprint.name] = cycle["id"]
                print(f"  Created cycle: {sprint.name} ({sprint.start_date} → {sprint.end_date})")
            else:
                print(f"  Cycle exists: {sprint.name}")

        state["cycles"] = cycles_map
    else:
        print(f"  Cycles: already configured ({len(state['cycles'])} cycles)")

    save_state(state)
    print("\nInit complete. Run 'python linear_sync.py sync' to create issues.")


def cmd_sync():
    """Create epics, user stories, QA issues, and relations from docs."""
    client = LinearClient()
    state = load_state()

    if "team_id" not in state:
        print("Error: run 'init' first.")
        sys.exit(1)

    team_id = state["team_id"]
    project_id = state.get("project_id")
    states_map = state.get("states", {})
    labels_map = state.get("labels", {})
    cycles_map = state.get("cycles", {})

    backlog_id = states_map.get("Backlog")
    sprints = get_sprints()

    # Parse source files
    epics, stories, criteria = parse_stories_file(USER_STORIES_PATH)
    test_cases = parse_tests_file(TEST_STRATEGY_PATH)

    # Build criteria lookup
    criteria_map = {c.story_id: c for c in criteria}

    # 1. Create epics as parent issues
    if "epics" not in state:
        state["epics"] = {}
    epics_map = state["epics"]

    print("Creating epics...")
    for epic in epics:
        if epic.id in epics_map:
            print(f"  Epic exists: {epic.id} — {epic.name}")
            continue

        component_label = EPIC_COMPONENTS.get(epic.id)
        label_ids = [labels_map[component_label]] if component_label and component_label in labels_map else []

        sprint = get_story_sprint(epic.id, sprints)
        cycle_id = cycles_map.get(sprint.name) if sprint else None

        issue = client.create_issue(
            team_id=team_id,
            title=f"[{epic.id}] {epic.name}",
            description=f"**Epic:** {epic.name}\n\n{epic.description}\n\n**Component:** {epic.component}",
            state_id=backlog_id,
            label_ids=label_ids,
            project_id=project_id,
            cycle_id=cycle_id,
        )
        epics_map[epic.id] = issue["id"]
        print(f"  Created: {issue['identifier']} — [{epic.id}] {epic.name}")

    state["epics"] = epics_map

    # 2. Create user stories as sub-issues
    if "stories" not in state:
        state["stories"] = {}
    stories_map = state["stories"]

    print("\nCreating user stories...")
    for story in stories:
        if story.id in stories_map:
            print(f"  Story exists: {story.id}")
            continue

        # Build description with acceptance criteria
        desc_parts = [f"**User Story:** {story.text}", f"\n**MoSCoW:** {story.moscow}"]
        ac = criteria_map.get(story.id)
        if ac:
            desc_parts.append(f"\n---\n\n## Acceptance Criteria: {ac.title}\n\n```gherkin\n{ac.gherkin}\n```")

        description = "\n".join(desc_parts)
        priority = MOSCOW_TO_PRIORITY.get(story.moscow, 0)

        # Labels: role + component
        label_ids = []
        for role in STORY_ROLES.get(story.id, []):
            if role in labels_map:
                label_ids.append(labels_map[role])
        component = EPIC_COMPONENTS.get(story.epic_id)
        if component and component in labels_map:
            label_ids.append(labels_map[component])

        parent_id = epics_map.get(story.epic_id)
        sprint = get_story_sprint(story.epic_id, sprints)
        cycle_id = cycles_map.get(sprint.name) if sprint else None

        issue = client.create_issue(
            team_id=team_id,
            title=f"[{story.id}] {story.text[:80]}",
            description=description,
            priority=priority,
            state_id=backlog_id,
            label_ids=label_ids,
            parent_id=parent_id,
            project_id=project_id,
            cycle_id=cycle_id,
        )
        stories_map[story.id] = issue["id"]
        print(f"  Created: {issue['identifier']} — {story.id} (P{priority})")

    state["stories"] = stories_map

    # 3. Create QA sub-issues for test case groups
    if "qa_issues" not in state:
        state["qa_issues"] = {}
    qa_map = state["qa_issues"]

    print("\nCreating QA test issues...")
    # Group test cases by section
    sections: dict[str, list] = {}
    for tc in test_cases:
        sections.setdefault(tc.section, []).append(tc)

    qa_label_id = labels_map.get("role:QA")

    for section_name, cases in sections.items():
        key = section_name[:50]
        if key in qa_map:
            print(f"  QA section exists: {key}")
            continue

        # Build checklist from test cases
        checklist = "\n".join(
            f"- [ ] **{tc.id}** {tc.name}: {tc.steps} → {tc.expected}"
            for tc in cases
        )
        description = f"## QA: {section_name}\n\n{checklist}"

        # Find related story for parent
        related = set()
        for tc in cases:
            related.update(get_related_stories(tc.id))

        # Use the first related story as parent (if it exists)
        parent_id = None
        for sid in sorted(related):
            if sid in stories_map:
                parent_id = stories_map[sid]
                break

        label_ids = [qa_label_id] if qa_label_id else []

        issue = client.create_issue(
            team_id=team_id,
            title=f"[QA] {section_name}",
            description=description,
            priority=2,
            state_id=backlog_id,
            label_ids=label_ids,
            parent_id=parent_id,
            project_id=project_id,
        )
        qa_map[key] = issue["id"]
        print(f"  Created: {issue['identifier']} — QA: {section_name}")

    state["qa_issues"] = qa_map

    # 4. Create relations (dependencies)
    if "relations_created" not in state:
        print("\nCreating issue relations (dependencies)...")
        relations_created = 0
        for story_id, deps in STORY_DEPENDENCIES.items():
            if story_id not in stories_map:
                continue
            for dep_id in deps:
                if dep_id not in stories_map:
                    continue
                try:
                    client.create_relation(
                        issue_id=stories_map[dep_id],
                        related_issue_id=stories_map[story_id],
                        relation_type="blocks",
                    )
                    relations_created += 1
                    print(f"  {dep_id} blocks {story_id}")
                except RuntimeError as e:
                    # Relation may already exist
                    print(f"  Skipping {dep_id}→{story_id}: {e}")

        state["relations_created"] = relations_created
        print(f"  Total relations: {relations_created}")

    save_state(state)
    print("\nSync complete.")


def cmd_move(story_id: str, target_state: str):
    """Move an issue to a different workflow state."""
    client = LinearClient()
    state = load_state()

    stories_map = state.get("stories", {})
    states_map = state.get("states", {})

    issue_id = stories_map.get(story_id)
    if not issue_id:
        # Try epics
        issue_id = state.get("epics", {}).get(story_id)
    if not issue_id:
        print(f"Error: {story_id} not found in state file.")
        sys.exit(1)

    state_id = states_map.get(target_state)
    if not state_id:
        print(f"Error: state '{target_state}' not found. Available: {list(states_map.keys())}")
        sys.exit(1)

    issue = client.update_issue(issue_id, stateId=state_id)
    print(f"Moved {issue['identifier']} to '{target_state}'")


def cmd_comment(story_id: str, message: str):
    """Add a comment to an issue."""
    client = LinearClient()
    state = load_state()

    stories_map = state.get("stories", {})
    issue_id = stories_map.get(story_id)
    if not issue_id:
        issue_id = state.get("epics", {}).get(story_id)
    if not issue_id:
        print(f"Error: {story_id} not found in state file.")
        sys.exit(1)

    comment = client.create_comment(issue_id, message)
    print(f"Comment added to {story_id}: {message[:60]}...")


def cmd_status():
    """Print all issues with their current statuses."""
    client = LinearClient()
    state = load_state()
    team_id = state.get("team_id")

    if not team_id:
        print("Error: run 'init' first.")
        sys.exit(1)

    issues = client.get_issues(team_id)

    # Group by state
    by_state: dict[str, list] = {}
    for issue in issues:
        state_name = issue["state"]["name"]
        by_state.setdefault(state_name, []).append(issue)

    # Print in workflow order
    state_order = [s[0] for s in WORKFLOW_STATES]
    total = len(issues)

    print(f"\nTokenStats — {total} issues\n{'='*50}")
    for state_name in state_order:
        group = by_state.get(state_name, [])
        if not group:
            continue
        print(f"\n{state_name} ({len(group)}):")
        for issue in sorted(group, key=lambda x: x["identifier"]):
            labels = ", ".join(l["name"] for l in issue.get("labels", {}).get("nodes", []))
            priority = ["None", "Urgent", "High", "Medium", "Low"][issue.get("priority", 0)]
            print(f"  {issue['identifier']:10s} P:{priority:6s} {issue['title'][:60]}")
            if labels:
                print(f"{'':12s} labels: {labels}")

    # Summary
    done = len(by_state.get("Done", []))
    blocked = len(by_state.get("Blocked", []))
    in_progress = len(by_state.get("In Progress", []))
    print(f"\n{'='*50}")
    print(f"Done: {done}/{total} | In Progress: {in_progress} | Blocked: {blocked}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "init":
        cmd_init()
    elif command == "sync":
        cmd_sync()
    elif command == "move":
        if len(sys.argv) < 4:
            print("Usage: python linear_sync.py move <US-XX> <State>")
            sys.exit(1)
        cmd_move(sys.argv[2], sys.argv[3])
    elif command == "comment":
        if len(sys.argv) < 4:
            print("Usage: python linear_sync.py comment <US-XX> <message>")
            sys.exit(1)
        cmd_comment(sys.argv[2], " ".join(sys.argv[3:]))
    elif command == "status":
        cmd_status()
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
