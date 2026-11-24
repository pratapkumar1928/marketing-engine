"""Push the ledger to the repo mid-run (CI only), so no later run can miss a post that is about to happen."""
import os
import subprocess
from pathlib import Path

ATTEMPTS = 3


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def checkpoint(root: Path) -> None:
    """Commit state/ and push. Raises RuntimeError if the ledger could not reach the remote."""
    root = Path(root)
    _git(root, "add", "state")
    if _git(root, "diff", "--cached", "--quiet").returncode == 0:
        return
    if _git(root, "commit", "-q", "-m", "ledger: publishing").returncode != 0:
        raise RuntimeError("ledger commit failed")
    branch = os.environ.get("LEDGER_BRANCH") or _git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    for _ in range(ATTEMPTS):  # another run may have pushed meanwhile: rebase (ledger merges by union) and retry
        if _git(root, "push", "-q", "origin", f"HEAD:{branch}").returncode == 0:
            return
        if _git(root, "pull", "-q", "--rebase", "origin", branch).returncode != 0:
            _git(root, "rebase", "--abort")
            break
    raise RuntimeError("ledger push failed")
