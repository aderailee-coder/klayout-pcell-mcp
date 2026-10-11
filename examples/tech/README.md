# KLayout Technology Example for Laker TF

This folder shows how to turn the output of `translate_laker_tf` into a proper KLayout Technology.

## Quick Setup

1. Run the MCP tool to generate files:
   - `layers.lyp`
   - `connectivity.txt` (optional reference)

2. Copy the generated `.lyp` into this folder and rename it if needed (e.g. `MyProcess.lyp`).

3. Edit `MyProcess.lyt` and update the paths / technology name.

4. Copy the whole `tech` folder to KLayout's technology directory:

   **Linux / macOS**
   ```bash
   mkdir -p ~/.klayout/tech/MyProcess
   cp -r examples/tech/* ~/.klayout/tech/MyProcess/
   ```

   **Windows**
   ```cmd
   mkdir %USERPROFILE%\KLayout\tech\MyProcess
   copy examples\tech\* %USERPROFILE%\KLayout\tech\MyProcess\
   ```

5. Restart KLayout. The technology should appear under **Tools → Manage Technologies**.

6. Open a GDS with the technology:
   ```bash
   klayout your_design.gds -t MyProcess
   ```

## Notes

- The `.lyt` file references the `.lyp` relatively.
- Connectivity rules still need to be entered manually in the Technology Manager (Connectivity tab), using the generated `connectivity.txt` as reference.
- You can later add DRC decks, LVS scripts, etc. into the same technology folder.
