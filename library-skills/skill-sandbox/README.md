# skill-sandbox

Portable subprocess sandbox for skill script execution — resource limits, environment filtering, path guards.

## Features

- Environment variable sanitization (strips API keys, tokens, credentials)
- POSIX resource limits (CPU time, address space)
- Timeout enforcement
- Automatic interpreter selection (.py, .sh, shebang)
- Path traversal protection

## Usage

```python
from sandbox import run_script
from pathlib import Path

result = run_script(
    script_path=Path("scripts/extract.py"),
    args=["arg1", "arg2"],
    timeout=30,
    env_extra={"CONFIG": "value"},
)

print(result.exit_code, result.stdout, result.stderr)
```

## License

Apache-2.0
