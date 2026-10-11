# KLayout + PCell MCP Server

MCP (Model Context Protocol) server ideas and starter code for semiconductor layout workflows using **KLayout**, focused on layout inspection, DRC, and parameterized cells (PCells).

## Goal
Build AI agent tools that help with:
- Layout inspection and geometry queries (GDS/OAS)
- Design Rule Checking (DRC) execution and result parsing
- PCell generation, instantiation, and validation

**Key principle**: Act as an *orchestrator*. Do **not** embed proprietary foundry design rules, PDK data, or sensitive layout content. Call the user's local licensed tools or open-source KLayout engine.

## Why KLayout First?
- Open-source, powerful Python API (`pya`)
- Excellent for learning the MCP pattern before moving to Cadence Virtuoso / Calibre
- Existing community projects to learn from

## Planned Phases

### Phase 1: KLayout Core (Current Focus)
- Open and inspect layouts
- List layers / cells / hierarchy
- Measure geometry / query regions
- Run DRC scripts and return structured violations
- Render views / screenshots for the agent
- Controlled `pya` script execution

### Phase 2: PCell Support
- Register and manage PCell libraries
- Create / modify PCell instances from natural language or parameters
- Generate simple PCell code (e.g. contacts, metal lines, basic devices)
- Validate PCell variants with DRC

### Phase 3: Advanced / Commercial
- License key gating for premium analysis features
- Remote MCP option for IP protection of advanced logic
- Bridge toward Virtuoso SKILL / Calibre (later)

## IP Protection Notes
- Local stdio MCP code is visible → keep advanced heuristics remote or license-gated.
- Use file allowlists (`KLAYOUT_MCP_ALLOWED_LAYOUT_ROOTS`, etc.).
- Never ship real foundry rules inside this repo.
- Prefer orchestration over re-implementing rule engines.

## Reference Projects
- [aycandv/klayout-mcp](https://github.com/aycandv/klayout-mcp) — clean read-only inspection + DRC
- [caidish/KlayoutClaw](https://github.com/caidish/KlayoutClaw) — GUI control + pya execution
- [klinkdev2026/klayout-klink](https://github.com/klinkdev2026/klayout-klink)
- [ssql2014/mcp4eda](https://github.com/ssql2014/mcp4eda) (klayout-mcp folder)

## Quick Start (Starter)
```bash
# Requires KLayout installed + Python klayout package
pip install fastmcp klayout
# Then run the server (see src/server.py)
```

## Status
Early idea / skeleton stage. Ready for iteration.

## License
MIT (starter code). Commercial features TBD.
