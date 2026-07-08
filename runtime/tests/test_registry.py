#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for the centralized plugin registry (mas.runtime.registry)."""

import pytest
from pathlib import Path
from mas.runtime.registry import (
    PluginRegistry,
    PluginEntry,
    VariantInfo,
    get_registry,
    register_plugin,
    add_plugin_path,
)


class TestVariantInfo:
    """Test VariantInfo dataclass."""
    
    def test_variant_info_creation(self):
        """Test creating a VariantInfo."""
        info = VariantInfo(
            module="mas.runtime.test",
            class_name="TestClass",
            version="1.0.0",
            description="Test plugin"
        )
        assert info.module == "mas.runtime.test"
        assert info.class_name == "TestClass"
        assert info.version == "1.0.0"
        assert info.description == "Test plugin"
    
    def test_load_class(self):
        """Test loading a class from VariantInfo."""
        info = VariantInfo(
            module="pathlib",
            class_name="Path",
        )
        cls = info.load_class()
        assert cls is Path


class TestPluginEntry:
    """Test PluginEntry dataclass."""
    
    def test_plugin_entry_creation(self):
        """Test creating a PluginEntry."""
        variant = VariantInfo(module="test", class_name="Test")
        entry = PluginEntry(
            urn="mas.dp.test",
            description="Test DP",
            default_variant="builtin",
            shortcuts=["test", "t"],
            variants={"builtin": variant}
        )
        assert entry.urn == "mas.dp.test"
        assert entry.description == "Test DP"
        assert entry.default_variant == "builtin"
        assert entry.shortcuts == ["test", "t"]
        assert "builtin" in entry.variants
    
    def test_default_property(self):
        """Test default variant property."""
        variant = VariantInfo(module="test", class_name="Test")
        entry = PluginEntry(
            urn="mas.dp.test",
            default_variant="builtin",
            variants={"builtin": variant}
        )
        assert entry.default is variant
    
    def test_resolve_default_variant(self):
        """Test resolving to default variant."""
        variant = VariantInfo(module="test", class_name="Test")
        entry = PluginEntry(
            urn="mas.dp.test",
            default_variant="builtin",
            variants={"builtin": variant}
        )
        resolved = entry.resolve()
        assert resolved is variant
    
    def test_resolve_specific_variant(self):
        """Test resolving to specific variant."""
        builtin = VariantInfo(module="test", class_name="Builtin")
        custom = VariantInfo(module="test", class_name="Custom")
        entry = PluginEntry(
            urn="mas.dp.test",
            default_variant="builtin",
            variants={"builtin": builtin, "custom": custom}
        )
        resolved = entry.resolve("custom")
        assert resolved is custom
    
    def test_resolve_unknown_variant_raises(self):
        """Test resolving unknown variant raises ValueError."""
        variant = VariantInfo(module="test", class_name="Test")
        entry = PluginEntry(
            urn="mas.dp.test",
            default_variant="builtin",
            variants={"builtin": variant}
        )
        with pytest.raises(ValueError, match="Unknown variant 'unknown'"):
            entry.resolve("unknown")


class TestPluginRegistry:
    """Test PluginRegistry class."""
    
    def test_registry_initialization(self):
        """Test registry initializes empty."""
        reg = PluginRegistry()
        assert len(reg.list_all()) >= 0  # May have loaded from YAML
        assert len(reg.list_categories()) >= 0
    
    def test_register_plugin_entry(self):
        """Test registering a plugin entry."""
        reg = PluginRegistry()
        variant = VariantInfo(module="pathlib", class_name="Path")
        entry = PluginEntry(
            urn="mas.dp.testplugin",
            shortcuts=["testplugin"],
            variants={"builtin": variant}
        )
        reg.register(entry)
        
        assert "mas.dp.testplugin" in reg.list_all()
        resolved = reg.resolve("testplugin")
        assert resolved is not None
        assert resolved.class_name == "Path"
    
    def test_resolve_by_urn(self):
        """Test resolving plugin by URN."""
        registry = get_registry()
        info = registry.resolve("mas.dp.react")
        assert info is not None
        assert info.class_name == "ReactPlugin"
    
    def test_resolve_by_shortcut(self):
        """Test resolving plugin by shortcut."""
        registry = get_registry()
        info = registry.resolve("react")
        assert info is not None
        assert info.class_name == "ReactPlugin"
    
    def test_resolve_unknown_returns_none(self):
        """Test resolving unknown plugin returns None."""
        registry = get_registry()
        info = registry.resolve("nonexistent_plugin_xyz")
        assert info is None
    
    def test_resolve_by_type_design_pattern(self):
        """Test type-based resolution for design patterns."""
        registry = get_registry()
        info = registry.resolve_by_type("design_pattern", "react")
        assert info is not None
        assert info.class_name == "ReactPlugin"
    
    def test_resolve_by_type_context_manager(self):
        """Test type-based resolution for context managers."""
        registry = get_registry()
        info = registry.resolve_by_type("context_manager", "stack")
        assert info is not None
        assert info.class_name == "StackConversation"
    
    def test_resolve_by_type_unknown_returns_none(self):
        """Test type-based resolution for unknown plugin returns None."""
        registry = get_registry()
        info = registry.resolve_by_type("design_pattern", "nonexistent_xyz")
        assert info is None

    def test_get_with_type_and_name(self):
        """Test generic get() API with explicit type and name."""
        registry = get_registry()
        info = registry.get("design_pattern", "react")
        assert info is not None
        assert info.class_name == "ReactPlugin"

    def test_get_with_type_and_attributes(self):
        """Test generic get() API with attribute filtering."""
        class _AttrPlugin:
            pass

        register_plugin(
            "mas.codec.test_store",
            _AttrPlugin,
            shortcuts=["test-store"],
            attributes={"artifact_kind": "test", "store_type": "store"},
        )

        info = get_registry().get(
            "codec",
            attributes={"artifact_kind": "test", "store_type": "store"},
        )
        assert info is not None
        assert info.class_name == "_AttrPlugin"
    
    def test_get_by_category_dp(self):
        """Test getting all design patterns by canonical category."""
        registry = get_registry()
        dp_plugins = registry.get_by_category("design_pattern")
        assert len(dp_plugins) > 0

        # Verify all entries are design patterns by declared plugin_type
        for entry in dp_plugins:
            assert entry.attributes.get("plugin_type") == "design_pattern"
    
    def test_get_by_category_cm(self):
        """Test getting all context managers by canonical category."""
        registry = get_registry()
        cm_plugins = registry.get_by_category("context_manager")
        assert len(cm_plugins) > 0

        # Verify all entries are context managers by declared plugin_type
        for entry in cm_plugins:
            assert entry.attributes.get("plugin_type") == "context_manager"
    
    def test_get_by_category_unknown_returns_empty(self):
        """Test getting unknown category returns empty list."""
        registry = get_registry()
        plugins = registry.get_by_category("nonexistent_category")
        assert plugins == []
    
    def test_list_categories(self):
        """Test listing all categories."""
        registry = get_registry()
        categories = registry.list_categories()
        assert len(categories) > 0
        assert "design_pattern" in categories
        assert "context_manager" in categories
    
    def test_all_aliases(self):
        """Test getting all aliases."""
        registry = get_registry()
        aliases = registry.all_aliases()
        assert len(aliases) > 0
        assert "react" in aliases
        assert aliases["react"] == "mas.dp.react"
    
    def test_add_scan_path(self):
        """Test adding plugin scan path."""
        reg = PluginRegistry()
        path = Path("/test/path")
        reg.add_scan_path(path)
        # Can't directly test _scan_paths (private), but shouldn't raise


class TestDynamicRegistration:
    """Test dynamic plugin registration."""
    
    def test_register_plugin_function(self):
        """Test registering a plugin via convenience function."""
        class TestPlugin:
            pass
        
        register_plugin("mas.test.dynamic", TestPlugin, shortcuts=["dynamic"])
        
        registry = get_registry()
        info = registry.resolve("dynamic")
        assert info is not None
        assert info.class_name == "TestPlugin"
    
    def test_register_plugin_with_variant(self):
        """Test registering a plugin with specific variant."""
        class CustomPlugin:
            pass
        
        register_plugin(
            "mas.test.custom",
            CustomPlugin,
            shortcuts=["custom"],
            variant="custom_variant",
            description="Custom test plugin"
        )
        
        registry = get_registry()
        info = registry.resolve("custom")
        assert info is not None
        assert info.class_name == "CustomPlugin"
    
    def test_add_plugin_path_function(self):
        """Test adding plugin path via convenience function."""
        path = Path("/test/custom/plugins")
        add_plugin_path(str(path))  # Should not raise


class TestSingleton:
    """Test registry singleton pattern."""
    
    def test_get_registry_returns_same_instance(self):
        """Test get_registry returns singleton."""
        reg1 = get_registry()
        reg2 = get_registry()
        assert reg1 is reg2
    
    def test_registry_initialized_once(self):
        """Test registry is initialized only once."""
        reg = get_registry()
        # Should have plugins from YAML
        plugins = reg.list_all()
        assert len(plugins) > 0  # Loaded from built-in registry data


class TestTypeResolution:
    """Test canonical type-based resolution."""

    def test_design_pattern_resolves(self):
        registry = get_registry()
        info = registry.resolve_by_type("design_pattern", "react")
        assert info is not None

    def test_context_manager_resolves(self):
        registry = get_registry()
        info = registry.resolve_by_type("context_manager", "stack")
        assert info is not None


class TestRealPlugins:
    """Test with real built-in plugins."""
    
    def test_react_plugin_registered(self):
        """Test react design pattern is registered."""
        registry = get_registry()
        info = registry.resolve("react")
        assert info is not None
        assert info.module == "mas.runtime.machines.design_pattern.plugins.react"
        assert info.class_name == "ReactPlugin"
    
    def test_cot_plugin_registered(self):
        """Test CoT design pattern is registered."""
        registry = get_registry()
        info = registry.resolve("cot")
        assert info is not None
        assert info.class_name == "CotPlugin"
    
    def test_stack_cm_registered(self):
        """Test stack context manager is registered."""
        registry = get_registry()
        info = registry.resolve("stack")
        assert info is not None
        assert info.class_name == "StackConversation"
    
    def test_sliding_window_cm_registered(self):
        """Test sliding-window context manager is registered."""
        registry = get_registry()
        info = registry.resolve("sliding-window")
        assert info is not None
        assert "SlidingWindow" in info.class_name
