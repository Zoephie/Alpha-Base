# Alpha-Base

A pipeline tool for extracting and converting G7 models and textures.

## Supported Exports

Currently, the exporter supports extracting the following assets:
- **Meshes**: Characters, Vehicles, Weapons, and Levels.
- **Textures**: All associated textures for the models.

*Note: Animation exporting is currently **unsupported** and there are no immediate plans to implement it.*

## Requirements

- **Blender**: Required for the actual model conversion process. *(Note: This pipeline has only been tested on **Blender 4.5.2**. Newer or older versions may not be supported.)*

## How to Use

1. **Launch the Program**: Open the packaged executable from the `dist` folder (or where you have extracted it).
2. **Select G7Reader**: In the interface, locate and select the `G7Reader.exe`.
3. **Select Blender Installation**: Set the path to your Blender installation (e.g., `blender.exe`). 
4. **Configure Options**: Set any other required input/output paths and run your extraction.

## Texture Guide

When models are extracted, you will encounter various texture suffixes. Here's a breakdown of what each one is and how to use them:

- **`_dif`**: **Albedo Map**. The base color texture of the material.
- **`_difa`**: **Albedo Map (with Alpha)**. Same as `_dif`, but the alpha channel contains the texture's transparency map.
- **`_nrm`**: **Normal Map**. Note that the blue channel is typically empty in these files. If you choose to invert the green channel in your software, it will flip the normal map to DirectX format (by default, it may be OpenGL). 
- **`_ref`**: **Reflection / Cubemap Mask**. When building your materials within a scene, this map can be used for the Metallic input.
- **`_spc_clrexp`**: **Specular Color & Exponent Map**. The RGB channels make up the Specular Color, while the Alpha channel acts as the Specular Exponent (gloss/smoothness).

## Known Issues & Cleanup

While the exporter is about 99% accurate, you may still encounter some abnormalities with the exported meshes. These can include:
- Incorrect normal maps
- Wrong face orientation
- Excess or duplicate vertices

## ⚠️ Important Disclaimer ⚠️

This tool is intended for extracting game assets and may operate within a legal gray area. By using it, you acknowledge and accept full responsibility for how any extracted assets are used.

I do not assume any liability for misuse of this tool or for any legal consequences that may arise from the unauthorized use, distribution, or modification of assets owned by Microsoft Studios, Halo Studios, or any other rights holders. It is your responsibility to ensure that your use of any extracted content complies with all applicable laws and licensing agreements.

## How to Build

If you want to build the executable yourself from the source code:
1. Make sure you have Python installed along with the required dependencies (such as PyInstaller).
2. Double-click and run the `build_exe.bat` file in the repository root.
3. Once completed, the newly built standalone executable will be generated inside the `dist` folder.

## Credits

- **surasia** for the `G7Reader.exe`, which is required for the initial extraction and parsing of the model files and is packaged alongside this release.
- **Bird** for their invaluable help with writing code and extensive testing.
