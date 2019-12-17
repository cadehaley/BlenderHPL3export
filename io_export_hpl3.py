# modified for blender 2.80 


bl_info = {
    "name": "HPL3 Export",
    "description": "Export objects and materials directly into an HPL3 map",
    "author": "cadely",
    "version": (2, 1, 0),
    "blender": (2, 80, 0),
    "location": "3D View > Tools",
    "warning": "", # used for warning icon and text in addons panel
    "wiki_url": "",
    "tracker_url": "",
    "category": "Import-Export"
}


import bpy, bmesh, struct, os, re, time, math, mathutils, fnmatch
import xml.etree.ElementTree as ET

from bpy.props import (StringProperty,
                       BoolProperty,
                       IntProperty,
                       FloatProperty,
                       FloatVectorProperty,
                       EnumProperty,
                       PointerProperty,
                       )
from bpy.types import (Panel,
                       Operator,
                       PropertyGroup,
                       )


# ------------------------------------------------------------------------
#    store properties in the active scene
# ------------------------------------------------------------------------

class HPL3_Export_Properties (PropertyGroup):
    
    show_advanced : BoolProperty(default = False)
    
    ## Static object and entity properties
    casts_shadows : BoolProperty(name="Casts Shadows", default = True)
    collides : BoolProperty(name="Collides", default = True)
    is_occluder : BoolProperty(name="Is Occluder", default = True)
    distance_culling : BoolProperty(name="Distance Culling", default = True)
    culled_by_fog : BoolProperty(name="Culled By Fog", default = True)
    add_bodies : BoolProperty(
        name="Add Basic Physics Bodies",
        description="Create a cube body around each subobject which matches the dimensions of the object's bounding box",
        default = True
    )
    
    def update_map_path(self, context):
        if self["map_file_path"] != "":
            no_double_slash = re.sub(r'\\\\|//', '', self["map_file_path"])
            self["map_file_path"] = os.path.abspath(no_double_slash)
    
    map_file_path : StringProperty(
        name="Map File",
        description="Set to destination map's main .hpm file. Leave blank to skip map export",
        default="",
        maxlen=4096,
        subtype='FILE_PATH',
        update=update_map_path
        )
    
    def update_entity_path(self, context):
        no_double_slash = re.sub(r'\\\\|//', '', self["entity_export_path"])
        self["entity_export_path"] = os.path.abspath(no_double_slash)

    entity_export_path : StringProperty(
        name="Entities Folder",
        description="Destination for all entity .dae and .dds files, which will be grouped into subfolders by mesh datablock name (under the polygon triangle icon). Recommendation: Use one of these asset folders per map, or per project. Also, make one asset folder for entities, and one for static objects",
        default="",
        maxlen=4096,
        subtype='DIR_PATH',
        update=update_entity_path
        )

    def update_statobj_path(self, context):
        no_double_slash = re.sub(r'\\\\|//', '', self["statobj_export_path"])
        self["statobj_export_path"] = os.path.abspath(no_double_slash)

    statobj_export_path : StringProperty(
        name="Static Objects Folder",
        description="Destination for all static object .dae and .dds files, which will be grouped into subfolders by mesh datablock name (under the polygon triangle icon). Recommendation: Use one of these asset folders per map, or per project. Also, make one asset folder for entities, and one for static objects",
        default="",
        maxlen=4096,
        subtype='DIR_PATH',
        update=update_statobj_path
        )
        
    bake_scene_lighting : BoolProperty(
        name="Bake Scene Lighting (SLOW)",
        description="Use Cycles to bake direct and indirect lighting to the diffuse texture (only use for single-use stationary objects). Set samples using Render > Sampling > Render Samples to control quality/time",
        default = False
        )
        
    def update_square(self, context):
      self["map_res_y"] = self["map_res_x"]
        
    square_resolution : BoolProperty(
        name="Square",
        description="Export a square image",
        default = True,
        update=update_square
        )
    
    def update_res_x_pow2(self, context):
        base_2 = round(math.log(self["map_res_x"],2))
        base_2 = max(min(base_2, 14), 0)
        result = int(math.pow(2, base_2))
        self["map_res_x"] = result
        if self.square_resolution:
          self["map_res_y"] = result
    
    def update_res_y_pow2(self, context):
        base_2 = round(math.log(self["map_res_y"],2))
        base_2 = max(min(base_2, 14), 0)
        result = int(math.pow(2, base_2))
        self["map_res_y"] = result
        if self["square_resolution"]:
          self["map_res_x"] = result
  
    map_res_x : IntProperty(
        name = "X",
        description="A integer property",
        default = 1024,
        subtype='PIXEL',
        min = 1,
        max = 8192,
        update=update_res_x_pow2
        )
        
    map_res_y : IntProperty(
        name = "Y",
        description="A integer property",
        default = 1024,
        subtype='PIXEL',
        min = 1,
        max = 8192,
        update=update_res_y_pow2
        )
    
    sync_blender_deletions : BoolProperty(
        name="Clean Up Missing Objects (Read Description)",
        description="If objects previously exported with this tool exist in the HPL3 map but not the current Blender scene, delete them from the map and disk. Note: Will erase .dds and .dae files even if they have been modified since the last export (.ent and .mat will be left). Protect your work with Git/other version control!",
        default = False
        )

    bake_multi_mat_into_single : EnumProperty(
        name="Bake object materials to",
        description="For objects with multiple materials, bake materials as",
        items=[ ('OP1', "One Texture Set Per Material", "Exported object will have multiple diffuse, specular, and normal maps (Allows each material's faces to use full UV space)"),
                ('OP2', "Single Texture Set", "Exported object will have one diffuse, specular, and normal map (Unwraps and packs all UVs into a single UV space)"),
                ('OP3', "None (.dae export only)", "Export only the .dae file, converted to Y-up for HPL3. NOTE: Object materials must have an image plugged into a principled node base color, otherwise .dae will not load")
               ]
        )
        
    entity_option : EnumProperty(
        name="Set objects up as",
        description="Type of object to be added to the HPL3 map",
        items=[ ('OP1', "Static Objects", "Use for large non-interactable objects that occlude and are not very high-poly"),
                ('OP2', "Entities", "Use for interactable objects and high-poly static items")
               ]
        )
        
    multi_mode: EnumProperty(
            items=(('MULTI', "Multi Export", "Export each selected object as its own HPL3 map item"),
                   ('SINGLE', "Single Export", "Export all selected objects as a single HPL3 map item. Active object will be used as the 3D origin and name."),
                   ),
            )


# ------------------------------------------------------------------------
#    operators - main script
# ------------------------------------------------------------------------

class OBJECT_OT_HPL3_Export (bpy.types.Operator):
    bl_idname = "wm.export_selected"
    bl_label = "Export Selected"
    
    root = None
    asset_xml = None
    current_DAE = None
    CONVERTERPATH = None
    main_tool = None
    selected = []
    active_object = None
    export_path = None
    dupes = None
    requested_dds_paths = None
    temp_images = []
    temp_materials = []
    

    # ------------------------------------------------------------------------
    #    get NVIDIA DDS converter executable
    # ------------------------------------------------------------------------
    def nvidiaGet(self):
        spaths = bpy.utils.script_paths()
        for rpath in spaths:
            tpath = rpath + '\\addons\\nvidia\\nvidia_dds.exe'
            if os.path.exists(tpath):
                npath = '"' + tpath + '"'
                return npath
        return None
    
    # ------------------------------------------------------------------------
    #    loop through scene objects and export
    # ------------------------------------------------------------------------
    def export_objects(self, mytool):
        error = 0
        
        # Initialize global vars
        self.main_tool          = mytool
        self.selected           = bpy.context.selected_objects[:]
        self.active_object      = bpy.context.active_object
        self.export_path    = mytool.statobj_export_path if mytool.entity_option == 'OP1' else mytool.entity_export_path
        self.export_path    = re.sub(r'\\', '/', os.path.normpath(self.export_path)) + "/"
        # Check that objects were selected
        if len(self.selected) is 0:
            if mytool.sync_blender_deletions:
                self.report({'WARNING'}, "No objects selected. Cleaning up unused files")
            else:
                self.report({'WARNING'}, "No objects selected.")
        
        exported_mesh_names = []
        export_num = 0
        
        # Save original naming and create duplicates
        for ob in self.selected:
            if ob.type != "MESH" and ob.type != "ARMATURE":
                ob.select_set(False)
            else:
                ob["hpl3export_obj_name"] = re.sub('[^0-9a-zA-Z]+', '_', ob.name)
                ob["hpl3export_is_active"] = "FALSE"
                ob["hpl3export_mesh_name"] = re.sub('[^0-9a-zA-Z]+', '_', ob.data.name)
                # Find all associated armatures and add to list
                if ob.type == "MESH":
                    for mod in ob.modifiers:
                        if mod.type == 'ARMATURE':
                            if mod.object is not None:
                                mod.object.select_set(True)
        self.active_object["hpl3export_is_active"] = "TRUE"
        bpy.ops.object.duplicate(mode='DUMMY')
        self.dupes = bpy.context.selected_objects[:]
        
        success = False
        # New export for each object
        if mytool.multi_mode == 'MULTI':
            for current in self.dupes:
                if current.type == 'MESH':
                    export_num += 1
                    
                    self.get_asset_xml_entry(current)
                    # Prevent re-exporting files for instanced objects
                    if current.data.name not in exported_mesh_names:
                        exported_mesh_names.append(current.data.name)
                        if mytool.bake_multi_mat_into_single != 'OP3':
                            # Export material, return path of main .dds file
                            self.requested_dds_paths = []
                            error += self.export_materials_and_mesh(mytool, current)
                            # Add DDS paths to asset tracking XML
                            if "DDSpath" not in self.current_DAE.attrib:
                                self.current_DAE.attrib["DDSpath"] = ""
                            self.delete_unused_dds()
                            for entry in self.requested_dds_paths:
                                self.current_DAE.attrib["DDSpath"] += entry + ";"
                    # Add object to map
                    if mytool.map_file_path != "":
                        self.add_object(mytool, current)
            if mytool.map_file_path != "" and mytool.sync_blender_deletions:
                error += self.sync_blender_deletions(mytool) 
            success = True

        # Multiple objects, one export
        elif self.active_object.type == 'MESH':
            self.requested_dds_paths = []
            export_num = 1
            # Prevent re-exporting files for instanced objects
            if mytool.bake_multi_mat_into_single != 'OP3':
                for current in self.dupes:
                    if current.type == 'MESH':
                        if current.data.name not in exported_mesh_names:
                            exported_mesh_names.append(current.data.name)
                            # Export material, return path of main .dds file
                            error += self.export_materials_and_mesh(mytool, current)
                        # Add object to map
            self.get_asset_xml_entry(self.active_object)
            if mytool.map_file_path != "":
                self.add_object(mytool, self.active_object)
                
            # Add DDS paths to asset tracking XML
            if "DDSpath" not in self.current_DAE.attrib:
                self.current_DAE.attrib["DDSpath"] = ""
            self.delete_unused_dds()
            for entry in self.requested_dds_paths:
                self.current_DAE.attrib["DDSpath"] += entry + ";"
            success = True
        
        bpy.context.window_manager.progress_end()
        
        if success:
            self.prepare_and_export()
        self.clean_up()
            
        # Restore object selection
        for obj_sel in self.selected:
            obj_sel.select_set(True)
        bpy.context.view_layer.objects.active = self.active_object
        
        
        msg = "Exported " + str(export_num) + " object(s)."
        self.report({'INFO'}, "%s" % (msg))
            
        return error
    
    
    # ------------------------------------------------------------------------
    #    add object to HPL3 map
    #        current_obj - blender object being exported
    # ------------------------------------------------------------------------
    def add_object(self, mytool, current_obj):
        if mytool.entity_option == 'OP2':
            is_ent = True
        else:
            is_ent = False
        
        # Get 'Blender@HPL3EXPORT' section of XML
        section = None
        for child in self.root:
            if child.get("Name") == "Blender@HPL3EXPORT":
                section = child
        # or make new
        if section is None:
            section = ET.SubElement(self.root, "Section")
            section.attrib["Name"] = "Blender@HPL3EXPORT"
            if is_ent:
                file_indices = ET.SubElement(section, "FileIndex_Entities")
            else:
                file_indices = ET.SubElement(section, "FileIndex_StaticObjects")
            file_indices.attrib["NumOfFiles"] = "0"
            objects = ET.SubElement(section, "Objects")
        else:
            objects = section.find("Objects")
        
        #BEGIN getting variables
        
        # Assemble .dae/ent path
        if is_ent:
            filepath = self.mesh_export_path + "/" + current_obj["hpl3export_mesh_name"] + "/" + current_obj["hpl3export_mesh_name"] + ".ent"
        else:
            filepath = self.mesh_export_path + "/" + current_obj["hpl3export_mesh_name"] + "/" + current_obj["hpl3export_mesh_name"] + ".dae"
        filepath = re.sub(r'\\', '/', os.path.normpath(filepath))
        short_path = re.sub(r'.*\/SOMA\/', '', filepath)
            
        # Find in file index list
        file_indices = section[0]
        existing_index = None
        current_idx = None
        for current_idx in file_indices.iter("File"):
            # If there is a match, save the index
            if short_path == current_idx.get("Path"):
                existing_index = current_idx.get("Id")
                break
            
        #self.get_asset_xml_entry(short_path)
        
        # If not in index, make new index and object entry
        if existing_index is None:
            print("Adding new index entry")
            newindex = ET.Element("File")
            # If list is entirely empty
            if current_idx is None:
                existing_index = 0
            else:
                existing_index = int(current_idx.get("Id")) + 1
            newindex.attrib["Id"] = str(existing_index)
            newindex.attrib["Path"] = short_path
            file_indices.append(newindex)
            # Increment NumOfFiles
            num_of_files = int(file_indices.attrib['NumOfFiles'])
            file_indices.attrib['NumOfFiles'] = str(num_of_files + 1)
            
            # Increment file use number in asset tracking
            if self.main_tool.multi_mode == "MULTI":
                self.current_DAE.attrib["Uses"] = str(int(self.current_DAE.attrib["Uses"]) + 1)
            

        
        # Get last StaticObject ID, set to a num in case no entries exist
        try:
            lastID = int(objects[-1].get("ID")) + 1
        except IndexError:
            if is_ent:
                lastID = 268435459
            else:
                lastID = 285212672
            
        # Get object name
        obj_name = current_obj["hpl3export_obj_name"]

        # Check object for an armature modifier
        is_rigged = False
        armature = None
        for mod in current_obj.modifiers:
            if mod.type == 'ARMATURE':
                if mod.object is not None:
                    is_rigged = True
                    armature = mod.object
                    break
        
        # Get world transforms, convert to Y-up
        # If it's rigged, get skeleton transforms instead
        if is_rigged:
            world_mat = armature.matrix_world
        else:
            world_mat = current_obj.matrix_world
        
        # Reorder vector columns such that Blender X = HPL Z, Blender Y = HPL X, Blender Z = HPL Y
        column_reorder = mathutils.Matrix(((0,1,0,0), (0,0,1,0), (1,0,0,0), (0,0,0,1)))
        y_up_mat = mathutils.Matrix(((0,-1,0,0), (1,0,0,0), (0,0,1,0), (0,0,0,1)))
        local_rot_y = mathutils.Matrix.Rotation(math.radians(90.0), 4, 'Y')
        new_mat = column_reorder @ world_mat @ local_rot_y @ y_up_mat
        loc, rot, scale = new_mat.decompose()
        rot = rot.to_euler()
        
        loc_str = "{:.5f}".format(loc[0]) + " " + "{:.5f}".format(loc[1]) + " " + "{:.5f}".format(loc[2])
        rot_str = "{:.5f}".format(rot[0]) + " " + "{:.5f}".format(rot[1]) + " " + "{:.5f}".format(rot[2])
        scale_str = "{:.5f}".format(scale[0])+ " " + "{:.5f}".format(scale[1]) + " " + "{:.5f}".format(scale[2])
        
        #END getting variables
        
        # Search for existing entry
        old_mod_time = 0
        created_new = 0
        newobj = None
        # If entry exists, update
        if is_ent:
            obj_type = "Entity"
        else:
            obj_type = "StaticObject"
        for obj in objects.iter(obj_type):
            if obj_name == obj.get("Name"):
                old_mod_time = int(obj.get("ModStamp"))
                newobj = obj
                break
            
        # If does not exist, make new
        if newobj is None:
            # Create new XML element
            newobj = ET.Element(obj_type)
            newobj.attrib["ID"] = str(lastID)
            newobj.attrib["CreStamp"] = str(int(time.time()))
            created_new = 1
            
        
        newobj.attrib["Name"] = obj_name
        newobj.attrib["ModStamp"] = str(int(time.time()))
        newobj.attrib["WorldPos"] = loc_str
        newobj.attrib["Rotation"] = rot_str
        newobj.attrib["Scale"] = scale_str
        newobj.attrib["FileIndex"] = str(existing_index)
        if is_ent:
            newobj.attrib["Active"] = "true"
            newobj.attrib["Important"] = "false"
        else:
            if mytool.collides:
                newobj.attrib["Collides"] = "true"
            else:
                newobj.attrib["Collides"] = "false"
            if mytool.casts_shadows:
                newobj.attrib["CastShadows"] = "true"
            else:
                newobj.attrib["CastShadows"] = "false"
            if mytool.is_occluder:
                newobj.attrib["IsOccluder"] = "true"
            else:
                newobj.attrib["IsOccluder"] = "false"
            newobj.attrib["ColorMul"] = "1 1 1 1"
        if mytool.distance_culling:
            newobj.attrib["CulledByDistance"] = "true"
        else:
            newobj.attrib["CulledByDistance"] = "false"
        if mytool.culled_by_fog:
            newobj.attrib["CulledByFog"] = "true"
        else:
            newobj.attrib["CulledByFog"] = "False"
        newobj.attrib["IllumColor"] = "1 1 1 1"
        newobj.attrib["IllumBrightness"] = "1"
        newobj.attrib["UID"] = "blender"
        
        if is_ent:
            user_variables = newobj.find("UserVariables")
            if user_variables is None:
                user_variables = ET.SubElement(newobj, "UserVariables")
            cast_shadows = None
            for var in user_variables.iter("Var"):
                if var.get("Name") == "CastShadows":
                    cast_shadows = var
                    break
            if cast_shadows is None:
                var = ET.SubElement(user_variables, "Var")
                var.attrib["Name"] = "CastShadows"
            if mytool.casts_shadows:
                var.attrib["Value"] = "true"
            else:
                var.attrib["Value"] = "false"
        
        if created_new:
            objects.append(newobj)

        return old_mod_time
    
    # ------------------------------------------------------------------------
    #    find (or create) an entry in the script's asset tracking xml file
    #        short_path - path to file with ".../SOMA/" removed
    # ------------------------------------------------------------------------
    def get_asset_xml_entry(self, object):
        # Build filepath
        filepath = self.mesh_export_path + "/" + object["hpl3export_mesh_name"] + "/" + object["hpl3export_mesh_name"] + ".dae"
        filepath = re.sub(r'\\', '/', os.path.normpath(filepath))
        short_path = re.sub(r'.*\/SOMA\/', '', filepath)
        # Find asset path in asset XML list
        asset_listed = 0
        for asset in self.asset_xml.iter("Asset"):
            if short_path == asset.get("DAEpath"):
                asset_listed = 1
                self.current_DAE = asset
                break
        if not asset_listed:
        # If asset not listed, save asset path to asset tracking xml list
            self.current_DAE = ET.SubElement(self.asset_xml, "Asset")
            self.current_DAE.attrib["DAEpath"] = short_path
            self.current_DAE.attrib["Uses"] = "0"  
    
    # ------------------------------------------------------------------------
    #    bake maps for every material in object, then create .ent and .mat files
    #    and export
    #        current_obj   - current blender object
    # ------------------------------------------------------------------------
    def export_materials_and_mesh(self, mytool, current_obj):
        print("Exporting material")
        wm = bpy.context.window_manager
        wm.progress_begin(0, 100)
        progress = 0
        
        error = 0
    
        orig_materials = []
        temp_materials = []
            
        materials_used = False
        object_has_nmaps = False
            
        export_name = current_obj["hpl3export_mesh_name"]
        
        # Prepare UV maps for bake
        uv_layers = current_obj.data.uv_layers
        old_uv = None
        if mytool.bake_multi_mat_into_single == 'OP2':
            for layer in uv_layers:
                if layer.active_render == True:
                    old_uv = layer
            # Hack: delete a slot if we are full
            print("SLOTS: ", len(uv_layers))
            if len(uv_layers) == 8:
                idx_to_remove = 7 if uv_layers.active_index != 7 else 6
                uv_layers.remove(uv_layers[idx_to_remove])
            # create new called "hpl3uv", select, and unwrap w/o stretching to uv bounds
            new_uv = uv_layers.new(name="hpl3uv")
            new_uv.active = True
            new_uv.active_render = True
            bpy.ops.uv.smart_project(angle_limit=85.0, island_margin = 0.02, use_aspect=False, stretch_to_bounds=False)
        elif len(uv_layers) is 0:
            # Make a new UV layer
            new_uv = uv_layers.new()
        
        # Prepare materials and slots
        bpy.context.view_layer.objects.active = current_obj
        if len(current_obj.material_slots) is 0:
            print("create new slot")
            bpy.ops.object.material_slot_add()

        # Make copies of each material and replace the slot with the copy
        for idx,slot in enumerate(current_obj.material_slots):
            if slot.material is not None:
                # Make a copy of the material
                materials_used = True
                orig_mat = slot.material
                print("MATERIAL: " + orig_mat.name)
                orig_materials.append((idx, orig_mat))
                principled_name = None
                mat = None
                if orig_mat.node_tree is not None: 
                    for node in orig_mat.node_tree.nodes:
                        if (node.type == 'BSDF_PRINCIPLED'):
                            principled_name = node.name
                if (not orig_mat.use_nodes or principled_name is None):
                    mat = bpy.data.materials.new("hpl3export_" + orig_mat.name)
                    mat.use_nodes = True
                    principled_name = "Principled BSDF"
                    # Copy base, spec, and roughness
                    mat.node_tree.nodes[principled_name].inputs["Base Color"].default_value = (orig_mat.diffuse_color[0], orig_mat.diffuse_color[1], orig_mat.diffuse_color[2], 1)
                    mat.node_tree.nodes[principled_name].inputs["Specular"].default_value = orig_mat.specular_intensity
                    mat.node_tree.nodes[principled_name].inputs["Roughness"].default_value = orig_mat.roughness
                else:
                    mat = orig_mat.copy()
                    mat.name = "hpl3export_" + mat.name
                    if not object_has_nmaps:
                        object_has_nmaps = mat.node_tree.nodes[principled_name].inputs["Normal"].is_linked
                    if mytool.bake_multi_mat_into_single == 'OP2':
                        # Add UV input to every node with an empty "Vector" input
                        uv_node = mat.node_tree.nodes.new("ShaderNodeUVMap")
                        uv_node.uv_map = old_uv.name
                        for node in mat.node_tree.nodes:
                            for input in node.inputs:
                                if input.name == "Vector" and not input.is_linked:
                                    mat.node_tree.links.new(uv_node.outputs["UV"], node.inputs["Vector"])
                temp_materials.append(mat)
                slot.material = mat
        

        if not materials_used:
            # new mat in slot 0
            mat = bpy.data.materials.new("hpl3export_default")
            mat.use_nodes = True
            temp_materials.append(mat)
            current_obj.material_slots[0].material = mat
            
        # Deselect all and select object
        for ob in bpy.context.selected_objects:
            ob.select_set(False)
        current_obj.select_set(True)

        render_engine = bpy.context.scene.render.engine
        if render_engine == "BLENDER_EEVEE":
            render_samples = bpy.context.scene.eevee.taa_render_samples
        else:
            render_samples = bpy.context.scene.cycles.samples
        
        # bake type, suffix, is_exportable, is_bakeable, socket_name, special_bake_type
        maps = (
        ('ROUGHNESS', '_rough',   False, True,  'Roughness', ''),
        ('PRESPEC',   '_prespec', False, True,  'Specular', 'DIFFUSE'),
        ('SPECULAR',  '_spec',    True,  False, 'Specular', ''),
        ('NORMAL',    '_nrm',     True,  True,  'Normal', ''),
        ('DIFFUSE',   '',         True,  True,  'Base Color', '')
        )
        
        images_to_export = []

        for map in maps:
            
            if map[0] == 'NORMAL' and not object_has_nmaps:
                continue
            if mytool.bake_multi_mat_into_single == 'OP2':
                # create new image
                bake_name = "hpl3export_" + export_name + map[1]
                bpy.ops.image.new(name=bake_name, width=mytool.map_res_x, height=mytool.map_res_y)
                bake_image = bpy.context.blend_data.images[bake_name]
                if map[2]:
                    if mytool.multi_mode == "MULTI":
                        destination_dds = self.export_path + export_name + "/" + export_name + map[1] + ".dds"
                    else:
                        destination_dds = self.export_path + self.active_object["hpl3export_mesh_name"] + "/" + export_name + map[1] + ".dds"
                    # image datablock, export path, type, material name
                    images_to_export.append((bake_image, destination_dds, map[0], export_name))
            
            # Loop through materials doing PRE-BAKE operations
            temp_bake_nodes = []
            
            for mat in temp_materials:
                matname_clean = re.sub('[^0-9a-zA-Z]+', '_', mat.name)
                if mytool.multi_mode == "MULTI":
                    targa_name = self.export_path + export_name + "/"
                else:
                    targa_name = self.export_path + self.active_object["hpl3export_mesh_name"] + "/"
                principled_node = None
                for node in mat.node_tree.nodes:
                    if (node.type == 'BSDF_PRINCIPLED'):
                        principled_node = node
                # Set metallic to 0
                principled_node.inputs["Metallic"].default_value = 0
                # add node, select it
                new_img_node = mat.node_tree.nodes.new("ShaderNodeTexImage")
                mat.node_tree.nodes.active = new_img_node
                node_setup = (mat.node_tree, new_img_node, principled_node)
                if mytool.bake_multi_mat_into_single == 'OP2':
                    targa_name = targa_name + export_name
                else:
                    targa_name = targa_name + matname_clean
                    res_x, res_y = self.get_optimal_image_size(mytool, principled_node.inputs[map[4]])
                    bake_name = matname_clean + map[1]
                    bpy.ops.image.new(name=bake_name, width=res_x, height=res_y)
                    bake_image = bpy.context.blend_data.images[bake_name]
                    if map[2]: # If map is exportable
                        if mytool.multi_mode == "MULTI":
                            destination_dds = self.export_path + export_name + "/" + matname_clean + map[1] + ".dds"
                        else:
                            destination_dds = self.export_path + self.active_object["hpl3export_mesh_name"] + "/" + matname_clean + map[1] + ".dds"
                        images_to_export.append((bake_image, destination_dds, map[0], matname_clean))
                new_img_node.image = bake_image
                temp_bake_nodes.append(node_setup)
                self.do_special_map_operation(mytool, map[0], False, node_setup, targa_name)
                # Mark for later deletion
                self.temp_materials.append(mat)
            
            if map[3]: # If map is bakeable
                if map[5] is not "":
                    bake_type = map[5]
                else:
                    bake_type = map[0]
                self.setup_bake(mytool, bake_type, render_samples)
                
                try:
                    if mytool.bake_multi_mat_into_single == 'OP2':
                        bpy.ops.object.bake(type=bake_type, use_split_materials=False)
                    else:
                        bpy.ops.object.bake(type=bake_type, use_split_materials=True)
                except RuntimeError:
                    error_msg = 'Bake Error: Check that the object(s) and its collection are enabled for rendering (camera icon), then delete temporary "hpl3export_*" image datablocks and try again'
                    self.report({'ERROR'}, "%s" % (error_msg))
                    error += 1
                    break
            
            # Loop through materials doing POST-BAKE operations
            for node_setup in temp_bake_nodes:
                self.do_special_map_operation(mytool, map[0], True, node_setup, "")
             
            progress += 10
            wm.progress_update(progress)
        
        if not error:
            for image in images_to_export:
                # export
                error = self.exportfile(mytool, image)
                self.requested_dds_paths.append(re.sub(r'.*\/SOMA\/', '', image[1]))
                # hook diffuse images up to exported file
                if image[2] == 'DIFFUSE':
                    image[0].source = 'FILE'
                    image[0].filepath = image[1]
                progress += 10
                # Mark for later deletion
                self.temp_images.append(image[0])
                wm.progress_update(progress)


            if mytool.bake_multi_mat_into_single == 'OP2':
                # Delete extra slots
                for i in range(0, len(uv_layers)-1):
                    uv_layers.remove(uv_layers[0])
                    

            # generate .mat files
            self.generate_mat(mytool, images_to_export)
        
        bpy.context.scene.render.engine = render_engine
        bpy.context.scene.cycles.samples = render_samples
            
        return error
    
    # ------------------------------------------------------------------------
    #    traverse socket-connected images to find optimal baking resolution
    #        socket - socket belonging to the material's Principled BSDF node
    # ------------------------------------------------------------------------    
    def get_optimal_image_size(self, mytool, socket):
        if not socket.is_linked:
            return 4, 4
        # set resolution to same as source
        # traverse socket subtree to find max res in image nodes
        subtree_nodes = [socket.links[0].from_node]
        node_list = []
        while len(subtree_nodes) is not 0:
            for input in subtree_nodes[0].inputs:
                if (input.is_linked):
                    # Will have duplicates but will include all in subtree
                    subtree_nodes.append(input.links[0].from_node)
            node_list.append(subtree_nodes[0])
            subtree_nodes.pop(0)
        max_res_x = max_res_y = 0
        for node in node_list:
            if (type(node) == bpy.types.ShaderNodeTexImage):
                if(node.image is not None):
                    max_res_x = max(node.image.size[0], max_res_x)
                    max_res_y = max(node.image.size[1], max_res_y)
        if max_res_x is not 0 and max_res_y is not 0:
            base_2 = round(math.log(max_res_x,2))
            base_2 = max(min(base_2, 14), 0)
            max_res_x = int(math.pow(2, base_2))
            # Limit to max bake size x
            max_res_x = min(max_res_x, mytool.map_res_x)
            
            base_2 = round(math.log(max_res_y,2))
            base_2 = max(min(base_2, 14), 0)
            max_res_y = int(math.pow(2, base_2))
            # Limit to max bake size y
            max_res_y = min(max_res_y, mytool.map_res_y)
        else:
            max_res_x = mytool.map_res_x
            max_res_y = mytool.map_res_y
        return max_res_x, max_res_y    
    
    # ------------------------------------------------------------------------
    #    for each map type, set up nodes for baking
    #        bake_type    - map type, e.g. "DIFFUSE"
    #        post_bake    - False if function is called before bake is initiated
    #        node_setup   - list (node_tree, new_img_node, principled_node)
    #        targa_export - export path for temporary targa files
    # ------------------------------------------------------------------------
    def do_special_map_operation(self, mytool, bake_type, post_bake, node_setup, targa_export):
    ##Roughness
        if bake_type == 'ROUGHNESS' and post_bake:
            # rename node
            node_setup[1].label = 'HPL3_ROUGHNESS'
            
    ##Pre-specular
        elif bake_type == 'PRESPEC':
            spec_socket = node_setup[2].inputs["Specular"]
            diff_socket = node_setup[2].inputs["Base Color"]
            if not post_bake:
                # If diff socket is linked, change the name and label
                if diff_socket.is_linked:
                    diff_socket.links[0].from_node.name = "HPL3_ORIGINALDIFF"
                    diff_socket.links[0].from_node.label = diff_socket.links[0].from_socket.name
                if not spec_socket.is_linked:
                    # Create RGB node and attach
                    spec_value = math.sqrt(spec_socket.default_value) * 0.8
                    node = node_setup[0].nodes.new("ShaderNodeRGB")
                    node.outputs[0].default_value = (spec_value, spec_value, spec_value, 1.0)
                    node.name = "HPL3_RGB"
                    node_setup[0].links.new(node.outputs[0], diff_socket)
                else:
                    spec_out_socket = None
                    for link in node_setup[0].links:
                        if (link.to_socket == spec_socket):
                            spec_out_socket = link.from_socket
                    # Make link from spec node to diffuse
                    node_setup[0].links.new(spec_out_socket, diff_socket)

                # Set up a diffuse bake
                #set_up_bake(node_setup, 'DIFFUSE')
            else: # Post-bake
                # BEWARE: Naming a node "HPL3_ORIGINALDIFF" will connect it even if was originally disconnected
                original_diff = None
                for node in node_setup[0].nodes:
                    if node.name == "HPL3_ORIGINALDIFF":
                        original_diff = node
                if original_diff is not None: # Re-link original diffuse node setup
                    original_socket = None
                    for socket in original_diff.outputs:
                        if socket.name == original_diff.label:
                            original_socket = socket
                    node_setup[0].links.new(original_socket, diff_socket)
                else:
                    node = node_setup[0].nodes.new("ShaderNodeRGB")
                    diff_color = diff_socket.default_value
                    node.outputs[0].default_value = (diff_color[0], diff_color[1], diff_color[2], 1.0)
                    node.name = "HPL3_DIFF_RGB"
                    node_setup[0].links.new(node.outputs[0], diff_socket)
                # rename node
                node_setup[1].label = 'HPL3_SPEC'
                
    ##Specular    
        elif bake_type == 'SPECULAR' and not post_bake:
            # Find rough and spec images in node tree
            rough = None
            spec = None
            for node in node_setup[0].nodes:
                if (node.label == 'HPL3_ROUGHNESS'):
                    rough = node.image
                elif (node.label == 'HPL3_SPEC'):
                    spec = node.image
                
            if node_setup[1].image.source == 'FILE':
                return # Skip whole function to avoid re-rendering
            
            
            # save then set renderer settings
            render_engine = bpy.context.scene.render.engine
            render_x = bpy.context.scene.render.resolution_x
            render_y = bpy.context.scene.render.resolution_y
            render_percent = bpy.context.scene.render.resolution_percentage
            if bpy.app.version >= (2, 81, 0):
                render_disp_mode = bpy.context.preferences.view.render_display_type
            else:
                render_disp_mode = bpy.context.scene.render.display_mode
            render_use_compositing = bpy.context.scene.render.use_compositing
            render_samples = bpy.context.scene.cycles.samples

            
        ## Combine spec and roughness nodes
            using_nodes = bpy.context.scene.use_nodes
            bpy.context.scene.use_nodes = True
            comp_tree = bpy.context.scene.node_tree
            hpl3_spec = None
            for node in comp_tree.nodes:
                # Mute existing comp nodes
                if (type(node) == bpy.types.CompositorNodeComposite):
                    node.mute = True
                # Mute existing render layers
                if (type(node) == bpy.types.CompositorNodeRLayers):
                    node.mute = True
            
            comp = []
            # add composite output
            comp.append(comp_tree.nodes.new("CompositorNodeComposite"))
            # connect alpha convert, straight to premul
            comp.append(comp_tree.nodes.new("CompositorNodePremulKey"))
            comp[1].mapping = 'STRAIGHT_TO_PREMUL'
            comp_tree.links.new(comp[1].outputs[0], comp[0].inputs[0])
            # connect set alpha
            comp.append(comp_tree.nodes.new("CompositorNodeSetAlpha"))
            comp_tree.links.new(comp[2].outputs[0], comp[1].inputs[0])
            # connect scale
            comp.append(comp_tree.nodes.new("CompositorNodeScale"))
            comp[3].space = 'RENDER_SIZE'
            comp_tree.links.new(comp[3].outputs[0], comp[2].inputs[0])
            # spec tex to image slot
            # If bake image is a solid color, replace with RGB node
            if spec.size[0] is 4 and spec.size[1] is 4:
                comp.append(comp_tree.nodes.new("CompositorNodeRGB"))
                comp[4].outputs[0].default_value = (math.pow(spec.pixels[0],2.2), math.pow(spec.pixels[1],2.2), math.pow(spec.pixels[2],2.2), 1.0)
            else:
                comp.append(comp_tree.nodes.new("CompositorNodeImage"))
                comp[4].image = spec
            comp_tree.links.new(comp[4].outputs[0], comp[3].inputs[0])
            # connect scale to alpha slot
            comp.append(comp_tree.nodes.new("CompositorNodeScale"))
            comp[5].space = 'RENDER_SIZE'
            comp_tree.links.new(comp[5].outputs[0], comp[2].inputs[1])
            # invert to scale, fac 1
            comp.append(comp_tree.nodes.new("CompositorNodeInvert"))
            comp[6].inputs[0].default_value = 1.0
            comp_tree.links.new(comp[6].outputs[0], comp[5].inputs[0])
            # clamp range to prevent glitches in RGB output
            comp.append(comp_tree.nodes.new("CompositorNodeMapRange"))
            comp[7].inputs[3].default_value = 0.001
            comp[7].inputs[4].default_value = 0.999
            comp_tree.links.new(comp[7].outputs[0], comp[6].inputs[1])
            # math to color slot, power, 0.5
            comp.append(comp_tree.nodes.new("CompositorNodeMath"))
            comp[8].operation = 'POWER'
            comp[8].inputs[0].default_value = 0.5
            comp_tree.links.new(comp[8].outputs[0], comp[7].inputs[0])
            # rough tex to other value slot
            # If bake image is a solid color, replace with RGB node
            if rough.size[0] is 4 and rough.size[1] is 4:
                comp.append(comp_tree.nodes.new("CompositorNodeRGB"))
                comp[9].outputs[0].default_value = (math.pow(rough.pixels[0],2.2), math.pow(rough.pixels[1],2.2), math.pow(rough.pixels[2],2.2), 1.0)
            else:
                comp.append(comp_tree.nodes.new("CompositorNodeImage"))
                comp[9].image = rough
            comp_tree.links.new(comp[9].outputs[0], comp[8].inputs[0])
            
            
            max_res_x = max(spec.size[0], rough.size[0])
            max_res_y = max(spec.size[1], rough.size[1])
            if max_res_x is not 0 and max_res_y is not 0:
                base_2 = round(math.log(max_res_x,2))
                base_2 = max(min(base_2, 14), 0)
                max_res_x = int(math.pow(2, base_2))
                base_2 = round(math.log(max_res_y,2))
                base_2 = max(min(base_2, 14), 0)
                max_res_y = int(math.pow(2, base_2))
            else:
                max_res_x = mytool.map_res_x
                max_res_y = mytool.map_res_y
                
            bpy.context.scene.render.resolution_x = max_res_x
            bpy.context.scene.render.resolution_y = max_res_y
            bpy.context.scene.render.resolution_percentage = 100
            if bpy.app.version >= (2, 81, 0):
                bpy.context.preferences.view.render_display_type = 'NONE'
            else:
                bpy.context.scene.render.display_mode = 'NONE'
            bpy.context.scene.render.use_compositing = True
            
            
            
            bpy.ops.render.render()
            
            for img in bpy.context.blend_data.images:
                if (img.type == 'RENDER_RESULT'):
                    hpl3_spec = img
                    
            scene_disp_device = bpy.context.scene.display_settings.display_device
            bpy.context.scene.display_settings.display_device = "None"
            
            hpl3_spec.save_render(targa_export + "_spec.tga")
            
            bpy.context.scene.display_settings.display_device = scene_disp_device
            #set above spec Image to FILE, set to path of newly exported image
            node_setup[1].image.source = 'FILE'
            node_setup[1].image.filepath = (targa_export + "_spec.tga")
            
            
            # Restore
            # Delete all in 'comp'
            for node in comp:
                comp_tree.nodes.remove(node)
            for node in comp_tree.nodes:
                # Mute existing comp nodes
                if (type(node) == bpy.types.CompositorNodeComposite):
                    node.mute = False
                # Mute existing render layers
                if (type(node) == bpy.types.CompositorNodeRLayers):
                    node.mute = False
            # Delete now-unused images
            bpy.context.blend_data.images.remove(rough)
            bpy.context.blend_data.images.remove(spec)
            
            
            
            # revert to old renderer options
            bpy.context.scene.use_nodes = using_nodes
            bpy.context.scene.render.engine = render_engine
            bpy.context.scene.render.resolution_x = render_x
            bpy.context.scene.render.resolution_y = render_y
            bpy.context.scene.render.resolution_percentage = render_percent
            if bpy.app.version >= (2, 81, 0):
                bpy.context.preferences.view.render_display_type = render_disp_mode
            else:
                bpy.context.scene.render.display_mode = render_disp_mode
            bpy.context.scene.render.use_compositing = render_use_compositing
            bpy.context.scene.cycles.samples = render_samples
            

    ##Normal
        elif bake_type == 'NORMAL' and not post_bake:
            normal_socket = node_setup[2].inputs[19]
            if normal_socket.is_linked:
                if (type(normal_socket.links[0].from_node) == bpy.types.ShaderNodeTexImage):
                    # User mistake, place a normal map node in between
                    nrm_out_socket = None
                    for link in node_setup[0].links:
                        if (link.to_socket == normal_socket):
                            nrm_out_socket = link.from_socket
                            new = node_setup[0].nodes.new("ShaderNodeNormalMap")
                            node_setup[0].links.new(nrm_out_socket, new.inputs[1])
                            node_setup[0].links.new(new.outputs[0], normal_socket)
                # Change subnodes to non-color data
                subtree_nodes = [normal_socket.links[0].from_node]
                node_list = []
                while len(subtree_nodes) is not 0:
                    for input in subtree_nodes[0].inputs:
                        if (input.is_linked):
                            # Will have duplicates but will include all in subtree
                            subtree_nodes.append(input.links[0].from_node)
                    node_list.append(subtree_nodes[0])
                    subtree_nodes.pop(0)
                for node in node_list:
                    if (type(node) == bpy.types.ShaderNodeTexImage):
                        if(node.image is not None):
                            node.image.colorspace_settings.name = 'Non-Color'


    ## Diffuse
        elif bake_type == 'DIFFUSE' and post_bake: # Connect node to principled node
            # attach new image node to Base Color in principled shader
            node_setup[0].links.new(node_setup[1].outputs[0], node_setup[2].inputs[0])
    
    # ------------------------------------------------------------------------
    #    setup blender bake options for each map type
    # ------------------------------------------------------------------------
    def setup_bake(self, mytool, bake_type, render_samples):
        print("setting up bake")
        bpy.context.scene.render.engine = 'CYCLES'
        #bpy.context.scene.cycles.device = 'GPU'
        # GPU baking errors in beta, use CPU for now
        bpy.context.scene.cycles.device = 'CPU'
        bpy.context.scene.cycles.samples = 4
        bpy.context.scene.cycles.bake_type = bake_type

        bake = bpy.context.scene.render.bake
        if bake_type is 'DIFFUSE':
            # Disable direct and indirect, enable color pass
            # if bake_scene_lighting, enable all 3 and set samples higher
            if mytool.bake_scene_lighting:
                bake.use_pass_direct = True
                bake.use_pass_indirect = True
                bpy.context.scene.cycles.samples = render_samples
            else:
                bake.use_pass_direct = False
                bake.use_pass_indirect = False
            bake.use_pass_color = True

        if bake_type is 'NORMAL':
            bake.normal_space = 'TANGENT'
            bake.normal_r = 'POS_X'
            bake.normal_g = 'POS_Y'
            bake.normal_b = 'POS_Z'
        bake.margin = 16
        bake.use_clear = True
        bake.use_selected_to_active = False
            
    # ------------------------------------------------------------------------
    #    export image and convert to DDS
    #        image               - list (image datablock, export path, type)
    # ------------------------------------------------------------------------
    def exportfile(self, mytool, image):
        filepath_no_ext = re.sub(r'\..*', '', image[1])
        bpy.context.scene.render.image_settings.file_format = 'TARGA'
        bpy.context.scene.render.image_settings.color_mode = 'RGBA'
        tga_file = filepath_no_ext+'.tga'
        dds_file = filepath_no_ext+".dds"
        try:
            image[0].save_render(tga_file)
        except RuntimeError:
            print("WARNING: Could not load image '" + image[0].name + "'. Saving as pink...")
            if 'missing' not in bpy.data.images:
                    bpy.ops.image.new(name='missing', width=2, height=2, color=(1,0,1,1))
            bpy.data.images['missing'].save_render(tga_file)
        except PermissionError:
            message = "Permission denied writing " + tga_file
            print(message)
            return 1
            #self.report({'WARNING'}, "%s" % (message))
        # Export DDS
        if image[2] == 'NORMAL':
            params=" -normal -bc5 "
        else:
            params=" -alpha -bc3 "
        output2='"'+dds_file+'"'
        input2='"'+tga_file+'"'
        error = True
        try:
            if (image[0].source == 'FILE') and (os.path.exists(dds_file)):
                    os.remove(dds_file)
            error = os.system('"'+self.CONVERTERPATH+params+" "+input2+" "+output2+'"')  
        except PermissionError:
            message = "Permission denied removing " + dds_file
            print(message)
            #self.report({'WARNING'}, "%s" % (message))
        print("REMOVING ", tga_file)
        os.remove(tga_file)

        if error:
            message = "Failed to write " + dds_file
            print(message)
            #self.report({'WARNING'}, "%s" % (message))
        
        return error






    # ------------------------------------------------------------------------
    #    prepare and export meshes to a DAE file
    # ------------------------------------------------------------------------
    def prepare_and_export(self):
        print("export here")
        
        dupes_to_export = []
        
        # Prepare object parents
        for dupe in self.dupes:
            self.prepare_parent(dupe)
        
        # Prepare armatures
        for dupe in self.dupes:
            if dupe.type == "ARMATURE":
                self.prepare_armature(dupe)
        
        # Update once to use newly-transformed bone matrices
        bpy.context.view_layer.update()
        
        # Prepare meshes
        for dupe in self.dupes:
            parent_armature = None
            if dupe.type == "MESH":
                for mod in dupe.modifiers:
                    if mod.type == 'ARMATURE':
                        if mod.object is not None:
                            parent_armature = mod.object
                subobjects = self.prepare_mesh(dupe, parent_armature)
                dupes_to_export.append(
                    {
                        "name": dupe["hpl3export_mesh_name"],
                        "subobjects": subobjects,
                    }
                )
        
        # Flatten all dupes_to_export into one list
        temp_objects = []
        for dupe in dupes_to_export:
            for object in dupe["subobjects"]:
                temp_objects.append(object)
        if self.main_tool.multi_mode == "SINGLE":
            dupes_to_export = [
                {
                    "name": self.active_object["hpl3export_mesh_name"],
                    "subobjects": temp_objects[:]
                }
            ]
        for obj in temp_objects:
            if obj[0] not in self.dupes:
                self.dupes.append(obj[0])
        
        # Export mesh(es)
        for dupe_dict in dupes_to_export:
            polycounts = self.export_mesh(dupe_dict)
            if self.main_tool.entity_option == "OP2":
                # Create/update entity
                ent_exists = os.path.exists(self.export_path + dupe_dict["name"] + "/" + dupe_dict["name"] + ".ent")
                ent_error = 0
                if ent_exists:
                    ent_error = self.update_ent(dupe_dict, polycounts)
                if not ent_exists or ent_error:
                    self.generate_ent(dupe_dict, polycounts)
                    
    # ------------------------------------------------------------------------
    #    Make sure skinned meshes are parented to armature
    # ------------------------------------------------------------------------

    def prepare_parent(self, dupe):
        parent_armature = None
        if dupe.type == "MESH":
            for mod in dupe.modifiers:
                if mod.type == 'ARMATURE':
                    if mod.object is not None:
                        parent_armature = mod.object
        if parent_armature is not None:
            if dupe.parent is None:
                # Deselect all
                for ob in bpy.context.selected_objects:
                    ob.select_set(False)
                dupe.select_set(True)
                parent_armature.select_set(True)
                bpy.context.view_layer.objects.active = parent_armature
                bpy.ops.object.parent_set()
                                      
    # ------------------------------------------------------------------------
    #    Prepare armatures for export
    # ------------------------------------------------------------------------
    def prepare_armature(self, dupe):
        is_multiexport = (self.main_tool.multi_mode == "MULTI")
        
        # Use transforms of active's armature if it has one
        armature_of_activeobj = None
        if self.active_object.type == "MESH":
            for mod in self.active_object.modifiers:
                if mod.type == 'ARMATURE':
                    if mod.object is not None:
                        armature_of_activeobj = mod.object
        if armature_of_activeobj is not None:
            active_mat = armature_of_activeobj.matrix_world
        else:
            active_mat = self.active_object.matrix_world
            
        # prepare_armature
        active_offset = active_mat.inverted_safe() @ dupe.matrix_world
        if is_multiexport:
            active_offset = mathutils.Matrix.Identity(4)
        # Rotate 90 Z
        dupe.matrix_world = mathutils.Matrix(((0,-1,0,0), (1,0,0,0), (0,0,1,0), (0,0,0,1))) @ active_offset
                
    # ------------------------------------------------------------------------
    #    Prepare meshes for export
    # ------------------------------------------------------------------------
    def prepare_mesh(self, dupe, parent_armature):
        is_single_mat = (self.main_tool.bake_multi_mat_into_single == 'OP2')
        is_multiexport = (self.main_tool.multi_mode == "MULTI")
        is_rigged = (parent_armature != None)
        
        if not is_rigged:
            # Apply modifiers
            depsgraph = bpy.context.evaluated_depsgraph_get()
            mod_mesh = bpy.data.meshes.new_from_object(dupe.evaluated_get(depsgraph), preserve_all_data_layers=True, depsgraph=depsgraph)
            dupe.data = mod_mesh
                    
        if is_rigged:
            # Multiply cube by armature inverse mat (which has not yet been updated by blender)
            dupe.matrix_world = parent_armature.matrix_world.inverted_safe() @ dupe.matrix_world
        else:
            if is_multiexport:
                dupe.matrix_world = mathutils.Matrix.Identity(4)
            else:
                dupe.matrix_world = self.active_object.matrix_world.inverted_safe() @ dupe.matrix_world

        for ob in bpy.context.selected_objects:
            ob.select_set(False)
        dupe.select_set(True)

        bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
        if is_rigged:
            bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
            
        original_mat = dupe.matrix_world.copy()
        dupe.matrix_world = self.convert_matrix(dupe.matrix_world, parent_armature)

        if is_single_mat:
            # Get first material
            mat_slots = dupe.data.materials
            first_mat = None
            for index in range(len(mat_slots)):
                if mat_slots[index] is not None and first_mat is None:
                    first_mat = mat_slots[index]
            # Clear slots
            while mat_slots:
                if bpy.app.version >= (2, 81, 0):
                    mat_slots.pop(index=0)
                else:
                    mat_slots.pop(index=0, update_data=True)
            # Add and assign only one material
            mat_slots.append(first_mat)
        else:
            # Separate by material
            bpy.ops.mesh.separate(type='MATERIAL')
            
        subobjects = []
        for object in bpy.context.selected_objects:
            subobjects.append((object, original_mat, parent_armature))
        return subobjects
    
   
    def convert_matrix(self, matrix, parent_armature = None):
        # Wacky transform
        local_rot_x = mathutils.Matrix.Rotation(math.radians(-90.0), 4, 'X')
        local_rot_z = mathutils.Matrix.Rotation(math.radians(180.0), 4, 'Z')
        world_mat = matrix.copy()
        world_rot_y = mathutils.Matrix.Identity(4)
        if parent_armature is not None:
            world_mat = parent_armature.matrix_world.copy()
            world_rot_y = mathutils.Matrix.Rotation(math.radians(-90.0), 4, 'Y')
        column_reorder = mathutils.Matrix(((0,1,0,0), (0,0,1,0), (1,0,0,0), (0,0,0,1)))
        result_mat = world_rot_y @ column_reorder @ world_mat @ local_rot_x @ local_rot_z
        return result_mat


    # ------------------------------------------------------------------------
    #   Build filepath and export to DAE
    # @param dupe_dict - Dict w/ keys "name" (string) and "subobjects" (list)
    # ------------------------------------------------------------------------
    def export_mesh(self, dupe_dict):
        # Deselect all
        for ob in bpy.context.selected_objects:
            ob.select_set(False)
        for subobject in dupe_dict["subobjects"]:
            if subobject[0].type == "MESH":
                subobject[0].select_set(True)
                # Select associated armature
                for mod in subobject[0].modifiers:
                    if mod.type == 'ARMATURE':
                        if mod.object is not None:
                            mod.object.select_set(True)
        # Sanitize name and build filepath
        san_name = re.sub('[^0-9a-zA-Z]+', '_', dupe_dict["name"])
        filepath = self.mesh_export_path + "/" + san_name + "/" + san_name + ".dae"
                            
        # Get polycounts
        polycounts = []
        for subobject in dupe_dict["subobjects"]:
            # Triangulate and get face count
            bm = bmesh.new()
            bm.from_mesh(subobject[0].data)
            bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method='BEAUTY', ngon_method='BEAUTY')
            bm.to_mesh(subobject[0].data)
            bm.free()
            polycounts.append({
                "object": subobject[0], 
                "count": str(len(subobject[0].data.polygons)),
                "WorldPos": "{:.5f}".format(subobject[0].location[0]) + " " + "{:.5f}".format(subobject[0].location[1]) + " " + "{:.5f}".format(subobject[0].location[2]),
                "Rotation": "{:.5f}".format(subobject[0].rotation_euler[0]) + " " + "{:.5f}".format(subobject[0].rotation_euler[1]) + " " + "{:.5f}".format(subobject[0].rotation_euler[2]),
                "Scale": "{:.5f}".format(subobject[0].scale[0]) + " " + "{:.5f}".format(subobject[0].scale[1]) + " " + "{:.5f}".format(subobject[0].scale[2]),
                "original_mat" : subobject[1],
                "parent_armature" : subobject[2]
            })
        # Export to DAE
        bpy.ops.wm.collada_export(
            filepath=filepath, 
            apply_modifiers=False, 
            selected=True, 
            include_children=True, 
            include_armatures=True,
            active_uv_only=True,
            use_texture_copies=False,
            triangulate=False, 
            use_object_instantiation=True,
            use_blender_profile=False,
            limit_precision=True
            )
        return polycounts




        
    # ------------------------------------------------------------------------
    #    generate HPL3 .mat file
    #        images_to_export - (image datablock, export path, type, material_name)
    # ------------------------------------------------------------------------
    def generate_mat(self, mytool, images_to_export):
        
        # Regroup images by material
        mat_names = []
        for image in images_to_export:
            if image[2] == "DIFFUSE":
                mat_names.append(image[3])
        
        materials = []
        index = 0
        for name in mat_names:
            materials.append([])
            for image in images_to_export:
                if image[3] == name:
                    materials[index].append(image)
            index += 1
                    
        
        
        for mat in materials:
            print("Exporting .mat")
            
            diffuse = None
            for image in mat:
                if image[2] == "DIFFUSE":
                    diffuse = image
            
            if diffuse is not None:
                path_no_ext = os.path.splitext(diffuse[1])[0]
                output = path_no_ext + ".mat"
                if os.path.exists(output):
                    print("\t.mat already exists")
                    pass
                
            mat_root = ET.Element("Material")
            main = ET.SubElement(mat_root, "Main")
            main.attrib["DepthTest"] = "True"
            main.attrib["PhysicsMaterial"] = "Default"
            main.attrib["Type"] = "SolidDiffuse"
            texture_units = ET.SubElement(mat_root, "TextureUnits")
            for image in mat:
                short_path = re.sub(r'.*\/SOMA\/', '', image[1])
                if image[2] == "DIFFUSE":
                    entry = ET.SubElement(texture_units, "Diffuse")
                if image[2] == "SPECULAR":
                    entry = ET.SubElement(texture_units, "Specular")
                if image[2] == "NORMAL":
                    entry = ET.SubElement(texture_units, "NMap")
                entry.attrib["AnimFrameTime"] = ""
                entry.attrib["AnimMode"] = ""
                entry.attrib["File"] = short_path
                entry.attrib["Mipmaps"] = "true"
                entry.attrib["Type"] = "2D"
                entry.attrib["Wrap"] =  "Repeat"
            specific_variables = ET.SubElement(mat_root, "SpecificVariables")
            #ET.dump(mat_root)

            ET.ElementTree(mat_root).write(output)
            mat_root.clear()

    # ------------------------------------------------------------------------
    #    update mesh entry in HPL3 .ent file
    #        polycounts = (mesh_name, triangle_count)
    #        destination_ent_no_ext = path without ".ent"
    #       current_obj
    # ------------------------------------------------------------------------
    def update_ent(self, dupe_dict, polycounts):
    
        print(".ent exists, updating")
        
        ent_path = self.export_path + dupe_dict["name"] + "/" + dupe_dict["name"] + ".ent"
        short_path = re.sub(r'.*\/SOMA\/', '', self.export_path + dupe_dict["name"] + "/" + dupe_dict["name"] + ".dae")
        try:
            ent_root = ET.parse(ent_path).getroot()
        except IOError:
            print("Could not update ent. Overwriting")
            return 1
        model_data = ent_root.find("ModelData")
        mesh = None
        if model_data is not None:
            mesh = model_data.find("Mesh")
        if mesh is not None:
            mesh.clear()
            mesh.attrib["Filename"] = short_path
            index = 0
            for entry in polycounts:
                object = entry["object"]
                submesh = None
                for submesh_entry in mesh:
                    if submesh_entry.get("Name") == object.name:
                        submesh = submesh_entry
                if submesh is None:
                    submesh = ET.SubElement(mesh, "SubMesh")
                submesh.attrib["ID"] = str(index)
                submesh.attrib["ID"] = str(index)
                submesh.attrib["Name"] = object.name
                submesh.attrib["CreStamp"] = "0"
                submesh.attrib["ModStamp"] = "0"
                submesh.attrib["WorldPos"] = entry["WorldPos"]
                submesh.attrib["Rotation"] = entry["Rotation"]
                submesh.attrib["Scale"] = entry["Scale"]
                submesh.attrib["TriCount"] = str(entry["count"])
                submesh.attrib["Material"] = ""
                index += 1
            ET.ElementTree(ent_root).write(ent_path)
        else:
            return 1

        return 0

    # ------------------------------------------------------------------------
    #    create new HPL3 .ent file
    #        polycounts = dict with tri count and other info
    #        destination_ent_no_ext = path without ".ent"
    #       current_obj
    # ------------------------------------------------------------------------
    def generate_ent(self, dupe_dict, polycounts):
        print("no .ent exists. Creating")
        # Check object for an armature modifier
        is_rigged = False
        for entry in polycounts:
            for mod in entry["object"].modifiers:
                if mod.type == 'ARMATURE':
                    if mod.object is not None:
                        is_rigged = True
                        break
        
        print("Exporting .ent")
        ent_path = self.export_path + dupe_dict["name"] + "/" + dupe_dict["name"] + ".ent"
        
        ent_root = ET.Element("Entity")
        model_data = ET.SubElement(ent_root, "ModelData")
        entities = ET.SubElement(model_data, "Entities")
        mesh = ET.SubElement(model_data, "Mesh")
        short_path = re.sub(r'.*\/SOMA\/', '', self.export_path + dupe_dict["name"] + "/" + dupe_dict["name"] + ".dae")
        mesh.attrib["Filename"] = short_path
        shapes = ET.SubElement(model_data, "Shapes")
        bodies = ET.SubElement(model_data, "Bodies")
        index = 0
        for entry in polycounts:
            object = entry["object"]
            submesh = ET.SubElement(mesh, "SubMesh")
            submesh.attrib["ID"] = str(index)
            submesh.attrib["Name"] = object.name
            submesh.attrib["CreStamp"] = "0"
            submesh.attrib["ModStamp"] = "0"
            submesh.attrib["WorldPos"] = entry["WorldPos"]
            submesh.attrib["Rotation"] = entry["Rotation"]
            submesh.attrib["Scale"] = entry["Scale"]
            submesh.attrib["TriCount"] = str(entry["count"])
            submesh.attrib["Material"] = ""
            if self.main_tool.add_bodies:
                # Get object name, bound box, and transforms
                
                # Create Shape
                shape_index = len(polycounts) + (index * 2)
                shape = ET.SubElement(shapes, "Shape")
                shape.attrib["ID"] = str(shape_index)
                shape.attrib["Name"] = "shape_" + object.name
                shape.attrib["CreStamp"] = "0"
                shape.attrib["ModStamp"] = "0"
                shape.attrib["Rotation"] = entry["Rotation"]
                # Get bounding box dimensions
                box_scale = (
                    (object.bound_box[4][0] - object.bound_box[0][0]),
                    (object.bound_box[3][1] - object.bound_box[0][1]),
                    (object.bound_box[1][2] - object.bound_box[0][2])
                )
                box_scale_mat = mathutils.Matrix.Identity(4)
                box_scale_mat[0][0] = box_scale[0]
                box_scale_mat[1][1] = box_scale[1]
                box_scale_mat[2][2] = box_scale[2]

                box_offset = (
                    object.bound_box[0][0] + (box_scale[0] * 0.5),
                    object.bound_box[0][1] + (box_scale[1] * 0.5),
                    object.bound_box[0][2] + (box_scale[2] * 0.5)
                )
                
                box_mat = entry["original_mat"] @ mathutils.Matrix.Translation(box_offset) @ box_scale_mat
                final_mat = self.convert_matrix(box_mat, entry["parent_armature"])
                loc, rot, scale = final_mat.decompose()
                
                box_scale_str = "{:.5f}".format(scale[0]) + " " + "{:.5f}".format(scale[1]) + " " + "{:.5f}".format(scale[2])
                box_offset_str = "{:.5f}".format(loc[0]) + " " + "{:.5f}".format(loc[1]) + " " + "{:.5f}".format(loc[2])
                #shape.attrib["WorldPos"] = entry["WorldPos"]
                shape.attrib["WorldPos"] = box_offset_str
                shape.attrib["Scale"] = box_scale_str
                shape.attrib["RelativeTranslation"] = box_offset_str
                shape.attrib["RelativeRotation"] = entry["Rotation"]
                shape.attrib["RelativeScale"] = "1 1 1"
                shape.attrib["ShapeType"] = "Box"
                
                # Create body
                body_index = len(polycounts) + (index * 2) + 1
                body = ET.SubElement(bodies, "Body")
                body.attrib["ID"] = str(body_index)
                body.attrib["Name"] = "body_" + object.name
                body.attrib["CreStamp"] = "0"
                body.attrib["ModStamp"] = "0"
                body.attrib["WorldPos"] = entry["WorldPos"]
                body.attrib["Rotation"] = "0 0 0"
                body.attrib["Scale"] = "1 1 1"
                body.attrib["Material"] = "Wood"
                body.attrib["Mass"] = "1"
                # Other attributes here
                
                children = ET.SubElement(body, "Children")
                child = ET.SubElement(children, "Child")
                child.attrib["ID"] = str(index)
                shape_assoc = ET.SubElement(body, "Shape")
                shape_assoc.attrib["ID"] = str(shape_index)
            
            index += 1
        bones = ET.SubElement(model_data, "Bones")
        # Add a dummy bone to cause model viewer to re-associate
        if is_rigged:
            dummy_bone = ET.SubElement(bones, "Bone")
            dummy_bone.attrib["ID"] = "1"
            dummy_bone.attrib["Name"] = "dummy"
            
        joints = ET.SubElement(model_data, "Joints")
        animations = ET.SubElement(model_data, "Animations")
        proc_animations = ET.SubElement(model_data, "ProcAnimations")
        user_defined_variables = ET.SubElement(ent_root, "UserDefinedVariables")
        user_defined_variables.attrib["EntityType"] = "StaticProp"
        var = ET.SubElement(user_defined_variables, "Var")
        var.attrib["Name"] = "ShowMesh"
        var.attrib["Value"] = "true"

        ET.ElementTree(ent_root).write(ent_path)

    # ------------------------------------------------------------------------
    #    remove unused files
    #        shortname_list - files to be removed, without ".../SOMA/"
    # ------------------------------------------------------------------------
    def delete_assets(self, mytool, shortname_list):
        leftover_files = []
        SOMA_path = re.sub(r'\\SOMA\\.*', '', self.mesh_export_path)
        # If re.sub worked, add SOMA back to path
        if SOMA_path != self.mesh_export_path:
            SOMA_path = SOMA_path + "\\SOMA\\"
        else:
            # Don't prepend SOMA path
            SOMA_path = ""
        for entry in shortname_list:
            if entry != "":
                try:
                    os.remove(SOMA_path + entry)
                    print("Removed file " + entry)
                except FileNotFoundError:
                    # If file is missing, remove from .xml in parent function
                    print("Warning: File '" + entry + "' not found")
                except:
                    print("Warning: Could not delete '" + entry + "'.")
                    leftover_files.append(entry)
        
        # Clean up old .mat files and folders (may cause running SOMA to crash)' and uncomment following:
        #try:
        #    leftover_dir = os.path.dirname(SOMA_path + shortname_list[0])
        #except IndexError:
        #    leftover_dir = None
        #if not os.listdir(leftover_dir):
        #    os.rmdir(leftover_dir)
        #    print("Removed directory ", leftover_dir)
        
        return leftover_files

    def delete_unused_dds(self):
        existing_files = self.current_DAE.attrib["DDSpath"].split(";")
        files_to_delete = []
        for file in existing_files:
            if file not in self.requested_dds_paths and file != "":
                files_to_delete.append(file)
        leftover_files = self.delete_assets(self.main_tool, files_to_delete)
        self.current_DAE.attrib["DDSpath"] = ""
        # Add leftover files back to list to try and delete later
        for entry in leftover_files:
            self.current_DAE.attrib["DDSpath"] += entry + ";"

    # ------------------------------------------------------------------------
    #    delete HPL3 map entries that do not match an object in blender
    # ------------------------------------------------------------------------
    def sync_blender_deletions(self, mytool):
        is_ent = False
        if mytool.entity_option == 'OP2':
            is_ent = True
        # Get 'Blender@HPL3EXPORT' section of XML
        section = None
        for child in self.root:
            if child.get("Name") == "Blender@HPL3EXPORT":
                section = child
        if section is None:
            return 0 #Empty
        else:
            objects = section.find("Objects")
        # For each object in the HPL3 map
        entries_to_remove = []
        for entry in objects:
            exists = 0
            # Find corresponding blender object
            for obj in bpy.context.scene.objects:
                if re.sub('[^0-9a-zA-Z]+', '_', obj.name) == entry.get("Name"):
                    exists = 1
                    break
            if not exists:
                removed_name = entry.get("Name")
                removed_idx = entry.get("FileIndex")
                entries_to_remove.append(entry)
                in_use = 0
                # If removed object's file is still in use, ignore
                for entry2 in objects:
                    if entry2.get("FileIndex") == removed_idx and entry2.get("Name") != entry.get("Name") and entry2 not in entries_to_remove:
                        in_use = 1
                        break
                if not in_use:
                    dae_path = None
                    # Remove file index from map file and reorder indices
                    if is_ent:
                        files = section.find("FileIndex_Entities")
                    else:
                        files = section.find("FileIndex_StaticObjects")
                    files.attrib["NumOfFiles"] = str(int(files.attrib["NumOfFiles"]) - 1)
                    remove = None
                    for file in files.iter("File"):
                        if file.get("Id") == removed_idx:
                            print("\tdeleting index ", file.get("Id"), " or ", file.get("Path"))
                            dae_path = file.get("Path")
                            remove = file
                        # If Id is greater than removed index, decrement the value
                        elif (int(file.get("Id")) > int(removed_idx)):
                            file.attrib["Id"] = str(int(file.attrib["Id"]) - 1)
                    files.remove(remove)
                    # Renumber indices in object list
                    for entry2 in objects:
                        if int(entry2.get("FileIndex")) > int(removed_idx):
                            entry2.attrib["FileIndex"] = str(int(entry2.attrib["FileIndex"]) - 1)
                    # Find asset in list and remove .dae and .dds
                    asset = None
                    
                    if is_ent:
                        dae_path = re.sub(r'ent$', 'dae', dae_path)
                    for listing in self.asset_xml.iter("Asset"):
                        if dae_path == listing.get("DAEpath"):
                            asset = listing
                            break
                    if asset is not None:
                        if asset.get("Uses") == "1":
                            leftover_files = None
                            files_to_delete = asset.attrib["DDSpath"].split(";")
                            files_to_delete.append(asset.attrib["DAEpath"])
                            files_to_delete.append(re.sub(r'.dae', '.msh', asset.attrib["DAEpath"])) # Delete .msh
                            
                            # Clean up old .mat files (may cause running SOMA to crash) and uncomment following:
                            #files_to_delete.append(re.sub(r'.dds', '.mat', files_to_delete[0])) # Delete .mat
              
                            leftover_files = self.delete_assets(mytool, files_to_delete)
                            self.asset_xml.remove(asset)
                            if leftover_files:
                                return 1
                        else:
                            asset.attrib["Uses"] = str(int(asset.attrib["Uses"]) - 1)
        for entry in entries_to_remove:
            objects.remove(entry) # Erase entry
                
        return 0

    def clean_up(self):
        # Remove temp_images
        for image in self.temp_images:
            try:
                bpy.data.images.remove(image)
            except ReferenceError:
                pass
        # Remove temp_materials
        for mat in self.temp_materials:
            try:
                bpy.data.materials.remove(mat)
            except ReferenceError:
                pass
        # Delete dupes
        data_to_delete = []
        for obj in self.dupes: # Change to self.subobjects
            if obj.data is not None:
                data_to_delete.append(obj.data)
            bpy.data.objects.remove(obj, do_unlink=True)
        for data in data_to_delete:
            if type(data) == bpy.types.Mesh:
                print("removing ", data.name)
                bpy.data.meshes.remove(data)
                
            else:
                bpy.data.armatures.remove(data)
        # Restore selection and delete custom properties
        for obj in self.selected:
            try:
                del obj["hpl3export_obj_name"]
                del obj["hpl3export_mesh_name"]
                del obj["hpl3export_is_active"]
            except KeyError:
                print("Could not delete all keys for '", obj.name, "'")
            obj.select_set(True)


    
    # ------------------------------------------------------------------------
    #    Addon operator, do initial checks and run script
    # ------------------------------------------------------------------------
    def execute(self, context):
        mytool = context.scene.my_tool
        ParseError = ET.ParseError
        os.system('cls')
        self.CONVERTERPATH = self.nvidiaGet()
        if self.CONVERTERPATH is None:
            error_msg = 'Nvidia tools not found, please place nvidia folder in blender addons.'
            self.report({'ERROR'}, "%s" % (error_msg))
            return {'FINISHED'}
        
        # Read map static objects/entity file
        if mytool.entity_option == 'OP2':
            map_file_path = mytool.map_file_path + "_Entity"
        else:
            map_file_path = mytool.map_file_path + "_StaticObject"
        if mytool.map_file_path != "":
            if os.path.splitext(mytool.map_file_path)[1] == '.hpm':
                try:
                    self.root = ET.parse(map_file_path).getroot()
                except (IOError, ParseError):
                    error_msg = 'Map file could not be opened.'
                    self.report({'ERROR'}, "%s" % (error_msg))
                    return {'FINISHED'}
            else:
                error_msg = 'Map path is not a .hpm file'
                self.report({'ERROR'}, "%s" % (error_msg))
                return {'FINISHED'}

        if mytool.entity_option == 'OP1':
            self.mesh_export_path = mytool.statobj_export_path
        else:
            self.mesh_export_path = mytool.entity_export_path
            
        if not os.path.exists(self.mesh_export_path):
            error_msg = 'Asset Folder does not exist'
            self.report({'ERROR'}, "%s" % (error_msg))
            return {'FINISHED'}
        
        # Read blender asset use list xml
        asset_xml_path = self.mesh_export_path + "/exportscript_asset_tracking.xml"
        
        try:
            self.asset_xml= ET.parse(asset_xml_path).getroot()
        except (IOError, ParseError):
            print("No asset use list found. Creating new")
            self.asset_xml = ET.Element("ExportedFiles")
        
        print("File read success")
        
        error = self.export_objects(mytool)
        
        #DEBUG
        #ET.dump(asset_xml)
        # END DEBUG
        if not error:
            if mytool.map_file_path != "":
                ET.ElementTree(self.root).write(map_file_path)
            ET.ElementTree(self.asset_xml).write(asset_xml_path)
        else:
            print("\tDid not write to map file or xml tracking")

        return {'FINISHED'}

# ------------------------------------------------------------------------
#    my tool in objectmode
# ------------------------------------------------------------------------

class OBJECT_PT_HPL3_Export (Panel):
    bl_idname = "OBJECT_PT_HPL3_Export"
    bl_label = "HPL3 Export"
    bl_space_type = "VIEW_3D"   
    bl_region_type = "TOOLS"
    bl_context = "objectmode"   


    @classmethod
    def poll(self,context):
        return context.object is not None

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        mytool = scene.my_tool

        layout.label(text=str(len(bpy.context.selected_objects)) + " Object(s) Selected for Export")   
        layout.label(text="Duplicate with ALT+D to share a mesh", icon="ERROR")
        obj_type_row = layout.row(align=True)
        obj_type_row.prop( mytool, "entity_option", text="")
        obj_type_row.prop( mytool, "multi_mode", expand=True)
        if mytool.multi_mode == "SINGLE":
            if bpy.context.active_object.data is not None:
                active_name_san = re.sub('[^0-9a-zA-Z]+', '_', bpy.context.active_object.data.name)
            else:
                active_name_san = re.sub('[^0-9a-zA-Z]+', '_', bpy.context.active_object.name)
            layout.label(text="Export name: " + active_name_san + ".dae")
        
        layout.prop( mytool, "map_file_path")
        if mytool.entity_option == 'OP1':
            layout.prop( mytool, "statobj_export_path")
        else:
            layout.prop( mytool, "entity_export_path")
        bake_row_1 = layout.row(align=True)
        bake_row_2 = layout.row(align=True)
        layout.prop( mytool, "bake_multi_mat_into_single", text="Bake to")

        ## Advanced panel
        entity = True
        box = layout.box()
        col = box.column()
        row = col.row()
        if mytool.show_advanced:
            row.prop( mytool, "show_advanced", icon="DOWNARROW_HLT", text="Advanced", emboss=False)
        else:
            row.prop( mytool, "show_advanced", icon="RIGHTARROW", text="Advanced", emboss=False)
        if mytool.show_advanced:
            # Add items from other panels draw method here
            map_export_col = col.column(align=True)
            map_export_col.prop( mytool, "casts_shadows" )
            if mytool.entity_option == 'OP1':
                map_export_col.prop( mytool, "collides" )
                map_export_col.prop( mytool, "is_occluder" )
            map_export_col.prop( mytool, "distance_culling" )
            map_export_col.prop( mytool, "culled_by_fog" )
            if mytool.entity_option == 'OP2':
                map_export_col.prop( mytool, "add_bodies" )
            map_export_col.enabled = obj_type_row.enabled
            
            bake_row_1 = col.row(align=True)
            bake_row_2 = col.row(align=True)
            bake_row_3 = col.row(align=True)
            option_row_4 = col.row(align=True)
            
            multi_mat = mytool.bake_multi_mat_into_single == 'OP1'
            single_mat = mytool.bake_multi_mat_into_single == 'OP2'
            
            if single_mat:
                bake_row_1.label(text="Bake Size:")
            else:
                bake_row_1.label(text="Max Bake Size:")
            bake_row_1.prop( mytool, "square_resolution" )
            bake_row_2.prop( mytool, "map_res_x" )
            bake_row_2.prop( mytool, "map_res_y" )
            bake_row_3.prop( mytool, "bake_scene_lighting")
            option_row_4.prop( mytool, "sync_blender_deletions")
            
            if single_mat or multi_mat:
                bake_row_1.enabled = True
                bake_row_2.enabled = True
            else:
                bake_row_1.enabled = False
                bake_row_2.enabled = False
            if mytool.bake_multi_mat_into_single != 'OP3':
                bake_row_3.enabled = True
            else:
                bake_row_3.enabled = False
            
            option_row_4.enabled = obj_type_row.enabled
            if mytool.multi_mode != "MULTI":
                option_row_4.enabled = False

        ##
        layout.operator( "wm.export_selected")




# ------------------------------------------------------------------------
# register and unregister
# ------------------------------------------------------------------------

def register():
    
    
    bpy.utils.register_class( HPL3_Export_Properties )
    bpy.types.Scene.my_tool = PointerProperty( type = HPL3_Export_Properties )
    #
    bpy.utils.register_class( OBJECT_PT_HPL3_Export )
    bpy.utils.register_class( OBJECT_OT_HPL3_Export )

def unregister():
    bpy.utils.unregister_class( OBJECT_OT_HPL3_Export )
    bpy.utils.unregister_class( OBJECT_PT_HPL3_Export )
    #
    bpy.utils.unregister_class( HPL3_Export_Properties )
    del bpy.types.Scene.my_tool



if __name__ == "__main__":
    
    register()