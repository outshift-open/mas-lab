#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from typing import List, Dict, Union, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

class StepType(str, Enum):
    # Basic execution
    LLM = "llm"                 # Call an LLM with a prompt
    TOOL = "tool"               # Execute a specific tool
    CODE = "code"               # Run local code (safe)
    
    # Flow control
    DECISION = "decision"       # Branching based on condition
    PARALLEL = "parallel"       # Run multiple branches concurrently
    JOIN = "join"              # Wait for parallel branches
    
    # Advanced reasoning patterns
    COT = "chain_of_thought"    # Linear reasoning sequence
    TOT = "tree_of_thoughts"    # Branching exploration with evaluation
    REFLECT = "reflection"      # Self-critique loop

@dataclass
class PromptConfig:
    template_id: str            # Reference to external prompt template
    input_vars: List[str]       # Variables required from state
    output_parser: Optional[str] = None # Parser for structured output

@dataclass
class Transition:
    target_step_id: str
    condition: Optional[str] = None # Expression evaluating state (e.g., "result > 0.8")

@dataclass
class Step:
    id: str
    type: StepType
    name: str
    description: Optional[str] = None
    
    # Execution details
    prompt: Optional[PromptConfig] = None
    tools: List[str] = field(default_factory=list) # List of tool names allowed
    
    # Flow
    next: List[Transition] = field(default_factory=list) # Possible next steps
    
    # Specific configs (e.g., for TOT)
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Metadata for TOT might include:
    # - max_depth: int
    # - branching_factor: int
    # - exploration_strategy: "bfs" | "dfs"

@dataclass
class Workflow:
    id: str
    name: str
    version: str
    inputs: Dict[str, str]      # Schema name -> type
    outputs: Dict[str, str]     # Schema name -> type
    steps: List[Step]
    start_step_id: str
