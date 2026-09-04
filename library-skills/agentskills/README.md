# agentskills

Python client library for [agentskills.io](https://agentskills.io/) — skill discovery, parsing, and lifecycle management.

## Features

- Multi-scope skill discovery (project, user, builtin)
- YAML frontmatter parsing with lenient fallback
- Session-based activation tracking and deduplication
- Collision detection
- Ancestor-directory scanning (monorepo support)
- Client-specific directory support (~/.{client}/skills/)

## Usage

```python
from agentskills import Discovery

registry = Discovery(
    manifest_skills=["code-review", "testing"],
    base_dir=Path("."),
    client_name="mas-lab",
).discover()

for record in registry.all():
    print(f"{record.name}: {record.description}")
```

## License

Apache-2.0
