#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""mas-ctl infra / flavour — list bundles from installed manifest libraries."""

from __future__ import annotations

import click

from mas.ctl.libraries.bundles import list_bundles, list_manifest_libraries


@click.group()
def infra_group() -> None:
    """Infrastructure bundle discovery."""


@infra_group.command("list")
@click.option("-v", "--verbose", is_flag=True)
def infra_list(verbose: bool) -> None:
    """List infra bundles (alias: mas-ctl list-bundles)."""
    libs = list_manifest_libraries()
    if not libs:
        click.echo("No manifest libraries. Run: task install-all")
        return
    bundles = list_bundles(verbose=verbose)
    for b in bundles:
        if b.kind and "Infra" in b.kind or b.kind in ("LLMProxy", "ToolRegistry", "InfraBundle"):
            click.echo(f"{b.ref}  kind={b.kind}  {b.name}")


@click.group()
def flavour_group() -> None:
    """Flavour manifests (deprecated — prefer deployment/v1)."""


@flavour_group.command("list")
def flavour_list() -> None:
    """List flavour YAML files from installed libraries."""
    try:
        from importlib.resources import as_file, files
    except ImportError:
        click.echo("No flavours (importlib.resources unavailable)")
        return
    found = False
    for lib_name, pkg in list_manifest_libraries().items():
        try:
            path = files(pkg) / "flavours"
            with as_file(path) as p:
                if not p.is_dir():
                    continue
                for yaml_file in sorted(p.glob("*.yaml")):
                    found = True
                    click.echo(f"{lib_name}:{yaml_file.stem}")
        except Exception:
            continue
    if not found:
        click.echo("No flavours found. Run: task install-all")
