#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
Dependency resolution for pipeline execution.

Handles:
- Topological sort of steps based on explicit dependencies
- Cycle detection
- Implicit dependency extraction (via @step.output references)
"""

from typing import List, Set, Dict
from collections import defaultdict, deque, OrderedDict


class DependencyResolver:
    """Resolves step execution order via topological sort."""
    
    def __init__(self, pipeline: "Pipeline"):
        self.pipeline = pipeline
        
    def resolve(self, steps: List[str] = None) -> List[str]:
        """Resolve execution order for steps.
        
        Args:
            steps: Specific steps to execute (None = all steps)
            
        Returns:
            List of step names in execution order
            
        Raises:
            ValueError: If cycle detected or step not found
        """
        # Default to all steps
        if steps is None:
            steps = [s.name for s in self.pipeline.steps]
        
        # Include all transitive dependencies
        required = self._get_transitive_dependencies(steps)
        
        # Build graph for required steps only
        graph = defaultdict(list)
        in_degree = defaultdict(int)
        
        for step_name in required:
            step = self.pipeline.get_step(step_name)
            if not step:
                raise ValueError(f"Step not found: {step_name}")
            
            # Explicit dependencies
            explicit_deps = step.depends_on
            
            # Implicit dependencies (from @step.output references)
            implicit_deps = self._extract_implicit_dependencies(step)
            
            all_deps = list(set(explicit_deps + implicit_deps))
            
            # Filter to only required steps
            all_deps = [d for d in all_deps if d in required]
            
            for dep in all_deps:
                if dep not in self.pipeline._step_map:
                    raise ValueError(f"Step '{step.name}' depends on unknown step '{dep}'")
                graph[dep].append(step_name)
                in_degree[step_name] += 1
            
            # Ensure step exists in in_degree even with no dependencies
            if step_name not in in_degree:
                in_degree[step_name] = 0
        
        # Topological sort (Kahn's algorithm)
        queue = deque([s for s in required if in_degree[s] == 0])
        result = []
        
        while queue:
            node = queue.popleft()
            result.append(node)
            
            for neighbor in graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        # Check for cycles
        if len(result) != len(required):
            raise ValueError("Cycle detected in pipeline dependencies")
        
        return result
    
    def _get_transitive_dependencies(self, steps: List[str]) -> List[str]:
        """Get all transitive dependencies for given steps.
        
        Returns steps in a stable, insertion-order-preserving list so that
        the topological sort that follows produces deterministic results for
        independent steps (YAML definition order is respected).
        """
        # Use an OrderedDict as an ordered set to preserve insertion order
        required: "OrderedDict[str, None]" = OrderedDict()
        queue = deque(steps)
        
        while queue:
            step_name = queue.popleft()
            if step_name in required:
                continue
            
            required[step_name] = None
            
            step = self.pipeline.get_step(step_name)
            if step:
                # Add explicit dependencies
                for dep in step.depends_on:
                    if dep not in required:
                        queue.append(dep)
                
                # Add implicit dependencies
                implicit = self._extract_implicit_dependencies(step)
                for dep in implicit:
                    if dep not in required:
                        queue.append(dep)
        
        return list(required.keys())
    
    def _extract_implicit_dependencies(self, step: "PipelineStep") -> List[str]:
        """Extract implicit dependencies from config.
        
        Looks for references like:
        - @dataset.output
        - @consolidate.dataframe
        
        Returns:
            List of step names referenced in config
        """
        dependencies = []
        
        def _scan_value(value):
            """Recursively scan config values for references."""
            if isinstance(value, str):
                # Check for @step.field references
                if value.startswith("@"):
                    parts = value[1:].split(".", 1)
                    step_name = parts[0]
                    if step_name in self.pipeline._step_map:
                        dependencies.append(step_name)
            
            elif isinstance(value, dict):
                for v in value.values():
                    _scan_value(v)
            
            elif isinstance(value, list):
                for item in value:
                    _scan_value(item)
        
        _scan_value(step.config)
        
        return dependencies
    
    def get_execution_layers(self, steps: List[str] = None) -> List[List[str]]:
        """Group steps into execution layers for parallel execution.
        
        Steps in the same layer have no dependencies on each other.
        
        Args:
            steps: Specific steps to execute (None = all)
            
        Returns:
            List of layers, where each layer is a list of step names
        """
        execution_order = self.resolve(steps)
        
        # Build dependency sets
        dep_sets = {}
        for step_name in execution_order:
            step = self.pipeline.get_step(step_name)
            explicit = set(step.depends_on)
            implicit = set(self._extract_implicit_dependencies(step))
            dep_sets[step_name] = explicit | implicit
        
        # Assign layers
        layers = []
        assigned = set()
        
        while len(assigned) < len(execution_order):
            layer = []
            for step_name in execution_order:
                if step_name in assigned:
                    continue
                
                # Check if all dependencies are assigned
                if dep_sets[step_name].issubset(assigned):
                    layer.append(step_name)
            
            if not layer:
                raise ValueError("Failed to compute layers (possible bug)")
            
            layers.append(layer)
            assigned.update(layer)
        
        return layers
