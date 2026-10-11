"""
Minimal FastMCP skeleton for KLayout layout tools.

Install:
  pip install fastmcp klayout

Run (stdio for Claude Desktop / Claude Code / Cursor):
  python src/server.py
"""

from fastmcp import FastMCP
import os

mcp = FastMCP("klayout-pcell")

# TODO: implement with pya / klayout.db
# Example stubs below

@mcp.tool
def get_layout_info(file_path: str, top_cell: str = None) -> dict:
    """Read basic information about a GDS/OAS layout."""
    # Placeholder
    return {
        "status": "not_implemented",
        "file": file_path,
        "note": "Implement with pya.Layout().read()"
    }

@mcp.tool
def run_drc(layout_file: str, drc_script: str) -> dict:
    """Execute a KLayout DRC script and return structured results."""
    return {
        "status": "not_implemented",
        "note": "Call klayout -b -r or use pya DRC API"
    }

if __name__ == "__main__":
    mcp.run()
