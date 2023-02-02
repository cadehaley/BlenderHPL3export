HPL3 Exporter Version 3.11
==============================================================================
![](https://i.imgur.com/1PrPPuD.jpg)

This addon allows you to model anything from single assets
to entire maps within Blender, and synchronize them to an HPL3 engine map,
automatically creating and configuring textures, material, and entity files
for a fast iteration process. The script is also capable of removing objects
from the HPL3 map which have been removed in the Blender scene, exporting
rigged and animated objects, and baking lighting onto scene objects.

Installation (Requires Windows and Blender 2.80 or later. Tested with 3.4)
------------------------------------------------------------------------------

- Copy "io_export_hpl3.py" and the "nvidia" folder to Blender's addons
directory (".../Blender/2.80/scripts/addons")

- Open Blender, go to Edit > Preferences > Add-ons > Search "hpl3"

- Check box next to "Import-Export: HPL3 Export" and press "Save Preferences"

- Exit window and go to the Tools bar in the left side of the 3D View. Drag
the width of the Tools bar out to set fields, and press T to hide the tools
bar at any time. Have fun!

Important Usage Notes
------------------------------------------------------------------------------
- Give each `Mesh` data-block a unique name in the asset's "Object Data Properties"
panel (under the poly triangle icon, not to be confused with the "Object Data"
panel under the cube icon).
	Example:
	```
	Object name = "evil_suzanne_by_doorway.005"
	Mesh data-block name = "Suzanne"
	```
On export, the subdirectory and mesh file will take this name ("Suzanne.dae"),
and having name conflicts in HPL3 (i.e. having two .dae files of the same name,
but in separate directories) can cause the wrong textures to load.
The "Object Name" does not matter as much, and will be used to name that
instance of the asset when placed in the map.

- If texture is black or has black parts, make sure UV faces are
within the square UV boundary. Texture baking requires that each material use
a single `Principled BSDF` node and that all UV faces lie within UV
coordinate bounds

- **Rigged Meshes**: Use "Single Export" when you have an animated mesh broken
into separate objects (e.g. shirt, head, hair) that are deformed by the same
armature (skeleton). Exporting meshes that are deformed by different armatures
to one file/entity is not supported by HPL3 and will produce unexpected results.

- **Baking Modes**:
Textures Per Material:
Think of each material as having its own UV set. Faces assigned to Material A
usually should not overlap in the UV editor with other Material A faces, though
it is ok (even recommended) for faces assigned to Material B to use up the full
UV space, since it won't matter if a face from Material A overlaps with a face
from Material B.

- **Instancing**: Use `Alt+D` to create copies of an object in Blender to place
around a map, since they will point to the same 'Mesh' data-block. Using
Copy/Paste or Shift+D creates a new `Mesh` data-block every time, and therefore
new .dae and .dds files on export, leaving you with multiple repeat numbered
.dae and/or .dds files taking unnecessary space on export.

Troubleshooting
------------------------------------------------------------------------------
- Hover your pointer over options for more in-depth info on how to use them
- When using "Textures Per Material", if texture is black or has black parts,
make sure faces are UV unwrapped to lie within the UV image boundaries.
The plugin uses texture baking, which will only bake parts of faces within
this boundary. Another workaround is to set a face to cover the whole boundary.
- If materials are failing to export properly, try switching between
"Textures Per Material" and "Textures Per Object", as one mode may
work better with your material setup than the other. Also, keep in mind that
texture baking requires that each material use a single `Principled BSDF` node
- In the Level Editor, if objects fail to appear after pressing
the button to reload static object or entity changes, try exiting out of the
editor and reloading your map to make objects appear properly again.

Bugs
------------------------------------------------------------------------------

For any questions or to report any bugs, message me @cadely on the [Frictional
Games Discord](https://discordapp.com/invite/frictionalgames)


Development
------------------------------------------------------------------------------
If you are interested in developing this addon or forking this project,
clone the "develop" branch. There you will find integration
and regression tests which can be extremely helpful when modifying the code
