#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""``mas-lab config`` — show effective runtime configuration and data paths."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import click

from mas.lab import paths as _paths


def _lab_output_label(lab_output: Path, slug: str) -> str:
    """Return a compact label ``{slug}#{hash8}`` for a lab output path.

    *slug* is either ``lab.name`` from lab-config.yaml (stable across renames)
    or the ``.lab`` directory name.  The 8-char sha256 prefix makes paths
    unique even when multiple labs share the same slug.
    """
    h8 = hashlib.sha256(str(lab_output).encode()).hexdigest()[:8]
    return f"{slug}#{h8}"


def _find_lab_config(start: Path) -> Path | None:
    """Walk up from *start* looking for lab-config.yaml."""
    for directory in [start, *start.parents]:
        candidate = directory / "lab-config.yaml"
        if candidate.exists():
            return candidate
    return None


def _resolve_lab_output() -> Path:
    return _paths.lab_output()


@click.command("config")
@click.option(
    "--json", "as_json",
    is_flag=True, default=False,
    help="Output as JSON instead of human-readable text.",
)
def config_cmd(as_json: bool) -> None:
    """Show effective mas-lab configuration and data paths.

    Displays where benchmark runs, lab output, and traces are stored, which
    lab-config.yaml is active, and which environment variables override defaults.
    """
    cwd = Path.cwd().resolve()

    summary = _paths.path_resolution_summary()
    labs_root = summary["labs_dir"].path
    data_dir = summary["data_dir"].path
    trace_cache_path = summary["trace_cache"].path
    lab_output = _resolve_lab_output()
    lout_source_override: str | None = None
    lab_slug: str | None = None
    lab_config_path = _find_lab_config(cwd)

    # When a lab-config.yaml is found and no env var overrides the output path,
    # use the lab's own output_dir (relative to the lab-config.yaml location).
    if lab_config_path:
        try:
            import yaml as _yaml
            _lab_cfg = _yaml.safe_load(lab_config_path.read_text())
            lab_section = _lab_cfg.get("lab", {})
            # Preferred stable slug: lab.name from YAML (survives file renames).
            # Fallback: parent directory name (strips .lab suffix for brevity).
            _raw_slug = lab_section.get("name") or lab_config_path.parent.name
            lab_slug = _raw_slug.removesuffix(".lab")
            if lab_section.get("output_dir"):
                lab_output = (lab_config_path.parent / lab_section["output_dir"]).resolve()
                lout_source_override = "lab-config.yaml"
        except Exception:
            pass  # fall back to global default

    # Workspace config
    workspace_config_path: Path | None = None
    try:
        from mas.runtime.workspace_config import find_workspace_file

        found = find_workspace_file(cwd)
        if found:
            workspace_config_path = found.resolve()
    except ImportError:
        try:
            from mas.lab.workspace import _find_config
            found = _find_config(cwd)
            if found:
                workspace_config_path = found.resolve()
        except (ImportError, Exception):
            pass

    if as_json:
        import json as _json
        data = {
            "cwd": str(cwd),
            "data_root": {
                "path": str(summary["data_root"].path),
                "source": summary["data_root"].source,
            },
            "labs_root": {
                "path": str(labs_root),
                "source": summary["labs_dir"].source,
            },
            "data_dir": {
                "path": str(data_dir),
                "source": summary["data_dir"].source,
            },
            "trace_cache": {
                "path": str(trace_cache_path),
                "source": summary["trace_cache"].source,
            },
            "runs_root": {
                "path": str(summary["runs_dir"].path),
                "source": summary["runs_dir"].source,
            },
            "lab_output": {
                "path": str(lab_output),
                "label": _lab_output_label(lab_output, lab_slug or lab_output.parent.name),
                "source": "lab-config.yaml" if lout_source_override == "lab-config.yaml" else "default",
            },
            "lab_config": str(lab_config_path) if lab_config_path else None,
            "workspace_config": str(workspace_config_path) if workspace_config_path else None,
        }
        click.echo(_json.dumps(data, indent=2))
        return

    # Human-readable output
    def _tag(source: str) -> str:
        return click.style(f"[{source}]", fg="yellow") if source != "default" else click.style("[default]", dim=True)

    click.echo()
    click.echo(click.style("mas-lab configuration", bold=True))
    click.echo(click.style("─" * 50, dim=True))

    click.echo(f"\n  {'cwd':<22} {cwd}")

    _data_root = summary["data_root"].path
    _droot_source = summary["data_root"].source
    click.echo(f"\n  {'data root':<22} {_data_root}  {_tag(_droot_source)}")

    lroot_source = summary["labs_dir"].source
    click.echo(f"\n  {'labs root':<22} {labs_root}  {_tag(lroot_source)}")
    click.echo(f"  {'  (experiments)':<22} {click.style('<labs_root>/<experiment>/ or flat metadata.yaml', dim=True)}")
    click.echo(f"  {'  exists':<22} {click.style('yes', fg='green') if labs_root.exists() else click.style('no (will be created on first run)', fg='yellow')}")

    ddir_source = summary["data_dir"].source
    click.echo(f"\n  {'data dir':<22} {data_dir}  {_tag(ddir_source)}")
    click.echo(f"  {'  (scratch)':<22} {click.style('<data_dir>/lab-output/, standalone-runs/', dim=True)}")

    tc_source = summary["trace_cache"].source
    click.echo(f"\n  {'trace cache':<22} {trace_cache_path}  {_tag(tc_source)}")
    click.echo(f"  {'  exists':<22} {click.style('yes', fg='green') if trace_cache_path.exists() else click.style('no (will be created on first run)', fg='yellow')}")

    runs_source = summary["runs_dir"].source
    click.echo(f"\n  {'runs root':<22} {summary['runs_dir'].path}  {_tag(runs_source)}")

    lout_source = "lab-config.yaml" if lout_source_override == "lab-config.yaml" else "default"
    _lout_label = _lab_output_label(lab_output, lab_slug or lab_output.parent.name)
    click.echo(f"\n  {'lab output':<22} {click.style(_lout_label, bold=True)}  {_tag(lout_source)}")
    click.echo(f"  {'  path':<22} {click.style(str(lab_output), dim=True)}")
    click.echo(f"  {'  exists':<22} {click.style('yes', fg='green') if lab_output.exists() else click.style('no (will be created on first run)', fg='yellow')}")

    click.echo()
    if lab_config_path:
        click.echo(f"  {'lab-config.yaml':<22} {click.style(str(lab_config_path), fg='green')}")
        # Show lab name + scenarios count
        try:
            import yaml
            raw = yaml.safe_load(lab_config_path.read_text())
            lab_section = raw.get("lab", {})
            name = lab_section.get("name", "?")
            scenarios = lab_section.get("scenarios", [])
            click.echo(f"  {'  name':<22} {name}")
            click.echo(f"  {'  scenarios':<22} {len(scenarios)}")
        except Exception:
            pass
    else:
        click.echo(f"  {'lab-config.yaml':<22} {click.style('not found (searched from cwd upward)', dim=True)}")

    click.echo()
    if workspace_config_path:
        click.echo(f"  {'workspace config':<22} {click.style(str(workspace_config_path), fg='green')}")
    else:
        click.echo(f"  {'workspace config':<22} {click.style('not found (using XDG defaults)', dim=True)}")

    click.echo()
