#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Generic output formatter for tabular data.

Supports multiple output formats (table, csv, json, markdown, etc.)
using tabulate for consistent formatting across components.
"""

import csv
import json
import sys
from enum import Enum
from io import StringIO
from typing import Any, Dict, List, Optional, Union

try:
    from tabulate import tabulate
except ImportError:
    tabulate = None


class OutputFormat(str, Enum):
    """Supported output formats."""
    
    # Table formats
    SIMPLE = "simple"       # Simple table (default)
    PLAIN = "plain"         # Plain text columns
    GRID = "grid"           # Full grid with borders
    PIPE = "pipe"           # Markdown-style pipes
    MARKDOWN = "markdown"   # Markdown table
    
    # Data formats
    CSV = "csv"             # Comma-separated values
    TSV = "tsv"             # Tab-separated values
    JSON = "json"           # JSON array of objects
    JSONL = "jsonl"         # JSON lines (one object per line)


class OutputFormatter:
    """Format tabular data for display or export.
    
    Examples:
        >>> data = [
        ...     {"id": "abc123", "status": "running", "progress": "50%"},
        ...     {"id": "def456", "status": "completed", "progress": "100%"},
        ... ]
        >>> formatter = OutputFormatter(format="simple")
        >>> print(formatter.format(data))
        
        >>> # Export to CSV
        >>> formatter = OutputFormatter(format="csv")
        >>> print(formatter.format(data))
    """
    
    def __init__(self, format: Union[str, OutputFormat] = OutputFormat.SIMPLE):
        """Initialize formatter.
        
        Args:
            format: Output format (simple, csv, json, etc.)
        """
        if isinstance(format, str):
            format = OutputFormat(format)
        self.output_format = format
    
    def format(
        self,
        data: List[Dict[str, Any]],
        columns: Optional[List[str]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> str:
        """Format data to string.
        
        Args:
            data: List of dictionaries
            columns: Column keys to include (None = all, in data order)
            headers: Map of column key -> display name (None = use keys)
            
        Returns:
            Formatted string
        """
        if not data:
            return ""
        
        # Determine columns
        if columns is None:
            columns = list(data[0].keys())
        
        # Determine headers
        if headers is None:
            headers = {col: col for col in columns}
        
        # Extract values in column order
        rows = [[row.get(col, "") for col in columns] for row in data]
        header_row = [headers.get(col, col) for col in columns]
        
        # Format based on type
        if self.output_format in (OutputFormat.SIMPLE, OutputFormat.PLAIN, OutputFormat.GRID, 
                          OutputFormat.PIPE, OutputFormat.MARKDOWN):
            return self._format_table(rows, header_row)
        
        elif self.output_format == OutputFormat.CSV:
            return self._format_csv(rows, header_row)
        
        elif self.output_format == OutputFormat.TSV:
            return self._format_tsv(rows, header_row)
        
        elif self.output_format == OutputFormat.JSON:
            return self._format_json(data, columns)
        
        elif self.output_format == OutputFormat.JSONL:
            return self._format_jsonl(data, columns)
        
        else:
            raise ValueError(f"Unknown format: {self.output_format}")
    
    def _format_table(self, rows: List[List[Any]], headers: List[str]) -> str:
        """Format as table using tabulate."""
        if tabulate is None:
            raise ImportError(
                "tabulate is required for table formatting. "
                "Install with: uv add tabulate"
            )
        
        # Map our format names to tabulate's tablefmt
        tablefmt_map = {
            OutputFormat.SIMPLE: "simple",
            OutputFormat.PLAIN: "plain",
            OutputFormat.GRID: "grid",
            OutputFormat.PIPE: "pipe",
            OutputFormat.MARKDOWN: "pipe",  # Markdown uses pipe format
        }
        
        tablefmt = tablefmt_map.get(self.output_format, "simple")
        return tabulate(rows, headers=headers, tablefmt=tablefmt)
    
    def _format_csv(self, rows: List[List[Any]], headers: List[str]) -> str:
        """Format as CSV."""
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
        return output.getvalue()
    
    def _format_tsv(self, rows: List[List[Any]], headers: List[str]) -> str:
        """Format as TSV."""
        output = StringIO()
        writer = csv.writer(output, delimiter="\t")
        writer.writerow(headers)
        writer.writerows(rows)
        return output.getvalue()
    
    def _format_json(self, data: List[Dict[str, Any]], columns: List[str]) -> str:
        """Format as JSON array."""
        # Filter to requested columns
        filtered = [{k: v for k, v in row.items() if k in columns} for row in data]
        return json.dumps(filtered, indent=2, default=str)
    
    def _format_jsonl(self, data: List[Dict[str, Any]], columns: List[str]) -> str:
        """Format as JSON lines."""
        lines = []
        for row in data:
            filtered = {k: v for k, v in row.items() if k in columns}
            lines.append(json.dumps(filtered, default=str))
        return "\n".join(lines)


def format_table(
    data: List[Dict[str, Any]],
    format: Union[str, OutputFormat] = OutputFormat.SIMPLE,
    columns: Optional[List[str]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> str:
    """Convenience function to format data.
    
    Args:
        data: List of dictionaries
        format: Output format (simple, csv, json, etc.)
        columns: Column keys to include (None = all)
        headers: Map of column key -> display name (None = use keys)
        
    Returns:
        Formatted string
        
    Examples:
        >>> data = [{"id": "abc", "status": "ok"}]
        >>> print(format_table(data, format="simple"))
        >>> print(format_table(data, format="csv"))
        >>> print(format_table(data, format="json"))
    """
    formatter = OutputFormatter(format=format)
    return formatter.format(data, columns=columns, headers=headers)
