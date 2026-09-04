#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Format AGENT↔LLM↔TOOL exchange lines for CLI trace output.

Color semantics for CLI trace output:
  - Agent: cyan (#0e7490)
  - LLM: orange (#ea580c)
  - Tool: green (#16a34a)
  - Processing: slate (#64748b)
"""

from __future__ import annotations

import json
import logging
import re
import sys
from dataclasses import dataclass
from typing import Any

from mas.runtime.boundary.obs.exchange_plugin import ExchangePlugin
from mas.runtime.driver.driver import ExchangeRecord

# ANSI color codes for CLI trace output
_COLORS = {
    "agent": "\033[36m",      # cyan
    "llm": "\033[33m",        # orange/yellow
    "tool": "\033[32m",       # green
    "processing": "\033[90m", # slate/gray
    "user": "\033[37m",       # white (user input)
    "reset": "\033[0m",       # reset
}

def _colorize(text: str, color_key: str) -> str:
    """Apply color to text if color support is enabled."""
    # Note: actual color enablement is checked at format time
    return f"{_COLORS.get(color_key, '')}{text}{_COLORS['reset']}"


@dataclass(frozen=True)
class TraceFormatOptions:
    timestamps: bool = False
    engine_io: bool = False
    summary_only: bool = False
    turn_start_mono: float = 0.0
    color: bool = False  # Use ANSI color codes for visual separation
    agent_name: str = "agent"  # Identity name for agent
    tool_name: str | None = None  # Identity name for tool (extracted from exchange)
    llm_name: str = "LLM"  # Identity name for LLM


def print_exchange(
    ex: ExchangeRecord,
    *,
    err: object = sys.stderr,
    agent_id: str = "agent",
    fmt: TraceFormatOptions | None = None,
) -> None:
    """Write one exchange block (streaming trace)."""
    write = getattr(err, "write", None)
    flush = getattr(err, "flush", None)
    if not callable(write):
        return
    block = format_exchange(agent_id, ex, fmt=fmt)
    write(block)
    if block and not block.endswith("\n"):
        write("\n")
    if callable(flush):
        flush()


def format_exchange(
    agent_id: str,
    ex: ExchangeRecord,
    *,
    fmt: TraceFormatOptions | None = None,
) -> str:
    opts = fmt or TraceFormatOptions()
    
    # Summary mode: ultra-compact single-line format
    if opts.summary_only:
        parts = []
        
        # 1. Timestamp: offset + optional wall-clock
        if ex.ts_mono and opts.turn_start_mono:
            offset = ex.ts_mono - opts.turn_start_mono
            ts_str = f"+{offset:.3f}s"
            # Add wall-clock if --trace-timestamps is set
            if opts.timestamps and ex.ts_wall:
                ts_str += f" [{ex.ts_wall}]"
            if opts.color:
                parts.append(f"\033[90m{ts_str}\033[0m")  # gray
            else:
                parts.append(ts_str)
        
        # 2. Header with arrows and identities
        header = _exchange_header_simple(ex.tag, opts.agent_name, detail=ex.detail, use_colors=opts.color, llm_name=opts.llm_name)
        parts.append(header)
        
        # 3. Cleaned detail (minimal info, no redundant prefixes)
        if ex.detail:
            detail = _clean_detail_for_summary(ex.detail, tag=ex.tag)
            if detail:
                if opts.color:
                    parts.append(f"\033[90m{detail}\033[0m")  # gray for metadata
                else:
                    parts.append(detail)
        
        # 4. Content (cleaned and truncated to one line)
        text = ex.text.strip().replace("\n", " ")
        
        # For TOOL calls, preserve args (actual data being passed to tool)
        # For LLM calls, remove tool metadata that shouldn't be there
        is_tool_call = "TOOL" in ex.tag
        
        # Remove metadata markers and prefixes that clutter summary output
        # - Role/type tags in brackets: [user], [assistant], [tools], [tool call_*], etc.
        text = re.sub(r'\[[\w\s_\-=]*\]', '', text)
        
        if is_tool_call:
            # For TOOL calls: preserve the args (that's the actual data)
            # Just clean up the metadata prefixes
            text = re.sub(r'\b(?:content|id|name)=[\w\d\-_]*', '', text)
            text = re.sub(r'(?:content|tool_call|tool_calls|next_step|name):\s*', '', text)
            # Keep tool= and args= for TOOL calls (that's the data)
            # But clean up tool name repeated at the start if present
            text = re.sub(r'^tool=[\w\-_]*\s*', '', text)  # Remove leading tool name
            text = re.sub(r'^\S+\s+(?={)', '', text)  # Remove word before opening brace (e.g., "web-search {")
            text = re.sub(r'\s*args=', '', text)  # Remove args= prefix, keep just the JSON
        else:
            # For LLM calls: remove tool-related metadata
            # - Metadata key=value pairs: content=..., id=call_1, name=web-search, etc.
            text = re.sub(r'\b(?:content|id|name|args)=[\w\d\-_]*', '', text)
            # - Metadata with colons: content:, name:, tool_call:, etc. 
            text = re.sub(r'(?:content|tool_call|tool_calls|next_step|name):\s*', '', text)
            # - Tool reference prefix (remove tool mentions from LLM exchanges)
            text = re.sub(r'\bweb-search\b', '', text)  # Remove tool names
            text = re.sub(r'\btool=[\w\-_]*', '', text)
            text = re.sub(r'\[tools?(?:\s+[^\]]*)?\]', '', text)  # Remove [tools] mentions
        
        # - Metadata in parentheses like (included in API payload)
        text = re.sub(r'\s*\([^)]*(?:payload|included|API)[^)]*\)\s*', ' ', text)
        # - Separator characters that are now orphaned: dashes, hyphens
        text = re.sub(r'\s*-\s+(\w)', r' \1', text)  # Remove dash between items (dash + space + word)
        text = re.sub(r'\s*-\s*$', '', text)  # Remove trailing dash
        # Normalize whitespace
        text = ' '.join(text.split())
        
        if text:
            if len(text) > 70:
                text = text[:67] + "..."
            if opts.color:
                parts.append(f"\033[37m{text}\033[0m")  # white
            else:
                parts.append(text)
        
        return " ".join(parts)
    
    # Detail mode: multi-line (unchanged)
    lines: list[str] = []
    header = _exchange_header(ex.tag, agent_id)
    
    if opts.timestamps and ex.ts_wall:
        delta = ""
        if ex.ts_mono and opts.turn_start_mono:
            delta = f" (+{ex.ts_mono - opts.turn_start_mono:.3f}s)"
        lines.append(f"{header}  {ex.ts_wall}{delta}")
    else:
        lines.append(header)
    if ex.detail:
        lines.append(f"  {ex.detail}")
    if opts.engine_io and ex.engine_raw.strip():
        lines.append("  engine:")
        for line in ex.engine_raw.strip().splitlines():
            lines.append(f"    {line}")
    if ex.text.strip():
        for line in ex.text.splitlines():
            lines.append(f"  {line}")
    return "\n".join(lines) + "\n"


class CliTraceExchangePlugin(ExchangePlugin):
    """ExchangePlugin driving mas-ctl's own --trace/--verbose stdout/log output.

    One persistent instance per SessionController, subscribed exactly once
    via KernelDriver.subscribe_exchange() (see
    SessionController._setup_exchange_tracing()) instead of being rebuilt
    and reassigned to a single driver.on_exchange callback every turn —
    per-turn state (trace/verbose toggles, turn_start_mono baseline) is
    updated in place via configure(), so subscribing only ever happens once
    per controller/driver pair, and other subscribers (e.g. a chat-UI
    plugin) are never silently discarded.
    """

    def __init__(self) -> None:
        self.enabled = False
        self.trace = False
        self.verbose = 0
        self.agent_id = "agent"
        self.fmt = TraceFormatOptions()
        self._logger = logging.getLogger("mas.runtime")

    def configure(
        self,
        *,
        trace: bool,
        verbose: int,
        agent_id: str,
        fmt: TraceFormatOptions,
    ) -> None:
        self.enabled = trace or verbose >= 1
        self.trace = trace
        self.verbose = verbose
        self.agent_id = agent_id
        self.fmt = fmt

    def on_exchange(self, record: ExchangeRecord) -> None:
        if not self.enabled:
            return
        # Realtime stderr output (if --trace) — primary display path
        if self.trace:
            print_exchange(record, err=sys.stderr, agent_id=self.agent_id, fmt=self.fmt)
        # Verbose logging only if NOT using --trace (alternative logging path)
        elif self.verbose >= 1:
            formatted = format_exchange(self.agent_id, record, fmt=self.fmt).strip()
            for line in formatted.splitlines():
                self._logger.info("[%s] %s", self.agent_id, line)



def _exchange_header_simple(tag: str, agent_id: str, detail: str = "", use_colors: bool = False, llm_name: str = "gpt-4o-mini") -> str:
    """Simple header for summary mode with identities and optional colors."""
    # Use the new header with identities
    header = _header_with_identities(tag, agent_id, detail, use_colors=use_colors, llm_name=llm_name)
    # Strip any ANSI codes if we're not using colors (fallback to plain)
    if not use_colors and "\033" in header:
        header = re.sub(r"\033\[[0-9;]*m", "", header)
    return header


def _clean_detail_for_summary(detail: str, tag: str = "") -> str:
    """Clean detail by removing all redundant prefixes, keeping only essential info.
    
    For LLM->AGENT exchanges where LLM is calling a tool, preserve tool name.
    For other exchanges, remove tool name since it's shown in the header.
    """
    if not detail:
        return ""
    
    detail = detail.replace("\n", " ").strip()
    
    # Remove correlation_id (trace context already carries this)
    detail = re.sub(r'\s*correlation_id=\d+\s*', ' ', detail)
    
    # Remove response_kind (redundant with header tag)
    detail = re.sub(r'\s*response_kind=[\w_]*\s*', ' ', detail)
    
    # Remove op= prefix (AGENT->LLM header already says it's an LLM call)
    detail = re.sub(r'\s*op=\w+\s*', ' ', detail)
    
    # Remove content: prefix (obvious from context)
    detail = re.sub(r'\s*content:\s*', ' ', detail)
    
    # Remove tool= prefix everywhere (it's redundant)
    detail = re.sub(r'\s*tool=', ' ', detail)
    
    # Remove args= prefix
    detail = re.sub(r'\s*args=\s*', ' ', detail)
    
    # Remove role tags: [user], [assistant], [tools], etc
    detail = re.sub(r'\s*\[\s*\w+(?:\s+\w+)*\s*\]\s*', ' ', detail)
    
    # Remove tool_call: prefix
    detail = re.sub(r'\s*tool_call:\s*', ' ', detail)
    detail = re.sub(r'\s*tool_calls:\s*', ' ', detail)
    
    # Normalize whitespace
    detail = ' '.join(detail.split())
    return detail



def _exchange_header(tag: str, agent_id: str) -> str:
    """Format exchange header with decorative borders."""
    if tag == "AGENT->LLM":
        return f"\n── AGENT → LLM ({agent_id}) ──"
    if tag == "LLM->AGENT":
        return f"\n── LLM → AGENT ({agent_id}) ──"
    if tag == "AGENT->TOOL":
        return f"\n── AGENT → TOOL ({agent_id}) ──"
    if tag == "TOOL->AGENT":
        return f"\n── TOOL → AGENT ({agent_id}) ──"
    if tag == "USER->AGENT":
        return f"\n── USER → AGENT ({agent_id}) ──"
    if tag == "AGENT->USER":
        return f"\n── AGENT → USER ({agent_id}) ──"
    return f"\n── {tag} ──"


def _parse_entity_from_detail(detail: str, entity_type: str) -> str | None:
    """Extract entity name from detail field (e.g., 'tool=web_search' → 'web_search')."""
    if not detail:
        return None
    # Look for pattern: tool=web_search, tool_name=web_search, etc.
    patterns = [
        rf"{entity_type}[_name]*=([\w\-]+)",
        rf"name=([\w\-]+).*{entity_type}",
    ]
    for pattern in patterns:
        match = re.search(pattern, detail)
        if match:
            return match.group(1)
    return None


def _header_with_identities(
    tag: str,
    agent_id: str,
    detail: str = "",
    *,
    use_colors: bool = False,
    llm_name: str = "gpt-4o-mini",
) -> str:
    """Format exchange header with entity identities and optional colors.
    
    Examples:
      AGENT[qa] -> LLM[gpt-4]
      AGENT[qa] -> TOOL[web-search]
      AGENT -> LLM[gpt-4]  (when agent has no identity)
      USER -> AGENT[qa]
      USER -> AGENT  (when agent has no identity)
      AGENT[qa] -> USER
    """
    # Normalize arrow
    tag = tag.replace("→", "->")
    
    # Parse entities from tag
    if "->" not in tag:
        return tag
    
    src, dst = tag.split("->", 1)
    src = src.strip()
    dst = dst.strip()
    
    # Extract identity names
    agent_name = agent_id or "agent"
    tool_name = _parse_entity_from_detail(detail, "tool")
    llm_name_to_use = llm_name or "gpt-4o-mini"
    user_name = "User"
    
    # Build header with identities
    def format_entity(entity: str) -> str:
        if entity == "AGENT":
            # Omit brackets if agent has no identity (n/a)
            if agent_name == "n/a":
                return "AGENT"
            return f"AGENT[{agent_name}]"
        elif entity == "USER":
            return "USER"
        elif entity == "LLM":
            return f"LLM[{llm_name_to_use}]"
        elif entity == "TOOL":
            if tool_name:
                return f"TOOL[{tool_name}]"
            return "TOOL"
        return entity
    
    src_fmt = format_entity(src)
    dst_fmt = format_entity(dst)
    
    if use_colors:
        # Apply entity-specific colors
        src_color = {"AGENT": "agent", "USER": "user", "LLM": "llm", "TOOL": "tool"}.get(
            src, "processing"
        )
        dst_color = {"AGENT": "agent", "USER": "user", "LLM": "llm", "TOOL": "tool"}.get(
            dst, "processing"
        )
        src_fmt = _colorize(src_fmt, src_color)
        dst_fmt = _colorize(dst_fmt, dst_color)
    
    return f"{src_fmt} -> {dst_fmt}"


def engine_payload_json(obj: Any) -> str:
    """Compact JSON for EngineIoReturn / InvokeEngineIo trace lines."""
    if hasattr(obj, "model_dump"):
        data = obj.model_dump(mode="json")
    elif isinstance(obj, dict):
        data = obj
    else:
        return str(obj)
    return json.dumps(data, ensure_ascii=False, indent=2)
