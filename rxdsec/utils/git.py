"""Git utilities for RxDsec"""

import subprocess
import tempfile
import os
from pathlib import Path
from typing import List, NamedTuple

class WorktreeInfo(NamedTuple):
    id: str
    path: Path
    status: str

def create_worktree(task_slug: str) -> Path:
    """Create an isolated worktree for a task using git worktree"""
    # Create a branch name for this task
    branch_name = f"rxdsec-{task_slug}"
    # Create a directory for the worktree
    worktree_dir = Path.home() / ".rxdsec" / "worktrees" / task_slug
    worktree_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Create and checkout a new branch for this task
        # First, check if branch already exists
        result = subprocess.run(
            ["git", "rev-parse", "--verify", branch_name],
            cwd=Path.cwd(),
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            # Branch doesn't exist, create it
            subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=Path.cwd(),
                check=True,
                capture_output=True
            )
        else:
            # Branch exists, just checkout
            subprocess.run(
                ["git", "checkout", branch_name],
                cwd=Path.cwd(),
                check=True,
                capture_output=True
            )

        # Now create the actual worktree
        subprocess.run(
            ["git", "worktree", "add", str(worktree_dir), branch_name],
            cwd=Path.cwd(),
            check=True,
            capture_output=True
        )

        return worktree_dir

    except subprocess.CalledProcessError as e:
        # If worktree creation fails, clean up and raise
        if worktree_dir.exists():
            import shutil
            shutil.rmtree(worktree_dir, ignore_errors=True)
        raise e

def list_worktrees() -> List[WorktreeInfo]:
    """List all active worktrees"""
    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path.cwd()
        )

        worktrees = []
        worktree_info = {}

        # Parse the porcelain output
        for line in result.stdout.strip().split('\n'):
            if line.startswith('worktree '):
                path = Path(line.split(' ', 1)[1])
            elif line.startswith('HEAD '):
                head = line.split(' ', 1)[1][:8]  # Short hash
            elif line.startswith('branch '):
                branch = line.split(' ', 1)[1].split('/')[-1]  # Get branch name
                worktrees.append(WorktreeInfo(
                    id=branch.replace("rxdsec-", "") if "rxdsec-" in branch else branch,
                    path=path,
                    status="active"  # All listed worktrees are active
                ))
            elif line == "":  # Empty line separates entries
                continue

        return worktrees
    except subprocess.CalledProcessError:
        # If porcelain format isn't supported, try basic format
        try:
            result = subprocess.run(
                ["git", "worktree", "list"],
                capture_output=True,
                text=True,
                check=True,
                cwd=Path.cwd()
            )

            worktrees = []
            for line in result.stdout.strip().split('\n'):
                if line.strip() and not line.startswith('Preparing '):
                    parts = line.split()
                    if len(parts) >= 2:
                        path = Path(parts[0])
                        branch = parts[1].strip('()')  # Remove parentheses
                        status = "active" if line.startswith('*') else "locked" if '(locked)' in line else "inactive"
                        worktrees.append(WorktreeInfo(
                            id=branch.replace("rxdsec-", "") if "rxdsec-" in branch else branch,
                            path=path,
                            status=status
                        ))

            return worktrees
        except subprocess.CalledProcessError:
            # Git command failed, return empty list
            return []

def delete_worktree(id_or_path: str) -> bool:
    """Delete a worktree by its ID or path"""
    try:
        # If id_or_path is a path, convert to the worktree directory name
        worktree_path = Path(id_or_path)
        if worktree_path.exists():
            # Remove the git worktree reference
            subprocess.run(
                ["git", "worktree", "remove", str(worktree_path)],
                cwd=Path.cwd(),
                check=True,
                capture_output=True
            )
        else:
            # Assume it's a branch name, construct the path
            worktree_dir = Path.home() / ".rxdsec" / "worktrees" / id_or_path
            if worktree_dir.exists():
                subprocess.run(
                    ["git", "worktree", "remove", str(worktree_dir)],
                    cwd=Path.cwd(),
                    check=True,
                    capture_output=True
                )

        # Remove the local directory
        worktree_dir = Path.home() / ".rxdsec" / "worktrees" / id_or_path
        if worktree_dir.exists():
            import shutil
            shutil.rmtree(worktree_dir, ignore_errors=True)

        # Also try to delete the branch
        try:
            subprocess.run(
                ["git", "branch", "-D", f"rxdsec-{id_or_path}"],
                cwd=Path.cwd(),
                capture_output=True  # Don't check, branch might be checked out elsewhere
            )
        except:
            pass  # Ignore errors when deleting branch

        return True
    except subprocess.CalledProcessError:
        return False

def attach_worktree(id_or_path: str) -> Path:
    """Attach to an existing worktree by changing to its directory"""
    worktree_dir = Path.home() / ".rxdsec" / "worktrees" / id_or_path

    if not worktree_dir.exists():
        raise ValueError(f"Worktree {id_or_path} does not exist")

    # Change to the worktree directory
    os.chdir(worktree_dir)
    return worktree_dir