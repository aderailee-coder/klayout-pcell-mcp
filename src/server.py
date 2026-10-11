"""
Minimal working FastMCP + KLayout example.

Tools:
- get_layout_info: Read GDS/OAS and return basic cell / layer / bbox info
- run_drc: Run a KLayout .drc script in batch mode and return output summary

Requirements:
  pip install fastmcp klayout

Also needs the `klayout` executable on PATH (for run_drc).
You can set KLAYOUT_BIN to the full path if needed.

Usage with Claude Code / Cloud Code (stdio):
  Add to your MCP config:
  {
    "mcpServers": {
      "klayout": {
        "command": "python",
        "args": ["/absolute/path/to/src/server.py"]
      }
    }
  }
"""

import os
import subprocess
import tempfile
import json
from pathlib import Path

from fastmcp import FastMCP

try:
    import klayout.db as db
except ImportError:
    db = None

mcp = FastMCP("klayout-pcell")

KLAYOUT_BIN = os.environ.get("KLAYOUT_BIN", "klayout")


def _safe_path(path: str) -> Path:
    """Basic path safety check (extend with allowlists later)."""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")
    return p


@mcp.tool
def get_layout_info(file_path: str, top_cell: str = None) -> dict:
    """
    Read a GDS/OAS layout and return basic information.

    Args:
        file_path: Path to .gds or .oas file
        top_cell: Optional specific top cell name (default: first top cell)

    Returns:
        dict with cells, layers, database unit, bounding box, etc.
    """
    if db is None:
        return {"error": "klayout Python package not installed. Run: pip install klayout"}

    try:
        path = _safe_path(file_path)
        layout = db.Layout()
        layout.read(str(path))

        # Top cells
        top_cells = [c.name for c in layout.top_cells()]
        selected_top = top_cell if top_cell and layout.cell(top_cell) else (top_cells[0] if top_cells else None)

        # Layers
        layers = []
        for li in layout.layer_indexes():
            info = layout.get_info(li)
            layers.append({
                "layer": info.layer,
                "datatype": info.datatype,
                "name": info.name or ""
            })

        # Bounding box of selected top cell (in microns)
        bbox = None
        if selected_top:
            cell = layout.cell(selected_top)
            if cell:
                bb = cell.dbbox()
                bbox = {
                    "left": bb.left,
                    "bottom": bb.bottom,
                    "right": bb.right,
                    "top": bb.top,
                    "width": bb.width(),
                    "height": bb.height()
                }

        # All cell names (limited)
        all_cells = [c.name for c in layout.each_cell()][:50]

        return {
            "file": str(path),
            "dbu": layout.dbu,
            "top_cells": top_cells,
            "selected_top_cell": selected_top,
            "num_cells": layout.cells(),
            "layers": layers,
            "bounding_box_um": bbox,
            "sample_cells": all_cells,
            "status": "ok"
        }
    except Exception as e:
        return {"error": str(e), "status": "error"}


@mcp.tool
def run_drc(layout_file: str, drc_script: str, top_cell: str = None) -> dict:
    """
    Run a KLayout DRC script in batch mode.

    The DRC script should use $input and $report variables, for example:

        source($input)
        report("DRC", $report)
        # ... your checks ...
        # input(1,0).width(0.1).output("width")

    Args:
        layout_file: Path to GDS/OAS
        drc_script: Path to .drc file
        top_cell: Optional top cell name

    Returns:
        Command output, report path, and basic status.
    """
    try:
        layout_path = _safe_path(layout_file)
        script_path = _safe_path(drc_script)

        # Temporary report file
        with tempfile.NamedTemporaryFile(suffix=".lyrdb", delete=False) as tmp:
            report_path = tmp.name

        cmd = [
            KLAYOUT_BIN,
            "-b",                     # batch mode
            "-r", str(script_path),
            "-rd", f"input={layout_path}",
            "-rd", f"report={report_path}",
        ]
        if top_cell:
            cmd.extend(["-rd", f"topcell={top_cell}"])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )

        # Simple summary (full parsing of .lyrdb can be added later)
        report_exists = Path(report_path).exists() and Path(report_path).stat().st_size > 0

        return {
            "status": "ok" if result.returncode == 0 else "error",
            "returncode": result.returncode,
            "stdout": result.stdout[-2000:] if result.stdout else "",
            "stderr": result.stderr[-2000:] if result.stderr else "",
            "report_file": report_path if report_exists else None,
            "report_generated": report_exists,
            "command": " ".join(cmd)
        }
    except Exception as e:
        return {"error": str(e), "status": "error"}


if __name__ == "__main__":
    mcp.run()
