# MAS-Lab Release Process

This document describes the repeatable release sequence for MAS-Lab, including
one-time public PyPI setup and the steps repeated for each release.

## Release model

PyPI publication is integrated before a release branch is cut. The order is:

1. Merge the PyPI publication feature into `main`.
2. Configure public PyPI Trusted Publishers for the distributions listed below.
3. Rebase or create `release/vX.Y` from the updated `main`.
4. Set all first-party package versions to `X.Y.0` and regenerate `uv.lock`.
5. Update `CHANGELOG.md`, `RELEASE-NOTES.md`, and the release blog post.
6. Run package builds, documentation checks, unit/functional gates, and protocol
   compliance checks.
7. Push the release branch and open a PR or draft PR so GitHub Actions runs on the
   exact release candidate.
8. Merge the release branch and create the annotated `vX.Y.0` tag. The tag
  workflow builds, tests, and publishes packages to PyPI once Trusted
  Publishers are configured.

The PyPI feature branch must be based on `main`, not on a release branch. The
release branch is the branch that receives the version bump and release-specific
notes after the publication support is merged.

## One-time public PyPI setup

The publication workflow targets only the public PyPI upload service through
`pypa/gh-action-pypi-publish@release/v1`. It does not publish to GitHub Packages
or to a Cisco-internal package index.

### GitHub setup

Create a GitHub Actions environment named `pypi` in
`outshift-open/mas-lab`. Add required reviewers to this environment if package
publication must be manually approved. The workflow grants `id-token: write`
only to the publication job.

### PyPI setup

For each distribution, configure a PyPI Trusted Publisher with:

- owner: `outshift-open`
- repository: `mas-lab`
- workflow: `.github/workflows/publish.yml`
- environment: `pypi`

Trusted Publishers can be configured as pending publishers before the first
upload. No long-lived PyPI API token is required, and no GPG signing key is
required for the upload. PyPI's attestations/provenance features can be enabled
separately if required by the release policy.

The current public distribution set is:

- `mas-runtime`
- `mas-ctl`
- `mas-lab`
- `mas-lab-core`
- `mas-lab-bench`
- `mas-lab-controller`
- `mas-library-standard`
- `mas-library-skills`
- `mas-library-samples`
- `mas-library-lab`
- `mas-library-eval`
- `mas-library-ioa`

The workspace metapackage is not part of the publication matrix. The MCP and
A2A compliance directories under `library-ioa/compliance/` are CI/test assets,
not user-facing distributions, and are never uploaded to PyPI.

## Repeated pre-release checks

Run from the repository root with the feature or release branch's `.venv`:

```bash
uv lock --check
python3 scripts/version_manager.py check
python3 scripts/gen_docs.py --check
git diff --check
```

Build every matrix package from sdist to wheel. This catches packages whose
wheel configuration depends on files that are absent from the source archive:

```bash
for package_path in runtime ctl library-standard library-skills \
  library-samples library-lab library-eval library-ioa \
  lab/components/core lab/components/bench lab/components/controller \
  lab; do
  uv build "$package_path" || exit 1
done
```

The workflow repeats this through `pyproject-build`, then runs `twine check`
before the OIDC upload. A package that fails either build or metadata validation
is not uploaded.

For a pipeline test before release, use `workflow_dispatch` with `publish=false`
(the default) and `bump_type=none`. This builds and uploads artifacts to the
GitHub Actions run without uploading to PyPI. Set `publish=true` to exercise the
OIDC upload manually, selecting the intended release tag as the workflow ref.
A `vX.Y.0` tag also uploads automatically; before Trusted Publishers are
configured, that upload is expected to fail at authentication.

Run the repository gates appropriate to the candidate:

```bash
task verify-unit
task verify-functional
task verify
```

Also verify MCP and A2A compliance reports and run `task docs-build` for the
published documentation site. Docker image publication is tag-driven; run the
container workflow manually on the candidate when a pre-tag image check is
needed.

## Version and branch rules

- PyPI publication support is merged to `main` before `release/vX.Y` is made.
- Release branches carry the coordinated version in `VERSION` and every
  publishable `pyproject.toml`.
- Do not tag until the release branch has been rebased onto the latest intended
  `main` and the release PR checks have passed.
- Do not reuse a published `(distribution, version)` pair. PyPI versions are
  immutable.

## Rollback and failure handling

A failed package build or Trusted Publisher configuration blocks publication;
fix the branch or PyPI/GitHub configuration and rerun the workflow. If some
packages have already uploaded, do not delete or reuse their version. Correct
the remaining package configuration and publish a new coordinated patch version
when necessary.

Container image publication is independent of PyPI upload success at the
workflow level, so inspect both package and GHCR job results before announcing a
release.
