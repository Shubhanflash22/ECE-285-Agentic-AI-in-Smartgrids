"""
data/loader.py – Loads CSV files and converts them to readable LLM context strings.

For each CSV the loader produces:
  • Column names and dtypes
  • Optional descriptive statistics for numeric columns
  • A Markdown-formatted sample of the data (up to max_rows rows)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Try pandas; fall back to the stdlib csv module for minimal environments
try:
    import pandas as pd
    _HAS_PANDAS = True
except ImportError:
    _HAS_PANDAS = False
    import csv as _csv_stdlib


class CSVLoader:
    """
    Parameters
    ----------
    max_rows       : Maximum data rows to include in the context (default 200).
    include_stats  : If True, include descriptive stats for numeric columns.
    """

    def __init__(self, max_rows: int = 200, include_stats: bool = True):
        self.max_rows      = max_rows
        self.include_stats = include_stats

    # ─────────────────────────────────────────────────────────

    def load(self, path: str, label: str = "Dataset") -> str:
        """
        Load a CSV file and return a plain-text context block.

        Parameters
        ----------
        path  : Filesystem path to the CSV.
        label : Human-friendly name for the dataset (used in the output header).

        Returns
        -------
        str : Formatted context string ready to inject into the LLM prompt.
        """
        if _HAS_PANDAS:
            return self._load_pandas(path, label)
        else:
            return self._load_stdlib(path, label)

    # ─────────────────────────────────────────────────────────
    # Pandas implementation
    # ─────────────────────────────────────────────────────────

    def _load_pandas(self, path: str, label: str) -> str:
        df = pd.read_csv(path)
        lines = []

        lines.append(f"### {label}  ({Path(path).name})")
        lines.append(f"Shape: {df.shape[0]} rows × {df.shape[1]} columns")
        lines.append("")

        # Column overview
        lines.append("**Columns:**")
        for col in df.columns:
            dtype = str(df[col].dtype)
            n_null = int(df[col].isna().sum())
            lines.append(f"  - `{col}` ({dtype})  nulls={n_null}")
        lines.append("")

        # Numeric stats
        if self.include_stats:
            num_df = df.select_dtypes(include="number")
            if not num_df.empty:
                lines.append("**Numeric statistics:**")
                stats = num_df.describe().round(3)
                lines.append(stats.to_string())
                lines.append("")

        # Sample rows
        sample = df.head(self.max_rows)
        lines.append(f"**Data sample (first {len(sample)} rows):**")
        lines.append(sample.to_markdown(index=False) if hasattr(sample, "to_markdown") else sample.to_string(index=False))
        lines.append("")

        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────
    # stdlib fallback (no pandas)
    # ─────────────────────────────────────────────────────────

    def _load_stdlib(self, path: str, label: str) -> str:
        lines = []
        with open(path, newline="", encoding="utf-8") as f:
            reader = _csv_stdlib.DictReader(f)
            rows   = list(reader)

        headers = rows[0].keys() if rows else []
        sample  = rows[: self.max_rows]

        lines.append(f"### {label}  ({Path(path).name})")
        lines.append(f"Rows: {len(rows)}  |  Columns: {len(list(headers))}")
        lines.append("")
        lines.append("Columns: " + ", ".join(f"`{h}`" for h in headers))
        lines.append("")
        lines.append(f"Data sample (first {len(sample)} rows):")

        # Simple pipe-table
        col_list = list(headers)
        header_row = " | ".join(col_list)
        sep_row    = " | ".join(["---"] * len(col_list))
        lines.append(header_row)
        lines.append(sep_row)
        for row in sample:
            lines.append(" | ".join(str(row.get(c, "")) for c in col_list))

        lines.append("")
        return "\n".join(lines)
