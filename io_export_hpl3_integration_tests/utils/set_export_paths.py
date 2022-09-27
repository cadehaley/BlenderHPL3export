import bpy, os, time

test_path = os.environ['TEST_PATH']
build = os.environ['BUILD']

#### Use this space in case you need to tweak a setting across all
#### blend files. Useful whenever they add new features or change some default
#bpy.data.scenes[0].render.bake.margin_type = 'EXTEND'
####

if build != "true":
    bpy.data.scenes["Scene"].hpl3_export.statobj_export_path = test_path + "/tmp"
    bpy.data.scenes["Scene"].hpl3_export.entity_export_path = test_path + "/tmp"
    if os.path.exists(test_path + "/tmp/map/map.hpm"):
        bpy.data.scenes["Scene"].hpl3_export.map_file_path = test_path + "/tmp/map/map.hpm"

    bpy.ops.wm.export_selected()
