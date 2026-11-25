import argparse
from collections.abc import Callable
from math import pi, radians
from pathlib import Path
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(DIRECTORY))

from animation import motion, track
from black_studio import build_black_studio
from exhaust import build_exhaust
from geometry import pivot, tube
from materials import detail_maps, pbr
from restomod import build_restomod

WORKSPACE = DIRECTORY.parent
SOURCE_URL = "https://sketchfab.com/3d-models/ford-mustang-john-bowe-1969-wwwvecarzcom-91a5454aaf02492a9c7e959b8eb6db9f"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
AUTHOR = "vecarz (https://sketchfab.com/heynic)"
CORNERS = ("FL", "FR", "RL", "RR")


def import_model(source):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.length_unit = "METERS"
    scene.render.fps = 30
    scene.frame_start = 1
    scene.frame_end = 690
    bpy.ops.import_scene.gltf(filepath=str(source))
    bpy.context.view_layer.update()
    source_objects = list(scene.objects)
    normalize = Matrix.Rotation(pi, 4, "Z") @ Matrix.Scale(.01, 4)
    meshes = [(obj, normalize @ obj.matrix_world.copy()) for obj in source_objects if obj.type == "MESH"]
    vehicle = pivot("Vehicle", (0, 0, 0))
    vehicle["sourceModel"] = SOURCE_URL
    vehicle["sourceAuthor"] = AUTHOR
    vehicle["sourceLicense"] = LICENSE_URL
    vehicle["modifications"] = "Jet-black finish, articulated panels, rear-left exhaust, V8 engine bay, road cabin and underbody"
    vehicle["forwardAxis"] = "-Z in glTF"
    chassis = pivot("Chassis", (0, 0, 0), vehicle)
    for obj, matrix in meshes:
        obj.parent = chassis
        obj.matrix_parent_inverse = Matrix.Identity(4)
        obj.matrix_basis = Matrix.Identity(4)
        obj.data.transform(matrix)
        obj.data.update()
    for obj in source_objects:
        if obj.type == "EMPTY":
            bpy.data.objects.remove(obj, do_unlink=True)
    return scene, vehicle, chassis, [obj for obj,_ in meshes]


def finishes():
    materials = bpy.data.materials
    values = {
        "carpaint": ("Jet black lacquer", (.0059,.0063,.0071), .216,.09,.98,.084),
        "black": ("Satin black trim and chassis", (.014,.015,.017), .49,.08,0,.24),
        "chrome": ("Polished nickel brightwork", (.53,.55,.58), .15,.95,.23,.16),
        "material_15": ("Machined wheel alloy", (.43,.46,.49), .23,.84,.22,.14),
        "brakedisk": ("Ground steel rotors", (.24,.26,.28), .35,.83,0,.30),
        "interior": ("Charcoal interior", (.021,.023,.026), .44,.03,.10,.28),
        "mirror": ("Silvered mirror faces", (.68,.71,.74), .078,1,0,.14),
        "windowglass": ("Clear automotive glass", (.91,.95,.96), .079,0,0,.17),
        "clearglass": ("Clear lamp optics", (.85,.92,.97), .11,0,.12,.12),
        "orangeglass": ("Amber indicator optics", (.50,.13,.008), .24,0,.40,.14),
        "redglass": ("TailEmission", (.38,.009,.015), .21,0,.40,.13),
    }
    for old, (name,color,rough,metal,coat,coat_rough) in values.items():
        material = materials[old]
        material.name = name
        material.diffuse_color = (*color,1)
        shader = material.node_tree.nodes.get("Principled BSDF")
        for key, value in {
            "Base Color": (*color, 1), "Roughness": rough, "Metallic": metal,
            "Coat Weight": coat, "Coat Roughness": coat_rough, "Alpha": 1,
            "IOR": 1.45, "Specular IOR Level": .50,
        }.items():
            shader.inputs[key].default_value = value
        shader.inputs["Transmission Weight"].default_value = {"windowglass": .975, "clearglass": .84}.get(old, 0)
        if old=="windowglass":
            shader.inputs["IOR"].default_value = 1.31
        if old=="redglass":
            shader.inputs["Emission Color"].default_value = (.55,.012,.018,1)
            shader.inputs["Emission Strength"].default_value = .13
    lacquer=materials["Jet black lacquer"]
    for node in tuple(lacquer.node_tree.nodes):
        if node.type not in {"BSDF_PRINCIPLED","OUTPUT_MATERIAL"}:
            lacquer.node_tree.nodes.remove(node)
    normal=detail_maps(lacquer,1024,1969,.216,.026,.041)
    normal.inputs["Strength"].default_value=.055
    detail_maps(materials["Charcoal interior"],512,31,.44,.115,.22)
    detail_maps(materials["Ground steel rotors"],512,29,.35,.1,.088)
    rubber = materials["tire"]
    rubber.name = "Performance tire tread and sidewall"
    shader = rubber.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Roughness"].default_value = .57
    shader.inputs["Coat Weight"].default_value = .035


def corner(point):
    return ("F" if point.y>0 else "R") + ("L" if point.x<0 else "R")


def split_mesh(obj, labels: tuple[str, ...], label_for: Callable[[Vector],str]):
    original = obj.data
    results = {}
    for label in labels:
        bm = bmesh.new()
        bm.from_mesh(original)
        removal = [face for face in bm.faces if label_for(face.calc_center_median()) != label]
        bmesh.ops.delete(bm, geom=removal, context="FACES")
        if bm.faces:
            data = bpy.data.meshes.new(f"{original.name} {label}")
            bm.to_mesh(data)
            part = bpy.data.objects.new(data.name,data)
            for material in original.materials:
                data.materials.append(material)
            bpy.context.collection.objects.link(part)
            part.parent = obj.parent
            results[label] = part
        bm.free()
    bpy.data.objects.remove(obj, do_unlink=True)
    if original.users == 0:
        bpy.data.meshes.remove(original)
    return results


def locate_world(obj):
    mins = Vector(tuple(min(vertex.co[axis] for vertex in obj.data.vertices) for axis in range(3)))
    maxs = Vector(tuple(max(vertex.co[axis] for vertex in obj.data.vertices) for axis in range(3)))
    return (mins+maxs)/2, maxs-mins


def reparent(obj,parent):
    bpy.context.view_layer.update()
    matrix=obj.matrix_world.copy()
    obj.parent=parent
    obj.matrix_world=matrix


def build_wheels(vehicle, objects):
    parts={}
    for obj in tuple(objects):
        material=obj.data.materials[0].name
        if material in {"tire","brakedisk"}:
            groups=split_mesh(obj,CORNERS,corner)
            for key, piece in groups.items():
                parts.setdefault(key,{}).setdefault(material,[]).append(piece)
        elif material == "material_15":
            center,size=locate_world(obj)
            if abs(center.x)>.55 and size.y<.50:
                parts.setdefault(corner(center),{}).setdefault("alloy",[]).append(obj)
    pivots={}
    valve_metal = pbr("Nickel valve collars",(.39,.43,.47),.24,.84)
    valve_rubber = pbr("Black valve caps",(.015,.017,.02),.52)
    for key in CORNERS:
        pieces=parts[key]
        if len(pieces.get("tire",())) != 1 or not pieces.get("alloy"):
            raise RuntimeError(f"Incomplete original wheel assembly: {key}")
        tire=pieces["tire"][0]
        center,span=locate_world(tire)
        suspension=pivot(f"Suspension_{key}",center,vehicle)
        steering=pivot(f"Steer_{key}",center,suspension)
        rotating=pivot(f"Wheel_{key}",center,steering)
        rotating["rollingRadiusMeters"]=float(span.z/2)
        for group in pieces.values():
            for obj in group:
                reparent(obj,rotating)
        tire.name=f"Tire {key}"
        for order,obj in enumerate(pieces["alloy"],1):
            obj.name=f"Original wheel alloy {key} {order}"
        for order,obj in enumerate(pieces.get("brakedisk",()),1):
            obj.name=f"Disc rotor {key} {order}"
        radius = span.z/2
        side = 1 if center.x>0 else -1
        x_face = center.x + side*(span.x*.32)
        base=(x_face,center.y+.130,center.z+radius*.333)
        neck=(x_face+side*.010,base[1]-.008,base[2]-.007)
        cap=(x_face+side*.016,base[1]-.012,base[2]-.011)
        tube(f"Nickel valve stem {key}",[base,neck],.0034,valve_metal,rotating,sides=10)
        tube(f"Rubber valve cap {key}",[neck,cap],.0042,valve_rubber,rotating,sides=10)
        pivots[key]=(suspension,steering,rotating)
    vehicle["wheelbaseMeters"]=float(pivots["FL"][0].location.y-pivots["RL"][0].location.y)
    return pivots


def build_lights(chassis):
    optics=bpy.data.materials["Clear lamp optics"]
    tails=bpy.data.materials["TailEmission"]
    ambers=bpy.data.materials["Amber indicator optics"]
    active = {
        "HeadlightEmission": (optics,(.78,.87,1),.08),
        "HighBeamEmission": (optics,(.92,.95,1),.08),
        "ReverseEmission": (optics,(.88,.94,1),.035),
        "FrontIndicator_L": (ambers,(.79,.22,.008),.11),
        "FrontIndicator_R": (ambers,(.79,.22,.008),.11),
        "BrakeEmission": (tails,(.55,.012,.018),.13),
        "RearIndicator_L": (tails,(.55,.012,.018),.13),
        "RearIndicator_R": (tails,(.55,.012,.018),.13),
    }
    lenses={}
    for name,(original,color,level) in active.items():
        material = original.copy()
        material.name=name
        shader=material.node_tree.nodes.get("Principled BSDF")
        shader.inputs["Emission Color"].default_value=(*color,1)
        shader.inputs["Emission Strength"].default_value=level
        lenses[name]=material
    for obj in chassis.children_recursive:
        if obj.type!="MESH":
            continue
        originals=tuple(obj.data.materials)
        if not any(material in {optics,ambers,tails} for material in originals):
            continue
        indices={}
        for face in obj.data.polygons:
            x,y,z=face.center
            old=originals[face.material_index]
            side="L" if x<0 else "R"
            if old==ambers:
                if z>.44:
                    name="HeadlightEmission" if abs(x)>.60 else "HighBeamEmission"
                else:
                    name=f"FrontIndicator_{side}"
            elif old==optics and y < -2.22 and z<.39:
                name="ReverseEmission"
            elif old==tails and y < -2.22 and abs(x)>.54:
                name=f"RearIndicator_{side}" if abs(x)>.645 else "BrakeEmission"
            else:
                continue
            if name not in indices:
                indices[name]=len(obj.data.materials)
                obj.data.materials.append(lenses[name])
            face.material_index=indices[name]


def animate(vehicle,panels,axles,scene):
    markers=scene.timeline_markers
    for index,(key,title,direction) in enumerate((("L","Driver",-1),("R","Passenger",1))):
        window_name=f"Window_{key}"
        if window_name in panels:
            obj=panels[window_name]
            rest_x,_,rest_z=obj.location
            travel = obj.get("travelMeters",.40)
            lateral = obj.get("outwardMeters",.030)
            for frame, vertical in motion(-travel):
                obj.location.x=rest_x+direction*lateral*vertical/-travel
                obj.keyframe_insert(data_path="location",index=0,frame=frame)
            clip=f"{title}_Window"
            start=1+index*78
            track(obj,clip,"location",2,rest_z,motion(-travel),start)
            markers.new(clip.replace("_"," "),frame=start)
        door_name=f"Door_{key}"
        if door_name in panels:
            obj=panels[door_name]
            clip=f"{title}_Door"
            start=157+index*78
            track(obj,clip,"rotation_euler",2,0,motion(radians(direction*obj.get("travelDegrees",58))),start)
            markers.new(clip.replace("_"," "),frame=start)
    for name,degrees,start in (("Hood",52,313),("Trunk",-48,391)):
        if name in panels:
            obj=panels[name]
            track(obj,name,"rotation_euler",0,0,motion(radians(obj.get("travelDegrees",degrees))),start)
            markers.new(name,frame=start)
    steer=[(1,0),(21,radians(26)),(43,radians(-26)),(65,0)]
    if "SteeringWheel" in panels:
        track(panels["SteeringWheel"],"Steering","rotation_euler",1,0,
              [(frame,-angle*10) for frame,angle in steer],470)
    for key,(suspension,pivot_steer,wheel) in axles.items():
        if key.startswith("F"):
            track(pivot_steer,"Steering","rotation_euler",2,0,steer,470)
        track(suspension,"Suspension","location",2,suspension.location.z,
              [(1,0),(18,.039),(36,-.024),(55,0)],532)
        track(wheel,"Wheel_Rotation","rotation_euler",0,0,
              [(1,0),(26,-2*pi),(51,-4*pi)],588,linear=True)
    markers.new("Steering",frame=470)
    markers.new("Suspension",frame=532)
    markers.new("Wheel rotation",frame=588)
    track(vehicle,"Turntable","rotation_euler",2,0,[(1,0),(241,2*pi)],644,linear=True)
    markers.new("Turntable",frame=644)
    scene.frame_end=884
    scene.frame_set(1)


def export(root, path):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in [root,*root.children_recursive]:
        obj.select_set(True)
    bpy.context.view_layer.objects.active=root
    bpy.ops.export_scene.gltf(
        filepath=str(path),export_format="GLB",use_selection=True,export_yup=True,
        export_animations=True,export_animation_mode="NLA_TRACKS",
        export_anim_slide_to_zero=True,export_optimize_animation_size=True,
        export_optimize_animation_keep_anim_object=False,export_extras=True,
        export_keep_originals=False,export_shared_accessors=True,export_tangents=True,export_apply=True,
        export_copyright=f"Original vehicle by {AUTHOR}, CC BY 4.0. Refinish and animation are modifications.",
        export_cameras=False,export_lights=False,
    )


def main():
    cli=argparse.ArgumentParser(description="Refinish and animate the supplied Vecarz Mustang.")
    cli.add_argument("--source",type=Path,required=True)
    cli.add_argument("--out",type=Path,default=WORKSPACE/"assets")
    args=cli.parse_args(sys.argv[sys.argv.index("--")+1:])
    output=args.out.resolve()
    output.mkdir(parents=True,exist_ok=True)
    scene,vehicle,chassis,objects=import_model(args.source.resolve())
    from source_panels import build_panels
    panels=build_panels(chassis,objects)
    for obj in tuple(chassis.children_recursive):
        if obj.type=="MESH" and not obj.data.polygons:
            bpy.data.objects.remove(obj,do_unlink=True)
    axles=build_wheels(vehicle,[obj for obj in chassis.children_recursive if obj.type=="MESH"])
    for obj in tuple(chassis.children_recursive):
        if obj.type!="MESH" or not obj.data.materials:
            continue
        material=obj.data.materials[0].name
        if material.startswith("LicPlate_"):
            bpy.data.objects.remove(obj,do_unlink=True)
    finishes()
    build_exhaust(chassis)
    build_lights(chassis)
    build_restomod(chassis,panels)
    animate(vehicle,panels,axles,scene)
    build_black_studio()
    bpy.ops.file.pack_all()
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.region_3d.view_perspective="CAMERA"
                area.spaces.active.overlay.show_overlays=False
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(output/"mustang-jet-black.blend"),compress=True)
    export(vehicle,output/"mustang-jet-black.glb")
    print(f"Jet-black model ready. Rig controls: {', '.join(panels)}",flush=True)


if __name__=="__main__":
    main()
