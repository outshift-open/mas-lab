"""Test cases demonstrating enhanced manifest validation.

These tests show that the validation catches common errors that previously
only appeared at runtime.
"""

import pytest
from pathlib import Path
import tempfile
import yaml

from mas.ctl.validate import validate_file, validate_data


def test_tool_missing_impl():
    """Tool manifest without spec.impl should fail validation."""
    manifest = {
        "apiVersion": "mas/v1",
        "kind": "Tool",
        "metadata": {"name": "my_tool"},
        "spec": {
            "description": "My tool",
            "parameters": []
        }
    }
    result = validate_data(manifest, kind="tool", strict=True)
    assert not result.ok
    assert any("spec.impl is required" in issue.message for issue in result.issues)


def test_tool_missing_module_path():
    """Tool manifest with impl but no module_path should fail."""
    manifest = {
        "apiVersion": "mas/v1",
        "kind": "Tool",
        "metadata": {"name": "my_tool"},
        "spec": {
            "description": "My tool",
            "parameters": [],
            "impl": {
                "kind": "python",
                "class_name": "MyTool"
            }
        }
    }
    result = validate_data(manifest, kind="tool", strict=True)
    assert not result.ok
    assert any("module_path is required" in issue.message for issue in result.issues)


def test_tool_legacy_implementation_key():
    """Tool using legacy 'implementation' instead of 'impl' should warn."""
    manifest = {
        "apiVersion": "mas/v1",
        "kind": "Tool",
        "metadata": {"name": "my_tool"},
        "spec": {
            "description": "My tool",
            "parameters": [],
            "implementation": {  # Wrong key!
                "type": "mock",
                "response": "{}"
            }
        }
    }
    result = validate_data(manifest, kind="tool", strict=True)
    assert not result.ok
    assert any("spec.implementation is not supported" in issue.message for issue in result.issues)


def test_agent_tool_ref_without_dot_slash():
    """Agent tool reference without ./ prefix should fail."""
    manifest = {
        "apiVersion": "mas/v1",
        "kind": "Agent",
        "metadata": {"name": "my_agent"},
        "spec": {
            "description": "My agent",
            "tools": [
                {"ref": "tools/my_tool.yaml"}  # Missing ./
            ],
            "models": [{"model": "azure/gpt-4o"}],
            "design_pattern": {"type": "react"}
        }
    }
    result = validate_data(manifest, kind="agent", strict=True)
    assert not result.ok
    assert any(
        "looks like a file path" in issue.message and
        "use './...'" in issue.message
        for issue in result.issues
    )


def test_agent_tool_ref_with_correct_format():
    """Agent tool reference with ./ prefix should pass."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        
        # Create a valid tool manifest
        tool_dir = tmppath / "tools"
        tool_dir.mkdir()
        tool_file = tool_dir / "my_tool.yaml"
        tool_file.write_text(yaml.dump({
            "apiVersion": "mas/v1",
            "kind": "Tool",
            "metadata": {"name": "my_tool"},
            "spec": {
                "description": "My tool",
                "parameters": [],
                "impl": {
                    "kind": "python",
                    "module_path": "./my_tool.py",
                    "class_name": "MyTool"
                }
            }
        }))
        
        # Create agent manifest with correct ref
        agent_file = tmppath / "agent.yaml"
        agent_file.write_text(yaml.dump({
            "apiVersion": "mas/v1",
            "kind": "Agent",
            "metadata": {"name": "my_agent"},
            "spec": {
                "description": "My agent",
                "tools": [
                    {"ref": "./tools/my_tool.yaml"}  # Correct format
                ],
                "models": [{"model": "azure/gpt-4o"}],
                "design_pattern": {"type": "react"}
            }
        }))
        
        result = validate_file(agent_file, kind="agent", strict=True, resolve_refs=True)
        assert result.ok, f"Validation failed: {[i.message for i in result.issues]}"


def test_overlay_with_append_tag():
    """Overlay using !append tag should fail (not supported by yaml.safe_load)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        overlay_file = tmppath / "overlay.yaml"
        
        # Write overlay with !append tag
        overlay_file.write_text("""
apiVersion: mas/v1
kind: Overlay
metadata:
  name: test-overlay
spec:
  target:
    kind: MAS
  patch:
    agents:
      my_agent:
        context:
          role: !append |
            Additional instructions
""")
        
        # The validation will fail during YAML loading
        # This is actually the desired behavior - fail fast
        try:
            result = validate_file(overlay_file, kind="overlay", strict=True, resolve_refs=False)
            # If we get here, check if validation caught the tag
            assert not result.ok
            assert any("!append" in issue.message for issue in result.issues)
        except Exception as e:
            # Expected: YAML parser raises exception for unknown tag
            assert "!append" in str(e)
            # This is correct behavior - fail fast at parse time


def test_overlay_with_op_add():
    """Overlay using $op: {add: [...]} should pass validation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        overlay_file = tmppath / "overlay.yaml"
        
        # Write overlay with $op add (correct pattern)
        overlay_file.write_text("""
apiVersion: mas/v1
kind: Overlay
metadata:
  name: test-overlay
spec:
  target:
    kind: MAS
  patch:
    agents:
      my_agent:
        context:
          role:
            $op:
              add:
                - |
                  Additional instructions to append
""")
        
        result = validate_file(overlay_file, kind="overlay", strict=True, resolve_refs=False)
        assert result.ok, f"Validation failed: {[i.message for i in result.issues]}"


def test_agent_bare_string_tool_ref_with_path():
    """Agent using bare string tool ref that looks like a path should fail."""
    manifest = {
        "apiVersion": "mas/v1",
        "kind": "Agent",
        "metadata": {"name": "my_agent"},
        "spec": {
            "description": "My agent",
            "tools": [
                "tools/query_salesforce_opportunity.yaml"  # Should be ./tools/...
            ],
            "models": [{"model": "azure/gpt-4o"}],
            "design_pattern": {"type": "react"}
        }
    }
    result = validate_data(manifest, kind="agent", strict=True)
    assert not result.ok
    assert any(
        "looks like a file path" in issue.message and
        "use './...'" in issue.message
        for issue in result.issues
    )


if __name__ == "__main__":
    # Run tests
    print("Running validation enhancement tests...\n")
    
    tests = [
        ("Tool missing impl", test_tool_missing_impl),
        ("Tool missing module_path", test_tool_missing_module_path),
        ("Tool legacy implementation key", test_tool_legacy_implementation_key),
        ("Agent tool ref without ./", test_agent_tool_ref_without_dot_slash),
        ("Agent tool ref with correct format", test_agent_tool_ref_with_correct_format),
        ("Overlay with !append tag", test_overlay_with_append_tag),
        ("Overlay with $op add", test_overlay_with_op_add),
        ("Agent bare string tool ref", test_agent_bare_string_tool_ref_with_path),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            test_func()
            print(f"✓ {name}")
            passed += 1
        except AssertionError as e:
            print(f"✗ {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {name}: EXCEPTION: {e}")
            failed += 1
    
    print(f"\n{passed} passed, {failed} failed")
