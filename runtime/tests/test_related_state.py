#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from pathlib import Path
from types import SimpleNamespace

from mas.ctl.session.controller import SessionController
from mas.ctl.session.manager import SessionManager
from mas.library.standard.plugins.related_state.copy_dir import CopyDirRelatedState
from mas.library.standard.plugins.related_state.git_worktree import GitWorktreeRelatedState
from mas.runtime.driver.mocks import AutoCtxAssembler
from mas.runtime.session.snapshot import SnapshotTree


def _session_with_related(tmp_path: Path, plugin) -> tuple:
    manager = SessionManager(snapshot_tree=SnapshotTree())
    ctx = AutoCtxAssembler()
    instance = SimpleNamespace(
        snapshot=lambda: {"q": {}, "run": {}},
        load_checkpoint=lambda data: None,
        pause=lambda **kw: None,
        resume=lambda: None,
        driver=SimpleNamespace(ctx=ctx),
        feed=lambda event: SimpleNamespace(client_responses=[], hitl_requests=[], boundary_errors=[]),
    )

    class _Display:
        def on_system(self, *_a, **_k):
            return None

        def on_user(self, *_a, **_k):
            return None

    controller = SessionController(instance=instance, display=_Display())
    session = manager.create(instance, controller, {"name": "agent", "spec": {}}, session_id="s1")
    session.related_state = [plugin]
    return manager, session


def test_copy_dir_related_state_roundtrip(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    (root / "a.txt").write_text("one")
    plugin = CopyDirRelatedState(root, tmp_path / "cache")
    manager, session = _session_with_related(tmp_path, plugin)
    snap = session.take_snapshot(label="n0")
    assert snap.related
    assert snap.related[0].plugin == "copy_dir"
    (root / "a.txt").write_text("two")
    session.restore_snapshot(snap)
    assert (root / "a.txt").read_text() == "one"
    tree = SnapshotTree.from_events(session.lineage_events)
    assert tree.live("s1") is not None
    assert tree.live("s1").snapshot_id == snap.ref.snapshot_id


def test_git_worktree_related_state_does_not_move_head(tmp_path: Path) -> None:
    import subprocess

    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    (root / "f.txt").write_text("alpha")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=augjorda@cisco.com",
            "-c",
            "user.name=Jordan Auge",
            "commit",
            "-m",
            "init",
        ],
        cwd=root,
        check=True,
        capture_output=True,
    )
    head_before = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    plugin = GitWorktreeRelatedState(root)
    manager, session = _session_with_related(tmp_path, plugin)
    snap = session.take_snapshot(label="n0")
    (root / "f.txt").write_text("beta")
    session.restore_snapshot(snap)
    assert (root / "f.txt").read_text() == "alpha"
    head_after = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    assert head_after == head_before
    assert snap.related[0].adapter == "git"
    _ = manager
