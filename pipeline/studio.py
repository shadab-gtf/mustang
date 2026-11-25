from mathutils import Vector
import bpy

from geometry import box
from materials import pbr


def aim(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def camera(name, origin, target, lens):
    data = bpy.data.cameras.new(name)
    obj = bpy.data.objects.new(name,data)
    bpy.context.collection.objects.link(obj)
    obj.location = origin
    data.lens = lens
    aim(obj,target)
    return obj


def area(name, origin, target, energy, color, width, height):
    light = bpy.data.lights.new(name,"AREA")
    light.energy, light.color, light.shape = energy, color, "RECTANGLE"
    light.size, light.size_y = width, height
    obj = bpy.data.objects.new(name,light)
    bpy.context.collection.objects.link(obj)
    obj.location = origin
    aim(obj,target)


def asphalt():
    mat = pbr("Studio tarmac",(.038,.043,.049),.42)
    nodes=mat.node_tree.nodes
    links=mat.node_tree.links
    shader=nodes.get("Principled BSDF")
    coords=nodes.new("ShaderNodeTexCoord")
    grain=nodes.new("ShaderNodeTexNoise")
    grain.inputs["Scale"].default_value=74
    grain.inputs["Detail"].default_value=3
    links.new(coords.outputs["Object"],grain.inputs["Vector"])
    ramp=nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position=.27
    ramp.color_ramp.elements[0].color=(.021,.026,.030,1)
    ramp.color_ramp.elements[1].position=.72
    ramp.color_ramp.elements[1].color=(.067,.077,.084,1)
    links.new(grain.outputs["Fac"],ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"],shader.inputs["Base Color"])
    bump=nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value=.37
    bump.inputs["Distance"].default_value=.024
    links.new(grain.outputs["Fac"],bump.inputs["Height"])
    links.new(bump.outputs["Normal"],shader.inputs["Normal"])
    water=nodes.new("ShaderNodeTexNoise")
    water.inputs["Scale"].default_value=.48
    water.inputs["Detail"].default_value=2
    links.new(coords.outputs["Object"],water.inputs["Vector"])
    roughness=nodes.new("ShaderNodeMapRange")
    roughness.inputs["To Min"].default_value=.24
    roughness.inputs["To Max"].default_value=.55
    links.new(water.outputs["Fac"],roughness.inputs["Value"])
    links.new(roughness.outputs["Result"],shader.inputs["Roughness"])
    return mat


def build_studio():
    scene=bpy.context.scene
    box("Continuous tarmac cyclorama",(0,0,-.087),(200,200,.164),asphalt(),None,radius=0)
    world=bpy.data.worlds.new("Dark studio ambient")
    scene.world=world
    world.use_nodes=True
    world.node_tree.nodes.get("Background").inputs[0].default_value=(.27,.32,.43,1)
    world.node_tree.nodes.get("Background").inputs[1].default_value=.34
    area("Key | broad warm softbox",(-3.65,3.29,5.59),(0,.35,.42),1450,(1,.88,.73),5.0,3.05)
    area("Fill | front reflector",(1.5,5.9,3.1),(0,0,.5),685,(.70,.81,1),4.70,1.60)
    area("Roof | linear softbox",(.0,-.28,5.52),(0,0,.1),1410,(.91,.96,1),2.45,7.20)
    area("Edge | blue strip", (3.25,-2.0,3.83),(0,-.45,.55),1300,(.62,.77,1),3.6,5.35)
    area("Rear | warm strip",(-2.1,-4.25,2.8),(0,-1.1,.68),718,(1,.70,.49),4.25,1.16)
    area("Left | belt highlight",(-4.85,-.87,2.10),(0,0,.47),410,(.82,.92,1),5.7,1.0)
    scene.camera=camera("Front three-quarter",(-4.38,6.46,2.36),(0,.10,.67),57)
    camera("Rear three-quarter",(-4.76,-5.64,2.32),(0,-.10,.65),56)
    camera("Engine inspection",(-2.58,3.65,3.12),(0,1.13,.68),52)
    camera("Driver cabin",(-2.78,-.72,2.23),(-.12,.04,.78),55)
    scene.render.engine="CYCLES"
    scene.cycles.samples=32
    scene.cycles.use_denoising=True
    scene.render.resolution_x=1500
    scene.render.resolution_y=936
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG"
    scene.view_settings.view_transform="AgX"
    scene.view_settings.look="AgX - Medium High Contrast"
