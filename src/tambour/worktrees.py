"""Worktree listing and management for tambour.

Lists git worktrees with tambour-specific metadata (heartbeat status,
issue association, health).
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class WorktreeInfo:
    """Information about a single git worktree."""

    path: Path
    head: str
    branch: str | None  # None for detached HEAD
    is_bare: bool
    heartbeat_age: float | None  # seconds since last heartbeat, or None
    heartbeat_pid: int | None  # PID from heartbeat file, or None

    @property
    def name(self) -> str:
        """Short name for the worktree (last path component)."""
        return self.path.name

    @property
    def short_head(self) -> str:
        """Short (7-char) commit hash."""
        return self.head[:7] if self.head else ""

    @property
    def short_branch(self) -> str:
        """Branch name without refs/heads/ prefix."""
        if self.branch and self.branch.startswith("refs/heads/"):
            return self.branch[len("refs/heads/"):]
        return self.branch or "(detached)"

    @property
    def is_alive(self) -> bool:
        """Whether the worktree has a recent heartbeat (< 5 min)."""
        if self.heartbeat_age is None:
            return False
        return self.heartbeat_age < 300

    @property
    def status_indicator(self) -> str:
        """Status indicator character."""
        if self.is_bare:
            return " "
        if self.heartbeat_age is None:
            return "-"  # no heartbeat
        if self.is_alive:
            return "*"  # active
        return "!"  # stale heartbeat (possible zombie)


def _parse_porcelain(output: str) -> list[WorktreeInfo]:
    """Parse `git worktree list --porcelain` output.

    Args:
        output: Raw porcelain output from git.

    Returns:
        List of WorktreeInfo objects.
    """
    worktrees: list[WorktreeInfo] = []
    current: dict[str, str] = {}

    for line in output.splitlines():
        if not line:
            # Empty line separates worktree entries
            if current:
                worktrees.append(_build_worktree_info(current))
                current = {}
            continue

        if line.startswith("worktree "):
            current["path"] = line[len("worktree "):]
        elif line.startswith("HEAD "):
            current["head"] = line[len("HEAD "):]
        elif line.startswith("branch "):
            current["branch"] = line[len("branch "):]
        elif line == "bare":
            current["bare"] = "true"
        elif line == "detached":
            current["detached"] = "true"

    # Handle last entry (no trailing blank line)
    if current:
        worktrees.append(_build_worktree_info(current))

    return worktrees


def _build_worktree_info(data: dict[str, str]) -> WorktreeInfo:
    """Build a WorktreeInfo from parsed porcelain data."""
    path = Path(data.get("path", ""))
    heartbeat_age, heartbeat_pid = _read_heartbeat(path)

    return WorktreeInfo(
        path=path,
        head=data.get("head", ""),
        branch=data.get("branch"),
        is_bare="bare" in data,
        heartbeat_age=heartbeat_age,
        heartbeat_pid=heartbeat_pid,
    )


def _read_heartbeat(worktree_path: Path) -> tuple[float | None, int | None]:
    """Read heartbeat file from a worktree.

    Args:
        worktree_path: Path to the worktree.

    Returns:
        Tuple of (age_in_seconds, pid) or (None, None) if no heartbeat.
    """
    heartbeat_file = worktree_path / ".tambour" / "heartbeat"
    if not heartbeat_file.exists():
        return None, None

    try:
        data = json.loads(heartbeat_file.read_text())
        timestamp_str = data.get("timestamp")
        pid = data.get("pid")

        age = None
        if timestamp_str:
            last_activity = datetime.fromisoformat(
                timestamp_str.replace("Z", "+00:00")
            )
            age = (datetime.now(timezone.utc) - last_activity).total_seconds()

        return age, int(pid) if pid is not None else None
    except (json.JSONDecodeError, ValueError, OSError):
        return None, None


def list_worktrees() -> list[WorktreeInfo]:
    """List all git worktrees with tambour metadata.

    Returns:
        List of WorktreeInfo objects.

    Raises:
        subprocess.CalledProcessError: If git command fails.
    """
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    return _parse_porcelain(result.stdout)


def _format_age(seconds: float | None) -> str:
    """Format age in seconds to human-readable string."""
    if seconds is None:
        return ""
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds / 60)}m"
    if seconds < 86400:
        return f"{int(seconds / 3600)}h"
    return f"{int(seconds / 86400)}d"


def format_worktrees(worktrees: list[WorktreeInfo]) -> str:
    """Format worktree list for terminal output.

    Args:
        worktrees: List of WorktreeInfo objects.

    Returns:
        Formatted string for display.
    """
    if not worktrees:
        return "No worktrees found."

    lines: list[str] = []
    for wt in worktrees:
        if wt.is_bare:
            lines.append(f"  {wt.path}  (bare)")
            continue

        status = wt.status_indicator
        branch = wt.short_branch
        head = wt.short_head

        heartbeat_info = ""
        if wt.heartbeat_age is not None:
            age_str = _format_age(wt.heartbeat_age)
            pid_str = f" pid:{wt.heartbeat_pid}" if wt.heartbeat_pid else ""
            heartbeat_info = f"  [{age_str} ago{pid_str}]"

        lines.append(f"{status} {wt.path}  {head} {branch}{heartbeat_info}")

    return "\n".join(lines)
