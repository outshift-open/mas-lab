<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Tool Definition Schema Reference

Complete specification for defining tools (callable functions) that agents can use.

## Overview

A tool is a callable function made available to an agent. Tool definitions specify:

- Name and description
- Input parameters and types
- Output format
- Usage constraints
- Error handling

## Tool Contract Implementation

All tools must implement `ToolContract`:

```python
from mas.runtime.contracts import ToolContract, ToolInput
from pydantic import Field

class MyTool(ToolContract):
    name = "my_tool"
    description = "What this tool does"
    
    class Input(ToolInput):
        param1: str = Field(..., description="Required parameter")
        param2: int = Field(10, description="Optional parameter with default")
    
    async def execute(self, input: Input) -> str:
        """Execute tool and return result."""
        result = process(input.param1, input.param2)
        return json.dumps(result)
```

## Schema Fields

### Tool Class Definition

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | str | ✅ | Unique tool identifier (alphanumeric, underscores) |
| `description` | str | ✅ | Human-readable description (shown to agent) |
| `Input` | Pydantic model | ✅ | Input parameter schema |
| `execute()` | async method | ✅ | Tool implementation |

### Input Class Definition

Tool inputs must inherit from `ToolInput` and use Pydantic fields:

```python
class Input(ToolInput):
    # Required field
    query: str = Field(..., description="Search query")
    
    # Optional with default
    limit: int = Field(10, description="Max results")
    
    # Optional (None default)
    filters: dict = Field(None, description="Search filters")
    
    # Constrained types
    page: int = Field(1, ge=1, description="Page number (>= 1)")
    confidence: float = Field(0.8, ge=0.0, le=1.0, description="Confidence threshold")
```

#### Field Requirements

| Property | Purpose | Example |
| --- | --- | --- |
| `description` | Required - shown to agent | `"User's search query"` |
| `default` or `...` | `...` = required, value = optional | `Field(...)` or `Field(10)` |
| `ge`, `le`, `gt`, `lt` | Numeric constraints | `Field(1, ge=1, le=100)` |
| `min_length`, `max_length` | String constraints | `Field(..., min_length=1)` |
| `pattern` | Regex validation | `Field(..., pattern=r"^\d{3}-\d{4}$")` |

### Return Type

Tools return `str` (JSON-serializable):

```python
async def execute(self, input: Input) -> str:
    result = {"status": "ok", "data": [...]}
    return json.dumps(result)
```

For complex structures, use JSON:

```python
async def execute(self, input: Input) -> str:
    results = [
        {"id": 1, "score": 0.95},
        {"id": 2, "score": 0.87},
    ]
    return json.dumps(results)
```

## Examples

### Simple Calculation Tool

```python
from mas.runtime.contracts import ToolContract, ToolInput
from pydantic import Field
import json

class CalculatorTool(ToolContract):
    name = "calculator"
    description = "Perform mathematical calculations"
    
    class Input(ToolInput):
        expression: str = Field(
            ...,
            description="Mathematical expression (e.g., '2+2', 'sqrt(16)')"
        )
    
    async def execute(self, input: Input) -> str:
        try:
            result = eval(input.expression)
            return json.dumps({"result": result, "error": None})
        except Exception as e:
            return json.dumps({"result": None, "error": str(e)})
```

### Search Tool with Constraints

```python
class WebSearchTool(ToolContract):
    name = "web_search"
    description = "Search the web for information"
    
    class Input(ToolInput):
        query: str = Field(
            ...,
            description="Search query",
            min_length=1,
            max_length=500
        )
        num_results: int = Field(
            10,
            description="Number of results (1-50)",
            ge=1,
            le=50
        )
        language: str = Field(
            "en",
            description="Language code (e.g., 'en', 'fr', 'de')"
        )
    
    async def execute(self, input: Input) -> str:
        results = await search_api(
            input.query,
            num_results=input.num_results,
            language=input.language
        )
        return json.dumps(results)
```

### Database Query Tool

```python
class DatabaseTool(ToolContract):
    name = "database_query"
    description = "Execute SQL queries against the database"
    
    class Input(ToolInput):
        table: str = Field(
            ...,
            description="Table name",
            pattern=r"^[a-z_]+$"  # Only lowercase and underscores
        )
        where_clause: str = Field(
            None,
            description="SQL WHERE clause (optional)"
        )
        limit: int = Field(
            100,
            description="Max rows",
            ge=1,
            le=10000
        )
    
    async def execute(self, input: Input) -> str:
        query = f"SELECT * FROM {input.table}"
        if input.where_clause:
            query += f" WHERE {input.where_clause}"
        query += f" LIMIT {input.limit}"
        
        try:
            results = await db.execute(query)
            return json.dumps({
                "rows": results,
                "count": len(results)
            })
        except Exception as e:
            return json.dumps({"error": str(e)})
```

## Tool Registration

### Via Manifest

```yaml
spec:
  tools:
    - module_path: "my_company.tools.calculator.CalculatorTool"
    - module_path: "my_company.tools.search.WebSearchTool"
```

### Via Builder (Python)

```python
from mas.runtime import RuntimeBuilder
from my_company.tools import CalculatorTool, WebSearchTool

builder = RuntimeBuilder.from_manifest("agent.yaml")
builder = builder.with_tool(CalculatorTool)
builder = builder.with_tool(WebSearchTool)

kernel = builder.build()
```

## Governance Integration

OSS tools integrate with **budget** and declarative policy overlays (guardrails,
HITL). Task-based access control (TBAC) and execution sandboxing are internal
extensions — see `mas-lab-internal` (`docs/contracts/tbac-contract.md`).

## Testing Tools

```python
import pytest
import asyncio
from my_company.tools import CalculatorTool

@pytest.mark.asyncio
async def test_calculator():
    tool = CalculatorTool()
    
    input_obj = tool.Input(expression="2+2")
    result = await tool.execute(input_obj)
    
    import json
    parsed = json.loads(result)
    assert parsed["result"] == 4
    assert parsed["error"] is None

@pytest.mark.asyncio
async def test_calculator_error():
    tool = CalculatorTool()
    
    input_obj = tool.Input(expression="1/0")
    result = await tool.execute(input_obj)
    
    parsed = json.loads(result)
    assert parsed["result"] is None
    assert parsed["error"] is not None
```

## Best Practices

1. **Clear descriptions**: Show agent exactly what tool does
2. **Constrain inputs**: Use Pydantic validators to prevent misuse
3. **Validate output**: Return JSON with clear structure
4. **Handle errors**: Catch exceptions and return structured error response
5. **Test thoroughly**: Each tool needs unit tests
6. **Document parameters**: Each field must have description
7. **Keep tools focused**: One responsibility per tool
8. **Version tools**: Tool changes can break agent behavior

## Common Patterns

### Optional Parameters

```python
class Input(ToolInput):
    query: str = Field(...)
    filters: dict = Field(None, description="Optional filters")
    timeout: int = Field(30, description="Request timeout")
```

### Constrained Numeric Values

```python
class Input(ToolInput):
    page: int = Field(1, ge=1, description="Page >= 1")
    confidence: float = Field(0.5, ge=0.0, le=1.0)
```

### Pattern Matching

```python
class Input(ToolInput):
    email: str = Field(..., pattern=r"^[\w\.-]+@[\w\.-]+\.\w+$")
    phone: str = Field(..., pattern=r"^\+?1?\d{9,15}$")
```

### Union Types

```python
from typing import Union

class Input(ToolInput):
    value: Union[str, int] = Field(...)  # Can be string or int
```

For full API reference, see [mas-runtime-api.md](../api-reference/mas-runtime-api.md#tooldevelopment).
