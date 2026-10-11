"""
Minimal working FastMCP + KLayout example.

Tools:
- get_layout_info: Read GDS/OAS and return basic cell / layer / bbox info
- run_drc: Run a KLayout .drc script in batch mode and return output summary
- translate_laker_tf: Convert Laker Technology File (.tf) to KLayout layer properties (.lyp)
  and connectivity rules for consistent net tracing

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
import re
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

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


def _pretty_xml(elem: Element) -> str:
    """Return pretty-printed XML string."""
    rough = tostring(elem, encoding="utf-8")
    reparsed = minidom.parseString(rough)
    return reparsed.toprettyxml(indent="  ")


def parse_laker_tf(tf_content: str) -> tuple[list[dict], list[dict]]:
    """
    Parse Laker Technology File for layers and connectivity.

    Returns:
        layers: list of layer mappings
        connections: list of connection rules (for net tracing)
    """
    layers = []
    connections = []

    # Layer mapping pattern
    layer_pattern = re.compile(
        r"def\s*\{\s*(\w+)\s+(\w+)\s+(\d+)(?:\s+(\d+))?",
        re.IGNORECASE
    )

    for match in layer_pattern.finditer(tf_content):
        layer_name = match.group(1)
        purpose = match.group(2)
        gds_layer = int(match.group(3))
        gds_datatype = int(match.group(4)) if match.group(4) else 0

        key = (layer_name, purpose)
        existing = next((l for l in layers if (l["layer_name"], l["purpose"]) == key), None)
        if existing:
            existing["gds_layer"] = gds_layer
            existing["gds_datatype"] = gds_datatype
        else:
            layers.append({
                "layer_name": layer_name,
                "purpose": purpose,
                "gds_layer": gds_layer,
                "gds_datatype": gds_datatype,
                "display_name": f"{layer_name}.{purpose}"
            })

    # Simple connectivity heuristics (common metal/via stacking)
    # Look for sequential metal layers or via-related names
    metal_layers = [l for l in layers if re.search(r"metal|met|m\d+", l["layer_name"], re.I)]
    via_layers = [l for l in layers if re.search(r"via|cont|contact", l["layer_name"], re.I)]

    # Example: connect consecutive metals through vias if names suggest it
    for i, metal in enumerate(metal_layers):
        if i + 1 < len(metal_layers):
            next_metal = metal_layers[i + 1]
            # Try to find a matching via
            via = next((v for v in via_layers if str(i + 1) in v["layer_name"] or "via" in v["layer_name"].lower()), None)
            if via:
                connections.append({
                    "from": f"{metal['gds_layer']}/{metal['gds_datatype']}",
                    "via": f"{via['gds_layer']}/{via['gds_datatype']}",
                    "to": f"{next_metal['gds_layer']}/{next_metal['gds_datatype']}",
                    "description": f"{metal['layer_name']} --{via['layer_name']}--> {next_metal['layer_name']}"
                })
            else:
                connections.append({
                    "from": f"{metal['gds_layer']}/{metal['gds_datatype']}",
                    "to": f"{next_metal['gds_layer']}/{next_metal['gds_datatype']}",
                    "description": f"{metal['layer_name']} --> {next_metal['layer_name']} (direct)"
                })

    return layers, connections


def generate_lyp(layers: list[dict]) -> str:
    """Generate a basic KLayout .lyp XML from layer mapping."""
    root = Element("layer-properties")

    for layer in layers:
        props = SubElement(root, "properties")
        SubElement(props, "frame-color").text = "#ff9d9d"
        SubElement(props, "fill-color").text = "#ff9d9d"
        SubElement(props, "frame-brightness").text = "0"
        SubElement(props, "fill-brightness").text = "0"
        SubElement(props, "dither-pattern").text = "I9"
        SubElement(props, "visible").text = "true"
        SubElement(props, "transparent").text = "false"
        SubElement(props, "width").text = "1"
        SubElement(props, "marked").text = "false"
        SubElement(props, "animation").text = "0"
        SubElement(props, "name").text = layer["display_name"]
        source = f"{layer['gds_layer']}/{layer['gds_datatype']}"
        SubElement(props, "source").text = source

    return _pretty_xml(root)


def generate_connectivity_txt(connections: list[dict]) -> str:
    """Generate a simple text description of connectivity for KLayout layer stack."""
    lines = ["# KLayout Connectivity Rules (generated from Laker TF)",
             "# Use these in Tools > Edit Layer Stack or NetTracerConnectivity"]
    for conn in connections:
        if "via" in conn:
            lines.append(f"connection: {conn['from']} --via({conn['via']})--> {conn['to']}  # {conn['description']}")
        else:
            lines.append(f"connection: {conn['from']} --> {conn['to']}  # {conn['description']}")
    return "\n".join(lines) + "\n"


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


@mcp.tool
def translate_laker_tf(tf_file: str, output_lyp: str = None, output_connectivity: str = None) -> dict:
    """
    Convert a Laker Technology File (.tf) into KLayout layer properties (.lyp)
    and connectivity rules for consistent net tracing.

    Extracts:
    - Layer names, purposes, GDS layer/datatype
    - Basic metal/via connectivity stacking (for Trace Net)

    Args:
        tf_file: Path to the Laker .tf file
        output_lyp: Optional path to write the .lyp file
        output_connectivity: Optional path to write a connectivity description (.txt)

    Returns:
        Mapping, connections, and output file paths.
    """
    try:
        path = _safe_path(tf_file)
        content = path.read_text(encoding="utf-8", errors="ignore")

        layers, connections = parse_laker_tf(content)

        if not layers:
            return {
                "status": "warning",
                "message": "No layers found. Check if the TF contains tfLayoutLayerTable or tfStreamIoTable sections.",
                "layers": [],
                "connections": []
            }

        result = {
            "status": "ok",
            "input_file": str(path),
            "num_layers": len(layers),
            "num_connections": len(connections),
            "layers": layers,
            "connections": connections
        }

        if output_lyp:
            lyp_path = Path(output_lyp).expanduser().resolve()
            lyp_path.parent.mkdir(parents=True, exist_ok=True)
            lyp_content = generate_lyp(layers)
            lyp_path.write_text(lyp_content, encoding="utf-8")
            result["output_lyp"] = str(lyp_path)

        if output_connectivity:
            conn_path = Path(output_connectivity).expanduser().resolve()
            conn_path.parent.mkdir(parents=True, exist_ok=True)
            conn_content = generate_connectivity_txt(connections)
            conn_path.write_text(conn_content, encoding="utf-8")
            result["output_connectivity"] = str(conn_path)

        if output_lyp or output_connectivity:
            result["message"] = "Generated layer properties and/or connectivity rules."

        return result

    except Exception as e:
        return {"error": str(e), "status": "error"}


if __name__ == "__main__":
    mcp.run()
