#!/usr/bin/env python3
"""
Laker Technology File (.tf) to KLayout Technology Translator

Usage:
  python tools/laker_tf_to_klayout.py --tf path/to/process.tf --out-dir ./tech_out --tech-name MyFab

This script:
1. Parses Laker TF (tfStreamIoTable / tfLayoutLayerTable / tfLayoutConnection)
2. Generates:
   - <tech>.lyp          (layer properties)
   - connectivity.txt    (human-readable connection rules)
   - <tech>.lyt          (KLayout technology definition with connectivity)
3. Optionally prints a klayout command line to open a GDS with the generated technology.

Designed to be called from a wrapper script before launching KLayout.
"""

import argparse
import re
import sys
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom


def extract_block(content: str, block_name: str) -> str:
    """Extract content inside a named block."""
    pattern = re.compile(
        rf"{re.escape(block_name)}\s*\{{([^}}]*)\}}",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(content)
    return match.group(1) if match else ""


def parse_layers(content: str) -> tuple[list[dict], dict]:
    """Parse layer definitions from stream table (preferred) or layout layer table."""
    layers = []
    lookup = {}

    stream_block = extract_block(content, "tfStreamIoTable")
    stream_pattern = re.compile(
        r"def\s*\{\s*(\w+)\s+(\w+)\s+(\d+)\s+(\d+)",
        re.IGNORECASE,
    )

    source = stream_block or content
    for match in stream_pattern.finditer(source):
        name, purpose, gds_l, gds_dt = match.groups()
        entry = {
            "layer_name": name,
            "purpose": purpose,
            "gds_layer": int(gds_l),
            "gds_datatype": int(gds_dt),
            "display_name": f"{name}.{purpose}",
        }
        layers.append(entry)
        lookup[(name.lower(), purpose.lower())] = entry
        lookup[name.lower()] = entry

    # Fallback to layout layer table if needed
    if not layers:
        layer_block = extract_block(content, "tfLayoutLayerTable")
        if layer_block:
            layout_pattern = re.compile(
                r"def\s*\{\s*(\w+)\s+(\w+)\s+(\d+)",
                re.IGNORECASE,
            )
            for match in layout_pattern.finditer(layer_block):
                name, purpose, gds_l = match.groups()
                entry = {
                    "layer_name": name,
                    "purpose": purpose,
                    "gds_layer": int(gds_l),
                    "gds_datatype": 0,
                    "display_name": f"{name}.{purpose}",
                }
                layers.append(entry)
                lookup[(name.lower(), purpose.lower())] = entry
                lookup[name.lower()] = entry

    return layers, lookup


def parse_connections(content: str, lookup: dict) -> list[dict]:
    """Parse tfLayoutConnection block."""
    connections = []
    conn_block = extract_block(content, "tfLayoutConnection")
    if not conn_block:
        return connections

    conn_pattern = re.compile(
        r"def\s*\{\s*(\w+)\s+(\w+)\s+(\w+)(?:\s+(\w+))?",
        re.IGNORECASE,
    )

    def resolve(name: str):
        key = name.lower()
        if key in lookup:
            return lookup[key]
        if (key, "drawing") in lookup:
            return lookup[(key, "drawing")]
        return None

    for match in conn_pattern.finditer(conn_block):
        l1_name, l2_name, via_name, extra = match.groups()
        l1 = resolve(l1_name)
        l2 = resolve(l2_name)
        via = resolve(via_name)
        if l1 and l2 and via:
            connections.append({
                "from_layer": l1_name,
                "from": f"{l1['gds_layer']}/{l1['gds_datatype']}",
                "via_layer": via_name,
                "via": f"{via['gds_layer']}/{via['gds_datatype']}",
                "to_layer": l2_name,
                "to": f"{l2['gds_layer']}/{l2['gds_datatype']}",
                "extra": extra,
                "description": f"{l1_name} --{via_name}--> {l2_name}"
                + (f" ({extra})" if extra else ""),
            })
    return connections


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
    rough = tostring(root, encoding="utf-8")
    return minidom.parseString(rough).toprettyxml(indent="  ")


def generate_connectivity_txt(connections: list[dict]) -> str:
    lines = [
        "# Connectivity rules generated from Laker tfLayoutConnection",
        "# These are also embedded in the .lyt file",
    ]
    for c in connections:
        lines.append(
            f"connection: {c['from']} --via({c['via']})--> {c['to']}  # {c['description']}"
        )
    return "\n".join(lines) + "\n"


def generate_lyt(tech_name: str, lyp_filename: str, connections: list[dict]) -> str:
    """Generate .lyt with embedded connectivity (symbols + connections)."""
    # Collect unique symbols (layer name -> GDS expression)
    symbols = {}
    for c in connections:
        symbols[c["from_layer"]] = c["from"]
        symbols[c["to_layer"]] = c["to"]
        symbols[c["via_layer"]] = c["via"]

    conn_xml = []
    for c in connections:
        # Format: from_layer,via_layer,to_layer
        conn_xml.append(
            f"    <connection>{c['from_layer']},{c['via_layer']},{c['to_layer']}</connection>"
        )

    symbol_xml = []
    for name, expr in sorted(symbols.items()):
        symbol_xml.append(f"    <symbols>{name}='{expr}'</symbols>")

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


def main():
    parser = argparse.ArgumentParser(description="Convert Laker TF to KLayout technology files")
    parser.add_argument("--tf", required=True, help="Path to Laker .tf file")
    parser.add_argument("--out-dir", default="./klayout_tech", help="Output directory")
    parser.add_argument("--tech-name", default="LakerProcess", help="Technology name")
    parser.add_argument("--gds", help="Optional GDS file to suggest klayout command")
    args = parser.parse_args()

    tf_path = Path(args.tf).expanduser().resolve()
    if not tf_path.exists():
        print(f"Error: TF file not found: {tf_path}", file=sys.stderr)
        sys.exit(1)

    content = tf_path.read_text(encoding="utf-8", errors="ignore")
    layers, lookup = parse_layers(content)
    connections = parse_connections(content, lookup)

    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    tech_name = args.tech_name
    lyp_file = out_dir / f"{tech_name}.lyp"
    conn_file = out_dir / "connectivity.txt"
    lyt_file = out_dir / f"{tech_name}.lyt"

    lyp_file.write_text(generate_lyp(layers), encoding="utf-8")
    conn_file.write_text(generate_connectivity_txt(connections), encoding="utf-8")
    lyt_file.write_text(generate_lyt(tech_name, lyp_file.name, connections), encoding="utf-8")

    print(f"Generated technology files in: {out_dir}")
    print(f"  Layers:        {len(layers)}")
    print(f"  Connections:   {len(connections)}")
    print(f"  .lyp:          {lyp_file}")
    print(f"  connectivity:  {conn_file}")
    print(f"  .lyt:          {lyt_file} (includes connectivity)")

    if args.gds:
        gds_path = Path(args.gds).expanduser().resolve()
        print("\nSuggested command to open GDS with this technology:")
        print(f"  klayout {gds_path} -t {tech_name}")
        print("\nOr install the technology first:")
        print(f"  mkdir -p ~/.klayout/tech/{tech_name}")
        print(f"  cp {out_dir}/* ~/.klayout/tech/{tech_name}/")


if __name__ == "__main__":
    main()
