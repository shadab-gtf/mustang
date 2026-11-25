import argparse
from dataclasses import dataclass
from pathlib import Path
import shutil
import sys

import bpy

DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(DIRECTORY))

from animation import build_tracks
from body import build_body
from fascia import build_fascia
from geometry import box, pivot
from materials import pbr, vehicle_materials
from mechanicals import build_mechanicals
from studio import build_studio
from wheels import WHEEL_SPECS, wheels

WORKSPACE = DIRECTORY.parent


@dataclass
class VehicleContext:
    detail: int
    materials: dict[str, bpy.types.Material]
    root: bpy.types.Object
    doors: dict[str, bpy.types.Object]
    windows: dict[str, bpy.types.Object]
    hood: bpy.types.Object
    trunk: bpy.types.Object
    steering: bpy.types.Object
    engine: bpy.types.Object
    suspension: dict[str, bpy.types.Object]
    knuckles: dict[str, bpy.types.Object]
    wheels: dict[str, bpy.types.Object]


def rig(detail):
    vehicle = pivot("Vehicle",(0,0,0))
    vehicle["wheelbaseMeters"] = 2.7432
    vehicle["modelYear"] = 1967
    vehicle["forwardAxis"] = "-Z in glTF"
    frame = pivot("Chassis",(0,0,0),vehicle)
    doors, windows = {}, {}
    for side, key in ((-1,"L"),(1,"R")):
        doors[key]=pivot("Door_"+key,(side*.805,.58,.70),frame)
        doors[key]["travelDegrees"]=62
        windows[key]=pivot("Window_"+key,(0,0,0),doors[key])
        windows[key]["travelMeters"]=.422
    hood=pivot("Hood",(0,.719,.855),frame)
    trunk=pivot("Trunk",(0,-1.693,.872),frame)
    steering=pivot("SteeringWheel",(-.36,.41,.86),frame)
    engine=pivot("Engine",(0,1.39,.52),frame)
    suspension,knuckles,spinning={},{},{}
    for key,(x,y,radius,_) in WHEEL_SPECS.items():
        contact=(x,y,radius)
        suspension[key]=pivot("Suspension_"+key,contact,vehicle)
        knuckles[key]=pivot("Steer_"+key,contact,suspension[key])
        spinning[key]=pivot("Wheel_"+key,contact,knuckles[key])
        spinning[key]["rollingRadiusMeters"]=radius
    return VehicleContext(detail,vehicle_materials(detail),frame,doors,windows,hood,trunk,
                          steering,engine,suspension,knuckles,spinning)


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene=bpy.context.scene
    scene.unit_settings.system="METRIC"
    scene.unit_settings.length_unit="METERS"
    scene.render.fps=30
    scene.frame_start=1
    scene.frame_end=528
    return scene


def batch_meshes(vehicle):
    grouped = {}
    for obj in vehicle.children_recursive:
        if obj.type != "MESH":
            continue
        grouped.setdefault(obj.parent, []).append(obj)
    bpy.context.view_layer.update()
    graph = bpy.context.evaluated_depsgraph_get()
    baked = []
    for objects in grouped.values():
        for obj in objects:
            if obj.modifiers:
                mesh = bpy.data.meshes.new_from_object(
                    obj.evaluated_get(graph),preserve_all_data_layers=True,depsgraph=graph
                )
                baked.append((obj,mesh))
    for obj, data in baked:
        obj.modifiers.clear()
        obj.data=data
    bpy.ops.object.select_all(action="DESELECT")
    for parent, objects in grouped.items():
        if len(objects)>1:
            for obj in objects:
                obj.select_set(True)
            bpy.context.view_layer.objects.active=objects[0]
            bpy.ops.object.join()
            objects[0].name=parent.name+" surfaces"
            objects[0].select_set(False)


def export(root, path, *, animated=True, materials=True):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in [root,*root.children_recursive]:
        obj.select_set(True)
    bpy.context.view_layer.objects.active=root
    bpy.ops.export_scene.gltf(
        filepath=str(path),export_format="GLB",use_selection=True,export_yup=True,
        export_animations=animated,export_animation_mode="NLA_TRACKS",
        export_anim_slide_to_zero=True,export_optimize_animation_size=True,
        export_optimize_animation_keep_anim_object=False,export_extras=True,
        export_materials="EXPORT" if materials else "NONE",export_keep_originals=False,
        export_shared_accessors=True,export_cameras=False,export_lights=False,
        export_apply=True,
    )


def generate(detail, output, project):
    scene=reset_scene()
    ctx=rig(detail)
    build_body(ctx)
    build_fascia(ctx)
    wheels(ctx)
    build_mechanicals(ctx)
    build_tracks(ctx,scene.timeline_markers)
    scene.frame_set(1)
    if detail==0:
        build_studio()
        scene.frame_set(1)
        for screen in bpy.data.screens:
            for area in screen.areas:
                if area.type == "VIEW_3D":
                    area.spaces.active.region_3d.view_perspective = "CAMERA"
                    area.spaces.active.overlay.show_overlays = False
        bpy.context.preferences.filepaths.save_version = 0
        bpy.ops.wm.save_as_mainfile(filepath=str(project),compress=True)
    vehicle=ctx.root.parent
    batch_meshes(vehicle)
    filename="mustang.glb" if detail==0 else f"mustang-lod{detail}.glb"
    asset=output/filename
    export(vehicle,asset)
    if detail==1 and output==(WORKSPACE/"assets").resolve():
        web=WORKSPACE/"preview"/"public"/"models"
        web.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(asset,web/"mustang.glb")
    print(f"MUSTANG LOD{detail}: {asset}",flush=True)


def collision(output):
    reset_scene()
    hull=pivot("Collision",(0,0,0))
    hull["kind"]="Compound convex proxy"
    mat=pbr("Collision proxy",(.3,.3,.3),1)
    for name, center, dimensions, bevel in [
        ("Hull_Lower",(0,-.50,.55),(1.67,3.42,.47),.065),
        ("Hull_Nose",(0,1.70,.59),(1.65,1.17,.44),.09),
        ("Hull_Cab",(0,-.22,1.01),(1.28,1.40,.49),.13),
    ]:
        box(name,center,dimensions,mat,hull,radius=bevel,segments=1)
    export(hull,output/"mustang-collision.glb",animated=False,materials=False)


def main():
    cli=argparse.ArgumentParser(description="Build the editable Mustang, four visual LODs and collision proxies.")
    cli.add_argument("--levels",nargs="+",type=int,choices=range(4),default=list(range(4)))
    cli.add_argument("--out",type=Path,default=WORKSPACE/"assets")
    cli.add_argument("--skip-collision",action="store_true")
    args=cli.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
    output=args.out.resolve()
    output.mkdir(parents=True,exist_ok=True)
    for detail in args.levels:
        generate(detail,output,output/"mustang.blend")
    if not args.skip_collision:
        collision(output)


if __name__=="__main__":
    main()
