import argparse
from pathlib import Path
import sys

import bpy

VIEWS = {
    "front": ("Front three-quarter",1),
    "rear": ("Rear three-quarter",1),
    "engine": ("Engine inspection",199),
    "cabin": ("Driver cabin",114),
    "night": ("Front three-quarter",1),
}


def night(scene):
    from mathutils import Vector
    scene.world.node_tree.nodes.get("Background").inputs[1].default_value=.095
    for obj in scene.objects:
        if obj.type=="LIGHT":
            obj.data.energy *= .32 if "blue strip" in obj.name else .16
    for x in (-.735,.735):
        light=bpy.data.lights.new("Low beam road projection","SPOT")
        light.energy=95
        light.color=(.83,.9,1)
        light.spot_size=.76
        light.spot_blend=.37
        obj=bpy.data.objects.new(light.name,light)
        scene.collection.objects.link(obj)
        obj.location=(x,2.28,.65)
        obj.rotation_euler=Vector((x*.07,1,-.14)).to_track_quat("-Z","Y").to_euler()
    for material in bpy.data.materials:
        if material.name in {"HeadlightEmission","TailEmission","DashEmission"}:
            node=material.node_tree.nodes.get("Principled BSDF")
            node.inputs["Emission Strength"].default_value *= 2.5


def main():
    cli=argparse.ArgumentParser(description="Render the studio views from the editable Mustang scene.")
    cli.add_argument("views",nargs="+",choices=VIEWS)
    cli.add_argument("--out",type=Path,default=Path(__file__).resolve().parents[1]/"renders")
    cli.add_argument("--scale",type=int,default=100)
    cli.add_argument("--samples",type=int,default=32)
    args=cli.parse_args(sys.argv[sys.argv.index("--")+1:])
    args.out.mkdir(parents=True,exist_ok=True)
    scene=bpy.context.scene
    scene.render.resolution_percentage=args.scale
    scene.cycles.samples=args.samples
    for name in sorted(args.views,key=lambda view: view=="night"):
        camera,frame=VIEWS[name]
        scene.camera=bpy.data.objects[camera]
        scene.frame_set(frame)
        if name=="night":
            night(scene)
        scene.render.filepath=str(args.out.resolve()/f"mustang-{name}.png")
        bpy.ops.render.render(write_still=True)


if __name__=="__main__":
    main()
