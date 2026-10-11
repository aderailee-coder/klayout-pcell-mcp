"""
FastMCP + KLayout Server with Laker TF to Technology support.

Tools:
- get_layout_info: Read GDS/OAS and return basic cell / layer / bbox info
- run_drc: Run a KLayout .drc script in batch mode
- translate_laker_tf: Convert Laker TF to layer mapping + connectivity (lightweight)
- generate_klayout_technology: Full conversion to .lyp + .lyt (with connectivity) + connectivity.txt
- klayout_tech: Alias of generate_klayout_technology (preferred name)

Requirements:
  pip install fastmcp klayout

Usage with Claude Code / Cloud Code (stdio):
  {
    "mcpServers": {
      "klayout": {
        "command": "python3",
        "args": ["/absolute/path/to/src/server.py"]
      }
    }
  }
"""

import os
import subprocess
import tempfile
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
    """Basic path safety check."""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")
    return p


def _pretty_xml(elem: Element) -> str:
    rough = tostring(elem, encoding="utf-8")
    reparsed = minidom.parseString(rough)
    return reparsed.toprettyxml(indent="  ")


def _extract_block(content: str, block_name: str) -> str:
    pattern = re.compile(
        rf"{re.escape(block_name)}\s*\{{([^}}]*)\}}",
        re.IGNORECASE | re.DOTALL
    )
    match = pattern.search(content)
    return match.group(1) if match else ""


def parse_laker_tf(tf_content: str) -> tuple[list[dict], list[dict]]:
    layers = []
    layer_lookup = {}

    stream_block = _extract_block(tf_content, "tfStreamIoTable")
    layer_block = _extract_block(tf_content, "tfLayoutLayerTable")

    stream_pattern = re.compile(
        r"def\s*\{\s*(\w+)\s+(\w+)\s+(\d+)\s+(\d+)",
        re.IGNORECASE
    )
    for match in stream_pattern.finditer(stream_block or tf_content):
        layer_name = match.group(1)
        purpose = match.group(2)
        gds_layer = int(match.group(3))
        gds_datatype = int(match.group(4))

        entry = {
            "layer_name": layer_name,
            "purpose": purpose,
            "gds_layer": gds_layer,
            "gds_datatype": gds_datatype,
            "display_name": f"{layer_name}.{purpose}"
        }
        layers.append(entry)
        layer_lookup[(layer_name.lower(), purpose.lower())] = entry
        layer_lookup[layer_name.lower()] = entry

    if not layers and layer_block:
        layout_pattern = re.compile(
            r"def\s*\{\s*(\w+)\s+(\w+)\s+(\d+)",
            re.IGNORECASE
        )
        for match in layout_pattern.finditer(layer_block):
            layer_name = match.group(1)
            purpose = match.group(2)
            gds_layer = int(match.group(3))

            entry = {
                "layer_name": layer_name,
                "purpose": purpose,
                "gds_layer": gds_layer,
                "gds_datatype": 0,
                "display_name": f"{layer_name}.{purpose}"
            }
            layers.append(entry)
            layer_lookup[(layer_name.lower(), purpose.lower())] = entry
            layer_lookup[layer_name.lower()] = entry

    connections = []
    conn_block = _extract_block(tf_content, "tfLayoutConnection")
    if conn_block:
        conn_pattern = re.compile(
            r"def\s*\{\s*(\w+)\s+(\w+)\s+(\w+)(?:\s+(\w+))?",
            re.IGNORECASE
        )
        for match in conn_pattern.finditer(conn_block):
            layer1 = match.group(1)
            layer2 = match.group(2)
            via = match.group(3)
            extra = match.group(4)

            def resolve(name: str):
                key = name.lower()
                if key in layer_lookup:
                    return layer_lookup[key]
                if (key, "drawing") in layer_lookup:
                    return layer_lookup[(key, "drawing")]
                return None

            l1 = resolve(layer1)
            l2 = resolve(layer2)
            v = resolve(via)

            if l1 and l2 and v:
                connections.append({
                    "from_layer": layer1,
                    "from": f"{l1['gds_layer']}/{l1['gds_datatype']}",
                    "via_layer": via,
                    "via": f"{v['gds_layer']}/{v['gds_datatype']}",
                    "to_layer": layer2,
                    "to": f"{l2['gds_layer']}/{l2['gds_datatype']}",
                    "extra": extra,
                    "description": f"{layer1} --{via}--> {layer2}" + (f" ({extra})" if extra else "")
                })

    return layers, connections


def generate_lyp(layers: list[dict]) -> str:
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
        SubElement(props, "source").text = f"{layer['gds_layer']}/{layer['gds_datatype']}"
    return _pretty_xml(root)


def generate_connectivity_txt(connections: list[dict]) -> str:
    lines = [
        "# Connectivity rules generated from Laker tfLayoutConnection",
        "# Also embedded in the .lyt file"
    ]
    for conn in connections:
        lines.append(
            f"connection: {conn['from']} --via({conn['via']})--> {conn['to']}  # {conn['description']}"
        )
    return "\n".join(lines) + "\n"


def generate_lyt(tech_name: str, lyp_filename: str, connections: list[dict]) -> str:
    symbols = {}
    for c in connections:
        symbols[c["from_layer"]] = c["from"]
        symbols[c["to_layer"]] = c["to"]
        symbols[c["via_layer"]] = c["via"]

    conn_xml = [
        f"    <connection>{c['from_layer']},{c['via_layer']},{c['to_layer']}</connection>"
        for c in connections
    ]
    symbol_xml = [
        f"    <symbols>{name}='{expr}'</symbols>"
        for name, expr in sorted(symbols.items())
    ]

    connectivity_block = ""
    if conn_xml or symbol_xml:
        connectivity_block = "\n  <connectivity>\n" + "\n".join(conn_xml + symbol_xml) + "\n  </connectivity>"

    return f'''<?xml version="1.0" encoding="utf-8"?>
<technology>
  <name>{tech_name}</name>
  <description>Generated from Laker Technology File</description>
  <group></group>
  <dbu>0.001</dbu>
  <base-path>$(appdata_path)/tech/{tech_name}</base-path>
  <original-base-path>$(appdata_path)/tech/{tech_name}</original-base-path>
  <layer-properties_file>{lyp_filename}</layer-properties_file>
  <add-other-layers>true</add-other-layers>
  <reader-options>
    <gds2>
      <create-other-layers>true</create-other-layers>
    </gds2>
  </reader-options>{connectivity_block}
</technology>
'''


def _generate_tech_files(tf_file: str, output_dir: str, tech_name: str) -> dict:
    """Shared implementation for technology file generation."""
    path = _safe_path(tf_file)
    content = path.read_text(encoding="utf-8", errors="ignore")
    layers, connections = parse_laker_tf(content)

    if not layers:
        return {
            "status": "warning",
            "message": "No layers found in TF.",
            "num_layers": 0,
            "num_connections": 0
        }

    out_dir = Path(output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    lyp_file = out_dir / f"{tech_name}.lyp"
    lyt_file = out_dir / f"{tech_name}.lyt"
    conn_file = out_dir / "connectivity.txt"

    lyp_file.write_text(generate_lyp(layers), encoding="utf-8")
    conn_file.write_text(generate_connectivity_txt(connections), encoding="utf-8")
    lyt_file.write_text(generate_lyt(tech_name, lyp_file.name, connections), encoding="utf-8")

    return {
        "status": "ok",
        "input_file": str(path),
        "tech_name": tech_name,
        "output_dir": str(out_dir),
        "num_layers": len(layers),
        "num_connections": len(connections),
        "files": {
            "lyp": str(lyp_file),
            "lyt": str(lyt_file),
            "connectivity": str(conn_file)
        },
        "install_hint": f"mkdir -p ~/.klayout/tech/{tech_name} && cp {out_dir}/* ~/.klayout/tech/{tech_name}/",
        "open_hint": f"klayout your_design.gds -t {tech_name}"
    }


@mcp.tool
def get_layout_info(file_path: str, top_cell: str = None) -> dict:
    """Read a GDS/OAS layout and return basic information."""
    if db is None:
        return {"error": "klayout Python package not installed. Run: pip install klayout"}

    try:
        path = _safe_path(file_path)
        layout = db.Layout()
        layout.read(str(path))

        top_cells = [c.name for c in layout.top_cells()]
        selected_top = top_cell if top_cell and layout.cell(top_cell) else (top_cells[0] if top_cells else None)

        layers = []
        for li in layout.layer_indexes():
            info = layout.get_info(li)
            layers.append({
                "layer": info.layer,
                "datatype": info.datatype,
                "name": info.name or ""
            })

        bbox = None
        if selected_top:
            cell = layout.cell(selected_top)
            if cell:
                bb = cell.dbbox()
                bbox = {
                    "left": bb.left, "bottom": bb.bottom,
                    "right": bb.right, "top": bb.top,
                    "width": bb.width(), "height": bb.height()
                }

        return {
            "file": str(path),
            "dbu": layout.dbu,
            "top_cells": top_cells,
            "selected_top_cell": selected_top,
            "num_cells": layout.cells(),
            "layers": layers,
            "bounding_box_um": bbox,
            "status": "ok"
        }
    except Exception as e:
        return {"error": str(e), "status": "error"}


@mcp.tool
def run_drc(layout_file: str, drc_script: str, top_cell: str = None) -> dict:
    """Run a KLayout DRC script in batch mode."""
    try:
        layout_path = _safe_path(layout_file)
        script_path = _safe_path(drc_script)

        with tempfile.NamedTemporaryFile(suffix=".lyrdb", delete=False) as tmp:
            report_path = tmp.name

        cmd = [
            KLAYOUT_BIN, "-b", "-r", str(script_path),
            "-rd", f"input={layout_path}",
            "-rd", f"report={report_path}",
        ]
        if top_cell:
            cmd.extend(["-rd", f"topcell={top_cell}"])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
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
    Lightweight conversion: Laker TF → layer mapping + connectivity data.
    Optionally writes .lyp and connectivity.txt.
    """
    try:
        path = _safe_path(tf_file)
        content = path.read_text(encoding="utf-8", errors="ignore")
        layers, connections = parse_laker_tf(content)

        if not layers:
            return {
                "status": "warning",
                "message": "No layers found.",
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
            lyp_path.write_text(generate_lyp(layers), encoding="utf-8")
            result["output_lyp"] = str(lyp_path)

        if output_connectivity:
            conn_path = Path(output_connectivity).expanduser().resolve()
            conn_path.parent.mkdir(parents=True, exist_ok=True)
            conn_path.write_text(generate_connectivity_txt(connections), encoding="utf-8")
            result["output_connectivity"] = str(conn_path)

        return result
    except Exception as e:
        return {"error": str(e), "status": "error"}


@mcp.tool
def generate_klayout_technology(
    tf_file: str,
    output_dir: str,
    tech_name: str = "LakerProcess"
) -> dict:
    """
    Full conversion: Laker TF → complete KLayout Technology files.

    Generates:
    - <tech_name>.lyp
    - <tech_name>.lyt (with connectivity embedded)
    - connectivity.txt
    """
    try:
        return _generate_tech_files(tf_file, output_dir, tech_name)
    except Exception as e:
        return {"error": str(e), "status": "error"}


@mcp.tool
def klayout_tech(
    tf_file: str,
    output_dir: str,
    tech_name: str = "LakerProcess"
) -> dict:
    """
    Generate KLayout technology files (.lyp and .lyt) from a Laker TF.

    This is the preferred tool for producing a complete KLayout Technology
    that can be used with `klayout design.gds -t <tech_name>`.

    Generates:
    - <tech_name>.lyp
    - <tech_name>.lyt (includes connectivity rules)
    - connectivity.txt

    Args:
        tf_file: Path to the Laker Technology File (.tf)
        output_dir: Directory where the files will be written
        tech_name: Technology name (used for filenames and inside .lyt)

    Returns:
        File paths, layer/connection counts, and install/open hints.
    """
    try:
        return _generate_tech_files(tf_file, output_dir, tech_name)
    except Exception as e:
        return {"error": str(e), "status": "error"}


if __name__ == "__main__":
    mcp.run()
