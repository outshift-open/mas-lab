#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
Real-time progress tracking for benchmark execution.
"""

import sys
import time
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class ProgressMetrics:
    """Metrics collected during benchmark execution."""
    
    total_scenarios: int = 0
    completed_scenarios: int = 0
    failed_scenarios: int = 0
    in_progress: int = 0
    
    total_tokens_input: int = 0
    total_tokens_output: int = 0
    total_tokens: int = 0
    
    start_time: float = field(default_factory=time.time)
    
    # Store per-scenario results for summary
    scenario_results: Dict = field(default_factory=dict)
    
    @property
    def elapsed_seconds(self) -> float:
        """Time elapsed since start."""
        return time.time() - self.start_time
    
    @property
    def completion_rate(self) -> float:
        """Scenarios per second."""
        if self.elapsed_seconds == 0:
            return 0.0
        return self.completed_scenarios / self.elapsed_seconds
    
    @property
    def eta_seconds(self) -> Optional[float]:
        """Estimated time to completion in seconds."""
        if self.completion_rate == 0 or self.completed_scenarios == 0:
            return None
        remaining = self.total_scenarios - self.completed_scenarios
        return remaining / self.completion_rate
    
    @property
    def percent_complete(self) -> float:
        """Percentage completion (0-100)."""
        if self.total_scenarios == 0:
            return 0.0
        return (self.completed_scenarios / self.total_scenarios) * 100


class ProgressTracker:
    """Track and display real-time benchmark progress."""
    
    def __init__(self, enabled: bool = True, show_details: bool = True):
        """Initialize progress tracker.
        
        Args:
            enabled: Whether to show progress updates
            show_details: Whether to show detailed metrics
        """
        self.enabled = enabled
        self.show_details = show_details
        self.metrics = ProgressMetrics()
        self._last_update = 0
        self._update_interval = 0.1  # Update every 100ms
        
    def start(self, total_scenarios: int):
        """Start tracking progress."""
        self.metrics.total_scenarios = total_scenarios
        self.metrics.start_time = time.time()
        if self.enabled:
            print(f"\n🚀 Starting benchmark: {total_scenarios} scenarios\n", flush=True)
    
    def update_in_progress(self, count: int):
        """Update number of scenarios currently executing."""
        self.metrics.in_progress = count
        self._maybe_render()
    
    def complete_scenario(self, scenario_id: str, success: bool, tokens: Dict[str, int]):
        """Mark a scenario as complete.
        
        Args:
            scenario_id: Scenario identifier
            success: Whether scenario succeeded
            tokens: Token usage dict with 'input', 'output', 'total'
        """
        self.metrics.completed_scenarios += 1
        if not success:
            self.metrics.failed_scenarios += 1
        
        # Accumulate tokens
        self.metrics.total_tokens_input += tokens.get("input", 0)
        self.metrics.total_tokens_output += tokens.get("output", 0)
        self.metrics.total_tokens += tokens.get("total", 0)
        
        # Store result
        self.metrics.scenario_results[scenario_id] = {
            "success": success,
            "tokens": tokens
        }
        
        self._maybe_render()
    
    def _maybe_render(self):
        """Render progress bar if enough time has passed."""
        if not self.enabled:
            return
        
        now = time.time()
        if now - self._last_update < self._update_interval:
            return
        
        self._last_update = now
        self._render()
    
    def _render(self):
        """Render current progress to stdout (single line)."""
        m = self.metrics
        
        # Format elapsed time
        elapsed_str = self._format_duration(m.elapsed_seconds)
        
        # Format ETA
        if m.eta_seconds is not None:
            eta_str = self._format_duration(m.eta_seconds)
        else:
            eta_str = "calculating..."
        
        # Format tokens
        tokens_str = self._format_number(m.total_tokens)
        
        # Calculate projected total based on current average
        if m.completed_scenarios > 0:
            avg_tokens_per_scenario = m.total_tokens / m.completed_scenarios
            projected_total = int(avg_tokens_per_scenario * m.total_scenarios)
            projected_str = self._format_number(projected_total)
        else:
            projected_str = "estimating..."
        
        # Build progress bar
        bar_width = 30
        filled = int(bar_width * m.percent_complete / 100)
        bar = "█" * filled + "░" * (bar_width - filled)
        
        # Build status line
        status_parts = [
            f"{bar}",
            f"{m.percent_complete:5.1f}%",
            f"│ {m.completed_scenarios}/{m.total_scenarios} scenarios",
        ]
        
        if m.in_progress > 0:
            status_parts.append(f"│ {m.in_progress} active")
        
        if m.failed_scenarios > 0:
            status_parts.append(f"│ ⚠️  {m.failed_scenarios} failed")
        
        status_parts.extend([
            f"│ ⏱  {elapsed_str}",
            f"│ ETA {eta_str}",
            f"│ 🎫 {tokens_str}",
            f"→ {projected_str} projected"
        ])
        
        status_line = " ".join(status_parts)
        
        # Clear line and print (stay on same line)
        sys.stdout.write(f"\r{' ' * 200}\r")  # Clear
        sys.stdout.write(status_line)
        sys.stdout.flush()
    
    def finish(self, output_dir: str, logs_dir: Optional[str] = None, jsonl_path: Optional[str] = None):
        """Finish progress tracking and show summary.
        
        Args:
            output_dir: Path to output directory
            logs_dir: Optional path to logs directory
            jsonl_path: Optional path to JSONL observability file
        """
        if not self.enabled:
            return
        
        # Clear progress line
        sys.stdout.write(f"\r{' ' * 200}\r")
        sys.stdout.flush()
        
        m = self.metrics
        
        # Print summary
        print("\n" + "=" * 80)
        print("📊 BENCHMARK SUMMARY")
        print("=" * 80)
        print(f"Scenarios:        {m.completed_scenarios}/{m.total_scenarios} completed")
        
        if m.failed_scenarios > 0:
            print(f"Failed:           {m.failed_scenarios} ({m.failed_scenarios/m.total_scenarios*100:.1f}%)")
        
        print(f"Duration:         {self._format_duration(m.elapsed_seconds)}")
        print(f"Throughput:       {m.completion_rate:.2f} scenarios/sec")
        
        print(f"\nToken Usage:")
        print(f"  Input tokens:   {self._format_number(m.total_tokens_input)}")
        print(f"  Output tokens:  {self._format_number(m.total_tokens_output)}")
        print(f"  Total tokens:   {self._format_number(m.total_tokens)}")
        
        # Cost estimation (Gemini pricing as example)
        # vertex_ai/gemini-3-pro-preview: ~$0.10/1M input, ~$0.30/1M output
        cost_input = (m.total_tokens_input / 1_000_000) * 0.10
        cost_output = (m.total_tokens_output / 1_000_000) * 0.30
        total_cost = cost_input + cost_output
        print(f"  Estimated cost: ${total_cost:.4f}")
        
        print(f"\nOutput:")
        print(f"  Results:        {output_dir}/results.csv")
        print(f"  Plots:          {output_dir}/plots/")
        
        if logs_dir:
            print(f"  Logs:           {logs_dir}")
        
        if jsonl_path:
            print(f"  Observability:  {jsonl_path}")
        
        print("=" * 80 + "\n")
    
    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format duration as HH:MM:SS or MM:SS."""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            mins = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{mins}m{secs:02d}s"
        else:
            hours = int(seconds // 3600)
            mins = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            return f"{hours}h{mins:02d}m{secs:02d}s"
    
    @staticmethod
    def _format_number(num: int) -> str:
        """Format number with K/M suffix."""
        if num >= 1_000_000:
            return f"{num/1_000_000:.2f}M"
        elif num >= 1_000:
            return f"{num/1_000:.1f}K"
        else:
            return str(num)
