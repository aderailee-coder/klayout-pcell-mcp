# Architecture Notes

## Deployment Models

| Model | Code Visibility | IP Protection | Recommended Use |
|-------|-----------------|---------------|-----------------|
| Local stdio MCP | Visible | Medium (license key) | Personal / early validation |
| Remote MCP | Hidden | High | Commercial advanced logic |
| Hybrid | Partial | High | Best long-term |

## Suggested Tools (Phase 1)

- `open_layout(file_path)`
- `get_layout_info(file_path, top_cell=None)`
- `list_layers` / `list_cells` / `describe_cell`
- `query_region` / `measure_geometry`
- `run_drc(layout_file, drc_script)` → structured violations
- `extract_markers`
- `render_view` / `screenshot`
- `execute_script` (sandboxed / allowlisted)

## PCell Direction
Use `pya.PCellDeclarationHelper`.
- Register libraries
- `create_pcell_instance(name, params)`
- Generate or modify parameter sets
- Batch DRC on variants

## Security
- Allowlist directories for layouts and DRC decks
- No arbitrary file system access
- Log tool calls
- For commercial: verify license key on startup or per premium tool
