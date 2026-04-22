"""Script to replace datetime.utcnow() with utc_now() across the codebase."""

import ast
import sys
from pathlib import Path

REPO_ROOT = Path("/Users/peter/development/partymap-bot/apps/api/src")

# Files that should NOT be modified
SKIP_FILES = {
    REPO_ROOT / "utils" / "utc_now.py",
}


def has_datetime_import(content: str) -> bool:
    """Check if file imports datetime."""
    return "datetime" in content


def add_utc_now_import(content: str) -> str:
    """Add utc_now import after any existing from-datetime import, or at top."""
    lines = content.splitlines()
    import_line = "from src.utils.utc_now import utc_now"

    # Check if already imported
    if import_line in content:
        return content

    # Find best insertion point (after other src.utils imports, or after datetime import)
    insert_idx = 0
    for i, line in enumerate(lines):
        if line.startswith("from datetime") or line.startswith("import datetime"):
            insert_idx = i + 1
        elif line.startswith("from src.utils"):
            insert_idx = i + 1
        elif line.startswith("from ") and insert_idx == 0:
            insert_idx = i + 1

    lines.insert(insert_idx, import_line)
    return "\n".join(lines)


def replace_in_content(content: str) -> str:
    """Replace datetime.utcnow() patterns with utc_now()."""
    # Replace function reference defaults: default=datetime.utcnow
    content = content.replace("default=datetime.utcnow", "default=utc_now")
    content = content.replace("onupdate=datetime.utcnow", "onupdate=utc_now")
    content = content.replace("default_factory=datetime.utcnow", "default_factory=utc_now")

    # Replace lambda defaults
    content = content.replace("lambda: datetime.utcnow()", "utc_now")

    # Replace direct calls
    content = content.replace("datetime.utcnow()", "utc_now()")

    return content


def process_file(filepath: Path) -> bool:
    """Process a single file. Returns True if modified."""
    if filepath in SKIP_FILES:
        return False

    content = filepath.read_text()
    if not has_datetime_import(content):
        return False

    # Skip files that don't use utcnow
    if "utcnow" not in content:
        return False

    new_content = replace_in_content(content)
    if new_content == content:
        return False

    new_content = add_utc_now_import(new_content)
    filepath.write_text(new_content)
    return True


def main():
    modified = []
    for pyfile in REPO_ROOT.rglob("*.py"):
        if process_file(pyfile):
            modified.append(str(pyfile.relative_to(REPO_ROOT)))

    print(f"Modified {len(modified)} files:")
    for f in modified:
        print(f"  - {f}")


if __name__ == "__main__":
    main()
