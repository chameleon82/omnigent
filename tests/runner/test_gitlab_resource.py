"""GitLab merge-request resource behavior."""

from __future__ import annotations

import json

import pytest

from omnigent.runner import gitlab_resource

_URL = "https://gitlab.example/group/subgroup/project/-/merge_requests/42"


def test_info_returns_structured_glab_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        gitlab_resource.shutil, "which", lambda name: "/usr/bin/glab" if name == "glab" else None
    )
    calls: list[list[str]] = []

    def fake_run(argv: list[str], *, root: str):
        calls.append(argv)
        return 0, json.dumps({"iid": 42, "web_url": _URL, "title": "MR"}), ""

    monkeypatch.setattr(gitlab_resource, "_run", fake_run)
    result = gitlab_resource.gitlab_info("/workspace", pr_url=_URL)

    assert result["object"] == "session.gitlab.info"
    assert result["available"] is True
    assert result["selected_mr_url"] == _URL
    assert result["merge_request"]["iid"] == 42
    assert calls == [
        [
            "glab",
            "--hostname",
            "gitlab.example",
            "mr",
            "view",
            "42",
            "--output",
            "json",
            "-R",
            "group/subgroup/project",
        ]
    ]


def test_diff_returns_empty_when_glab_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gitlab_resource.shutil, "which", lambda name: None)
    assert gitlab_resource.gitlab_mr_diff("/workspace", pr_url=_URL) == {
        "object": "session.gitlab.mr_diff",
        "patch": "",
    }


def test_resource_rejects_github_url() -> None:
    with pytest.raises(ValueError, match="GitLab merge request"):
        gitlab_resource.gitlab_info("/workspace", pr_url="https://github.com/example/repo/pull/42")
