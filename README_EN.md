# Blender Wing Generator: Wing Model
[简体中文](README.md) | English

An AI-assisted Blender add-on for procedural bird-wing modeling, inspired by real bird-wing anatomy. You can customize feather length, position, shape, and group parameters, preview flapping motion, and generate a bird-wing model with a basic rig.
## Features
- Parametric bird-wing generation: Adjust parameters such as wingspan, wing chord, width, sweep, fan spread, wingtip roundness, feather gaps, and wingtip lift.
- Feather groups: Includes primaries, secondaries, tertials, primary coverts, greater coverts, median coverts, lesser coverts, axillaries, and alula.
- Group and individual feather settings: Configure feather counts, dimensions, offsets, and length-distribution curves.
- Wing-shape presets: Includes Pigeon, Elliptical, High-Speed, Dynamic, and Slot presets.
- Motion preview tools: Preview flapping motion and help find a relatively spread-wing pose.
- Basic rigging workflow: Provides tools for the main wing bone chain, feather bones, mesh skinning, constraints, pose controls, fold/spread controls, and cycle controls.
- Utilities: Includes parameter JSON import, UV tools, pose reset, and rig diagnostics.
## Requirements
- Blender 5.2
- The add-on's current source imports do not require additional third-party Python packages.
## Installation
1. Download the add-on .zip archive. Do not extract it.
2. Drag and drop the .zip file directly into the Blender window.
3. If installation does not start automatically, open Edit → Preferences → Add-ons in Blender. From the menu in the upper-right corner, choose Install from Disk, then select the .zip file.
4. Enable the Wing Model add-on if it has not been enabled automatically.
5. In the 3D Viewport, press N to open the sidebar and find the Wing Model panel.
## Basic Usage
1. Open the Wing Model panel in the 3D Viewport sidebar.
2. Select a wing-shape preset or adjust the overall shape parameters manually.
3. Set the feather counts for each group and adjust global, group-level, or individual-feather parameters as needed.
4. Use the model-generation tools in the panel to create or regenerate the model.
5. Use the motion tools to preview flapping.
6. When rigging is needed, use the corresponding tools to generate the main wing bone chain and feather bones, then perform skinning. Run the rig diagnostics when needed.
Control names and specific features may change between versions. We recommend backing up your .blend file before regenerating the model or experimenting with rigging tools.
## Project Status
This project is still under development. The add-on includes procedural modeling and rigging workflows, but generated rigs may need to be tested and adjusted for specific models. Blender 5.2 is the current target version; compatibility with other versions is not guaranteed.
## AI Assistance
AI tools were used to assist with code generation and development.
## License
This project is licensed under the MIT License. See the LICENSE file for details.
## Additional Information
Bug reports, suggestions, and code contributions are welcome. When reporting an issue, please include your Blender version, reproduction steps, and any relevant error messages from the System Console.
The project source code is open for users to inspect, learn from, modify, and extend.
