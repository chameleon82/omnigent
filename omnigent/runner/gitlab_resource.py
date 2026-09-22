"""Session GitLab merge-request resources backed by the ``glab`` CLI."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any

from omnigent.runner.session_prs import PullRequestRef, SessionPrRegistry
from omnigent.runtime.filesystem_registry import _git_timeout_seconds


def _run(argv: list[str], *, root: str) -> tuple[int | None, str, str]:
    try:
        completed = subprocess.run(
            argv, cwd=root, capture_output=True, timeout=_git_timeout_seconds()
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, "", str(exc)
    return (
        completed.returncode,
        completed.stdout.decode("utf-8", errors="replace"),
        completed.stderr.decode("utf-8", errors="replace"),
    )


def _reference(pr_url: str) -> PullRequestRef:
    reference = PullRequestRef.from_url(pr_url)
    if reference.provider != "gitlab":
        raise ValueError("Expected a GitLab merge request URL")
    return reference


def _selected(session_id: str | None, pr_url: str | None) -> PullRequestRef | None:
    if pr_url:
        return _reference(pr_url)
    if not session_id:
        return None
    return next(
        (entry for entry in SessionPrRegistry(session_id).list() if entry.provider == "gitlab"),
        None,
    )


def _glab_args(reference: PullRequestRef, *args: str) -> list[str]:
    return ["glab", "--hostname", reference.host, "mr", *args, "-R", reference.repository]


def gitlab_info(
    root: str, *, session_id: str | None = None, pr_url: str | None = None
) -> dict[str, Any]:
    """Return selected GitLab MR details or a structured unavailable response."""
    reference = _selected(session_id, pr_url)
    if reference is None:
        return {"object": "session.gitlab.info", "available": False, "reason": "no_merge_request"}
    if shutil.which("glab") is None:
        return {
            "object": "session.gitlab.info",
            "available": False,
            "reason": "glab_not_installed",
        }
    rc, output, error = _run(
        _glab_args(reference, "view", str(reference.number), "--output", "json"), root=root
    )
    if rc != 0:
        return {
            "object": "session.gitlab.info",
            "available": False,
            "reason": "unavailable",
            "message": error.strip() or "GitLab could not load the merge request.",
        }
    try:
        mr = json.loads(output)
    except ValueError:
        return {"object": "session.gitlab.info", "available": False, "reason": "invalid_response"}
    if not isinstance(mr, dict):
        return {"object": "session.gitlab.info", "available": False, "reason": "invalid_response"}
    return {
        "object": "session.gitlab.info",
        "available": True,
        "provider": "gitlab",
        "selected_mr_url": reference.url,
        "merge_request": mr,
        "tracked_merge_requests": [
            entry.model_dump() for entry in SessionPrRegistry(session_id).list()
        ]
        if session_id
        else [],
    }


def gitlab_mr_diff(
    root: str, *, session_id: str | None = None, pr_url: str | None = None
) -> dict[str, str]:
    """Return the server-computed GitLab MR patch for the selected association."""
    reference = _selected(session_id, pr_url)
    if reference is None or shutil.which("glab") is None:
        return {"object": "session.gitlab.mr_diff", "patch": ""}
    rc, output, _ = _run(_glab_args(reference, "diff", str(reference.number)), root=root)
    return {"object": "session.gitlab.mr_diff", "patch": output if rc == 0 else ""}


def update_session_mr(session_id: str, *, url: str, action: str = "attach") -> dict[str, object]:
    """Attach or unlink a GitLab MR from the session's durable association list."""
    reference = _reference(url)
    registry = SessionPrRegistry(session_id)
    if action == "detach":
        registry.remove(reference.url)
    elif action == "attach":
        registry.record([reference], relationship="attached", source="resource")
    else:
        raise ValueError("Expected action 'attach' or 'detach'")
    return {
        "object": "session.gitlab.mr_association",
        "url": reference.url,
        "action": action,
        "tracked_merge_requests": [entry.model_dump() for entry in registry.list()],
    }
