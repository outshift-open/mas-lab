#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
Multi-run orchestration for benchmarks.

Coordinates N runs per dataset item across multiple patterns.
"""

import asyncio
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Callable, Awaitable, Optional, List
import yaml

from mas.lab.benchmark.dataset import Dataset, DatasetItem  
from mas.lab.benchmark.storage import ResultStorage, RunMetadata


class MultiRunOrchestrator:
    """
    Orchestrates multiple benchmark runs.
    
    Features:
    - N runs per dataset item
    - Multiple pattern support
    - Incremental execution
    - Progress tracking
    """
    
    def __init__(
        self,
        storage: ResultStorage,
        n_runs: int = 3,
        pause_between_runs: float = 1.0
    ):
        self.storage = storage
        self.n_runs = n_runs
        self.pause_between_runs = pause_between_runs
    
    async def run_dataset(
        self,
        dataset: Dataset,
        patterns: Dict[str, Dict[str, Any]],
        agent_factory: Callable[[str, Dict[str, Any]], Awaitable[Any]],
        item_filter: Optional[Callable[[DatasetItem], bool]] = None
    ) -> Dict[str, Any]:
        """
        Run full dataset evaluation.
        
        Args:
            dataset: Dataset to evaluate
            patterns: Dict of pattern_name -> config
            agent_factory: Async function(pattern_name, config) -> agent
                          Agent must have handle_task(prompt) method
            item_filter: Optional filter for items
            
        Returns:
            Summary statistics
        """
        print(f"{'='*70}")
        print(f"BENCHMARK: {dataset.name}")
        print(f"{'='*70}")
        print(f"Items: {len(dataset)}")
        print(f"Patterns: {list(patterns.keys())}")
        print(f"Runs per item: {self.n_runs}")
        print()
        
        total_runs = 0
        successful_runs = 0
        
        for item in dataset:
            if item_filter and not item_filter(item):
                continue
            
            print(f"\n{'─'*70}")
            print(f"Item: {item.id} [{item.category or 'general'}]")
            print(f"Prompt: {item.prompt[:80]}...")
            print(f"{'─'*70}")
            
            for pattern_name, pattern_config in patterns.items():
                print(f"\n  Pattern: {pattern_name}")
                
                for run_idx in range(1, self.n_runs + 1):
                    run_number = self.storage.get_next_run_number(
                        dataset.name, item.id, pattern_name
                    )
                    run_id = self.storage.generate_run_id(pattern_name, run_number)
                    
                    print(f"    Run {run_idx}/{self.n_runs} [{run_id}]...", end=" ")
                    
                    metadata = RunMetadata(
                        dataset_name=dataset.name,
                        item_id=item.id,
                        run_id=run_id,
                        pattern=pattern_name,
                        timestamp=datetime.now().isoformat(),
                        config=pattern_config
                    )
                    
                    start_time = time.time()
                    
                    try:
                        # Create agent
                        agent = await agent_factory(pattern_name, pattern_config)
                        
                        # Execute task
                        result = await self._execute_task(agent, item.prompt)
                        
                        metadata.success = True
                        metadata.latency_ms = (time.time() - start_time) * 1000
                        
                        # Save results
                        self.storage.save_run(
                            dataset_name=dataset.name,
                            item_id=item.id,
                            run_id=run_id,
                            metadata=metadata,
                            events_file=result.get("events_file"),
                            artifacts=result.get("artifacts")
                        )
                        
                        print(f"✓ {metadata.latency_ms:.0f}ms")
                        successful_runs += 1
                        
                    except Exception as e:
                        metadata.success = False
                        metadata.latency_ms = (time.time() - start_time) * 1000
                        metadata.error = str(e)
                        
                        self.storage.save_run(
                            dataset_name=dataset.name,
                            item_id=item.id,
                            run_id=run_id,
                            metadata=metadata
                        )
                        
                        print(f"✗ Error: {str(e)[:50]}")
                    
                    total_runs += 1
                    
                    # Pause between runs
                    if run_idx < self.n_runs:
                        await asyncio.sleep(self.pause_between_runs)
        
        summary = {
            "total_runs": total_runs,
            "successful_runs": successful_runs,
            "failed_runs": total_runs - successful_runs,
            "success_rate": successful_runs / total_runs if total_runs > 0 else 0
        }
        
        print(f"\n{'='*70}")
        print(f"SUMMARY")
        print(f"{'='*70}")
        print(f"Total runs: {total_runs}")
        print(f"Successful: {successful_runs}")
        print(f"Failed: {summary['failed_runs']}")
        print(f"Success rate: {summary['success_rate']:.1%}")
        
        return summary
    
    async def _execute_task(self, agent: Any, prompt: str) -> Dict[str, Any]:
        """Execute task on agent."""
        # Check if agent has async handle_task
        handle_task = getattr(agent, "handle_task", None)
        if not handle_task:
            raise ValueError("Agent must have handle_task method")
        
        result = handle_task({"prompt": prompt, "user_message": prompt})
        if asyncio.iscoroutine(result):
            result = await result
        
        return result or {}
    
    @classmethod
    def from_config(cls, config_path: Path, storage: ResultStorage) -> "MultiRunOrchestrator":
        """Load configuration from YAML."""
        with open(config_path) as f:
            config = yaml.safe_load(f)
        
        return cls(
            storage=storage,
            n_runs=config.get("n_runs", 3),
            pause_between_runs=config.get("pause_between_runs", 1.0)
        )
