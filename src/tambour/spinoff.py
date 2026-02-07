"""Spinoff command for tambour.

Create follow-up issues from within an agent session, automatically
linking them to the current work item.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field


@dataclass
class SpinoffResult:
    """Result of a spinoff operation."""

    success: bool
    issue_id: str | None = None
    title: str = ""
    error: str | None = None


@dataclass
class SpinoffCommand:
    """Create a follow-up issue linked to the current work."""

    title: str
    description: str | None = None
    issue_type: str = "task"
    priority: str | None = None
    labels: list[str] = field(default_factory=list)
    parent_issue: str | None = None
    blocks_current: bool = False
    current_issue: str | None = None

    def _resolve_current_issue(self) -> str | None:
        """Determine the current issue ID from args or environment."""
        if self.current_issue:
            return self.current_issue
        return os.environ.get("TAMBOUR_ISSUE_ID")

    def run(self) -> SpinoffResult:
        """Execute the spinoff: create a new issue linked to current work.

        Returns:
            SpinoffResult with the outcome.
        """
        if not self.title:
            return SpinoffResult(
                success=False,
                error="Title is required",
            )

        current = self._resolve_current_issue()

        cmd: list[str] = [
            "bd", "create",
            self.title,
            "--type", self.issue_type,
            "--silent",
        ]

        if self.description:
            cmd.extend(["--description", self.description])

        if self.priority:
            cmd.extend(["--priority", self.priority])

        for label in self.labels:
            cmd.extend(["--labels", label])

        if self.parent_issue:
            cmd.extend(["--parent", self.parent_issue])

        # Link to current issue
        deps: list[str] = []
        if current:
            deps.append(f"discovered-from:{current}")
            if self.blocks_current:
                deps.append(f"blocks:{current}")

        if deps:
            cmd.extend(["--deps", ",".join(deps)])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            return SpinoffResult(
                success=False,
                error="'bd' command not found. Is beads installed?",
            )

        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip() or "Unknown error"
            return SpinoffResult(
                success=False,
                error=f"Failed to create issue: {error_msg}",
            )

        new_id = result.stdout.strip()
        if not new_id:
            return SpinoffResult(
                success=False,
                error="bd create succeeded but returned no issue ID",
            )

        return SpinoffResult(
            success=True,
            issue_id=new_id,
            title=self.title,
        )


def cmd_spinoff(args) -> int:
    """Handle 'spinoff' command.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    spinoff = SpinoffCommand(
        title=args.title,
        description=args.description,
        issue_type=args.type,
        priority=args.priority,
        labels=args.labels or [],
        parent_issue=args.parent,
        blocks_current=args.blocks_current,
        current_issue=args.issue,
    )

    result = spinoff.run()

    if not result.success:
        print(f"Error: {result.error}", file=sys.stderr)
        return 1

    current = spinoff._resolve_current_issue()
    print(f"Created {result.issue_id}: {result.title}")
    if current:
        links = ["discovered-from"]
        if args.blocks_current:
            links.append("blocks")
        print(f"  Linked to {current} ({', '.join(links)})")

    return 0
