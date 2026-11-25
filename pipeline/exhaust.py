import bpy
from mathutils import Vector

from geometry import lathe, pivot
from materials import pbr

MOUTH = Vector((-.444, -2.269, .291))
DIRECTION = Vector((0, -1, .066)).normalized()
OUTLET_DISTANCE = .46
ORIGIN = MOUTH - DIRECTION * OUTLET_DISTANCE


def build_exhaust(chassis):
    previous = bpy.data.objects.get("Object_34")
    if previous is None or previous.parent != chassis or previous.type != "MESH" or len(previous.data.polygons) != 9344:
        raise RuntimeError("The original Mustang side-exit exhaust could not be identified.")
    bpy.data.objects.remove(previous, do_unlink=True)
    steel = pbr("Brushed titanium muffler", (.39, .37, .33), .35, .92)
    lip = pbr("Satin steel outlet", (.66, .64, .60), .26, .93)
    soot = pbr("Exhaust bore", (.013, .011, .009), .62, .25)
    axis = DIRECTION.to_track_quat("Z", "Y").to_matrix()

    def revolve(name, profile, material, segments=64):
        obj = lathe(name, (0, 0, 0), profile, 2, material, chassis, segments=segments)
        for vertex in obj.data.vertices:
            vertex.co = ORIGIN + axis @ vertex.co
        obj.data.update()
        return obj

    revolve("Rear left N1 titanium muffler", [
        (-.025, .032), (0, .033), (.037, .062), (.055, .069), (.069, .070),
        (.292, .070), (.313, .066), (.353, .048), (.360, .044),
        (.350, .038), (.310, .060), (.061, .064), (.008, .028), (-.025, .028),
    ], steel)
    revolve("Short rolled-rim exhaust outlet", [
        (.340, .045), (.369, .048), (.388, .055), (.403, .064), (.416, .068),
        (.435, .071), (.448, .073), (.455, .073), (.460, .070), (.460, .063),
        (.456, .060), (.450, .059), (.427, .059), (.401, .055),
        (.375, .047), (.348, .041),
    ], lip, segments=80)
    revolve("Dark recessed exhaust bore", [
        (.346, .001), (.346, .041), (.382, .050), (.413, .058),
        (.441, .0585), (.441, .0565), (.385, .046), (.350, .001),
    ], soot)
    outlet = pivot("Exhaust_Outlet", tuple(MOUTH), chassis)
    pivot("Exhaust_Outlet_Aim", tuple(MOUTH + DIRECTION * .1), outlet)
