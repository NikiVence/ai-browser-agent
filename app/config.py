import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

USER_DATA_DIR = REPO_ROOT / ".pw-user-data"

SCREENSHOT_DIR = REPO_ROOT / ".agent-screenshots"

MAX_AGENT_STEPS = 40

VISION_MAX_IMAGES_PER_STEP = int(os.getenv("VISION_MAX_IMAGES_PER_STEP", "4"))

PAGE_ARIA_DEPTH = 12

MAX_ARIA_SNAPSHOT_CHARS = 14_000

MAX_BODY_FALLBACK_CHARS = 2_500

ARIA_SNAPSHOT_TIMEOUT_MS = int(os.getenv("ARIA_SNAPSHOT_TIMEOUT_MS", "45000"))

BODY_INNER_TEXT_TIMEOUT_MS = int(os.getenv("BODY_INNER_TEXT_TIMEOUT_MS", "8000"))


def load_strict_root_only_hosts():

    raw = (os.environ.get("BROWSER_STRICT_ROOT_ONLY_HOSTS") or "").strip()

    if not raw:

        return frozenset()

    return frozenset(
        part.strip().lower()
        for part in raw.split(",")
        if part.strip()
    )


STRICT_ROOT_ONLY_HOSTS = load_strict_root_only_hosts()
