"""Initialize tambour in a project directory.

Creates .tambour/config.toml with sensible defaults.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

DEFAULT_CONFIG = """\
[tambour]
version = "1"

[agent]
default_cli = "claude"

[daemon]
health_interval = 60
zombie_threshold = 300
auto_recover = false

[worktree]
base_path = "../{repo}-worktrees"
"""


def _is_git_repo(directory: Path) -> bool:
    """Check if the directory is inside a git repository."""
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        cwd=directory,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def _get_git_root(directory: Path) -> Path | None:
    """Get the root of the git repository containing directory."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        cwd=directory,
    )
    if result.returncode == 0:
        return Path(result.stdout.strip())
    return None


def init_tambour(
    directory: Path | None = None,
    force: bool = False,
) -> tuple[bool, str]:
    """Initialize tambour in the given directory.

    Creates .tambour/config.toml with default configuration.

    Args:
        directory: Directory to initialize in. Defaults to current directory.
        force: Overwrite existing config if present.

    Returns:
        Tuple of (success, message).
    """
    if directory is None:
        directory = Path.cwd()

    directory = directory.resolve()

    if not directory.is_dir():
        return False, f"Not a directory: {directory}"

    if not _is_git_repo(directory):
        return False, f"Not a git repository: {directory}"

    git_root = _get_git_root(directory)
    if git_root is None:
        return False, "Could not determine git root"

    tambour_dir = git_root / ".tambour"
    config_path = tambour_dir / "config.toml"

    if config_path.exists() and not force:
        return False, f"Already initialized: {config_path} (use --force to overwrite)"

    tambour_dir.mkdir(parents=True, exist_ok=True)
    config_path.write_text(DEFAULT_CONFIG)

    return True, f"Initialized tambour in {tambour_dir}"
