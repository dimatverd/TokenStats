"""GraphQL client for Linear API."""

import json
from pathlib import Path
from typing import Any

import httpx

from config import LINEAR_API_KEY, LINEAR_API_URL, STATE_FILE


class LinearClient:
    """Thin wrapper around Linear's GraphQL API."""

    def __init__(self, api_key: str = LINEAR_API_KEY):
        self.api_key = api_key
        self.headers = {
            "Authorization": api_key,
            "Content-Type": "application/json",
        }

    def _request(self, query: str, variables: dict | None = None) -> dict:
        """Execute a GraphQL query/mutation."""
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        resp = httpx.post(LINEAR_API_URL, json=payload, headers=self.headers, timeout=30)
        data = resp.json()
        if "errors" in data:
            raise RuntimeError(f"Linear API error: {data['errors']}")
        if resp.status_code >= 400:
            raise RuntimeError(f"Linear HTTP {resp.status_code}: {resp.text[:300]}")
        return data["data"]

    # ── Team ────────────────────────────────────────────────

    def get_teams(self) -> list[dict]:
        data = self._request("{ teams { nodes { id name key } } }")
        return data["teams"]["nodes"]

    def create_team(self, name: str, key: str) -> dict:
        mutation = """
        mutation($input: TeamCreateInput!) {
            teamCreate(input: $input) {
                success
                team { id name key }
            }
        }"""
        data = self._request(mutation, {"input": {"name": name, "key": key}})
        return data["teamCreate"]["team"]

    # ── Workflow States ─────────────────────────────────────

    def get_workflow_states(self, team_id: str) -> list[dict]:
        query = """
        query($teamId: ID!) {
            workflowStates(filter: { team: { id: { eq: $teamId } } }) {
                nodes { id name type position }
            }
        }"""
        data = self._request(query, {"teamId": team_id})
        return data["workflowStates"]["nodes"]

    def create_workflow_state(self, team_id: str, name: str, state_type: str, position: int, color: str = "#6B7280") -> dict:
        mutation = """
        mutation($input: WorkflowStateCreateInput!) {
            workflowStateCreate(input: $input) {
                success
                workflowState { id name type }
            }
        }"""
        data = self._request(mutation, {
            "input": {"teamId": team_id, "name": name, "type": state_type, "position": position, "color": color}
        })
        return data["workflowStateCreate"]["workflowState"]

    # ── Project ─────────────────────────────────────────────

    def create_project(self, name: str, team_ids: list[str]) -> dict:
        mutation = """
        mutation($input: ProjectCreateInput!) {
            projectCreate(input: $input) {
                success
                project { id name }
            }
        }"""
        data = self._request(mutation, {"input": {"name": name, "teamIds": team_ids}})
        return data["projectCreate"]["project"]

    def get_projects(self) -> list[dict]:
        data = self._request("{ projects { nodes { id name } } }")
        return data["projects"]["nodes"]

    # ── Labels ──────────────────────────────────────────────

    def get_labels(self, team_id: str) -> list[dict]:
        query = """
        query($teamId: ID!) {
            issueLabels(filter: { team: { id: { eq: $teamId } } }) {
                nodes { id name }
            }
        }"""
        data = self._request(query, {"teamId": team_id})
        return data["issueLabels"]["nodes"]

    def create_label(self, team_id: str, name: str, color: str = "#6B7280") -> dict:
        mutation = """
        mutation($input: IssueLabelCreateInput!) {
            issueLabelCreate(input: $input) {
                success
                issueLabel { id name }
            }
        }"""
        data = self._request(mutation, {
            "input": {"teamId": team_id, "name": name, "color": color}
        })
        return data["issueLabelCreate"]["issueLabel"]

    # ── Cycles ──────────────────────────────────────────────

    def get_cycles(self, team_id: str) -> list[dict]:
        query = """
        query($teamId: ID!) {
            cycles(filter: { team: { id: { eq: $teamId } } }) {
                nodes { id name number startsAt endsAt }
            }
        }"""
        data = self._request(query, {"teamId": team_id})
        return data["cycles"]["nodes"]

    def create_cycle(self, team_id: str, name: str, starts_at: str, ends_at: str) -> dict:
        mutation = """
        mutation($input: CycleCreateInput!) {
            cycleCreate(input: $input) {
                success
                cycle { id name number startsAt endsAt }
            }
        }"""
        data = self._request(mutation, {
            "input": {"teamId": team_id, "name": name, "startsAt": starts_at, "endsAt": ends_at}
        })
        return data["cycleCreate"]["cycle"]

    # ── Issues ──────────────────────────────────────────────

    def create_issue(
        self,
        team_id: str,
        title: str,
        description: str = "",
        priority: int = 0,
        state_id: str | None = None,
        label_ids: list[str] | None = None,
        parent_id: str | None = None,
        project_id: str | None = None,
        cycle_id: str | None = None,
    ) -> dict:
        mutation = """
        mutation($input: IssueCreateInput!) {
            issueCreate(input: $input) {
                success
                issue { id identifier title url }
            }
        }"""
        input_data: dict[str, Any] = {"teamId": team_id, "title": title}
        if description:
            input_data["description"] = description
        if priority:
            input_data["priority"] = priority
        if state_id:
            input_data["stateId"] = state_id
        if label_ids:
            input_data["labelIds"] = label_ids
        if parent_id:
            input_data["parentId"] = parent_id
        if project_id:
            input_data["projectId"] = project_id
        if cycle_id:
            input_data["cycleId"] = cycle_id

        data = self._request(mutation, {"input": input_data})
        return data["issueCreate"]["issue"]

    def get_issues(self, team_id: str) -> list[dict]:
        query = """
        query($teamId: ID!) {
            issues(filter: { team: { id: { eq: $teamId } } }, first: 250) {
                nodes { id identifier title state { id name } priority labels { nodes { name } } }
            }
        }"""
        data = self._request(query, {"teamId": team_id})
        return data["issues"]["nodes"]

    def update_issue(self, issue_id: str, **kwargs: Any) -> dict:
        mutation = """
        mutation($id: String!, $input: IssueUpdateInput!) {
            issueUpdate(id: $id, input: $input) {
                success
                issue { id identifier title state { name } }
            }
        }"""
        data = self._request(mutation, {"id": issue_id, "input": kwargs})
        return data["issueUpdate"]["issue"]

    # ── Relations ───────────────────────────────────────────

    def create_relation(self, issue_id: str, related_issue_id: str, relation_type: str = "blocks") -> dict:
        mutation = """
        mutation($input: IssueRelationCreateInput!) {
            issueRelationCreate(input: $input) {
                success
                issueRelation { id type }
            }
        }"""
        data = self._request(mutation, {
            "input": {"issueId": issue_id, "relatedIssueId": related_issue_id, "type": relation_type}
        })
        return data["issueRelationCreate"]["issueRelation"]

    # ── Comments ────────────────────────────────────────────

    def create_comment(self, issue_id: str, body: str) -> dict:
        mutation = """
        mutation($input: CommentCreateInput!) {
            commentCreate(input: $input) {
                success
                comment { id body }
            }
        }"""
        data = self._request(mutation, {"input": {"issueId": issue_id, "body": body}})
        return data["commentCreate"]["comment"]


# ── State file management ───────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))
