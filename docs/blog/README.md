<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Blog (contributors)

## Adding a post

Each post is a **folder** under `docs/blog/posts/` with an `index.md` and any
figures or assets for that post:

```
docs/blog/posts/
  2026-06-17-v0-1-release/
    index.md
    Three-layers.png
```

`index.md` starts with YAML front matter:

```yaml
---
date: 2026-06-17
authors:
  - jordan.auge
categories:
  - Updates   # or Releases
---
```

Reference figures with a path relative to the **published post URL** (date/slug), not
the source folder. The blog plugin serves posts under `blog/YYYY/MM/DD/slug/` while
assets from the post folder land under `blog/YYYY-MM-DD-slug/`. Prefer shared
figures under `docs/assets/blog/` and link with:

```html
<img src="../../../../../assets/blog/your-figure.png" alt="..." />
```

(five `../` segments from `blog/YYYY/MM/DD/slug/` to the site root.)

Authors are defined in `docs/blog/.authors.yml`.

Allowed categories (enforced in `mkdocs.yml`):

| Category | Use for |
|----------|---------|
| **Updates** | Development on `main` between releases — features, docs, reproducibility |
| **Releases** | Versioned release notes — everything that changed since the last tag |

Category intro pages (optional custom copy above post lists):

- `docs/blog/category/updates.md`
- `docs/blog/category/releases.md`

This file is **not** published on the site (`exclude_docs` in `mkdocs.yml`).
