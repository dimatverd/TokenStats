"""Configuration for Linear sync tools."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

LINEAR_API_KEY = os.getenv("LINEAR_API_KEY", "")
LINEAR_API_URL = "https://api.linear.app/graphql"

PROJECT_ROOT = Path(__file__).parent.parent
DOCS_DIR = PROJECT_ROOT / "docs"
USER_STORIES_PATH = DOCS_DIR / "product" / "user-stories-mvp.md"
TEST_STRATEGY_PATH = DOCS_DIR / "qa" / "test-strategy.md"
STATE_FILE = PROJECT_ROOT / ".linear_state.json"

TEAM_NAME = "TokenStats"
TEAM_KEY = "TS"
PROJECT_NAME = "TokenStats MVP"
