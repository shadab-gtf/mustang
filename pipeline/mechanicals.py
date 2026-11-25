"""Mustang cabin, engine bay, chassis and articulate interior trim, in metres."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import cos, pi, sin, tau
from typing import Protocol

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Vector


Point = tuple[float, float, float]
Material = bpy.types.Material
Object = bpy.types.Object


class VehicleContext(Protocol):
    root: Object
    doors: Mapping[str, Object]
    steering: Object
    engine: Object
    trunk: Object
    detail: int


class MeshBatch:
    def __init__(self, name: str, parent: Object) -> None:
        self.name = name
        self.parent = parent
        self.vertices: list[Point] = []
        self.faces: list[tuple[int, ...]] = []
        self.face_attributes: list[tuple[int, bool]] = []
        self.materials: list[Material] = []

    def loft(
        self,
        material: Material,
        rings: Sequence[Sequence[Point]],
        *,
        closed: bool = False,
        smooth: bool = True,
        cap: bool = True,
    ) -> None:
        if material not in self.materials:
            self.materials.append(material)
        material_index = self.materials.index(material)
        start = len(self.vertices)
        width = len(rings[0])
        self.vertices.extend(point for ring in rings for point in ring)
        for index in range(len(rings) if closed else len(rings) - 1):
            first = start + index * width
            second = start + ((index + 1) % len(rings)) * width
            for offset in range(width):
                following = (offset + 1) % width
                self.faces.append((first + offset, first + following, second + following, second + offset))
                self.face_attributes.append((material_index, smooth))
        if not closed and cap:
            end = start + (len(rings) - 1) * width
            self.faces.extend((tuple(reversed(range(start, start + width))), tuple(range(end, end + width))))
            self.face_attributes.extend(((material_index, False), (material_index, False)))

    def panel(
        self, material: Material, outline: Sequence[Point], offset: Point
    ) -> None:
        back = [tuple(Vector(point) + Vector(offset)) for point in outline]
        self.loft(material, (outline, back), smooth=False)

    def finish(self) -> Object:
        mesh = bpy.data.meshes.new(self.name)
        inverse = self.parent.matrix_world.inverted()
        mesh.from_pydata([inverse @ Vector(point) for point in self.vertices], [], self.faces)
        for material in self.materials:
            mesh.materials.append(material)
        for face, (material_index, smooth) in zip(mesh.polygons, self.face_attributes, strict=True):
            face.material_index = material_index
            face.use_smooth = smooth

        editable = bmesh.new()
        editable.from_mesh(mesh)
        bmesh.ops.recalc_face_normals(editable, faces=list(editable.faces))
        editable.to_mesh(mesh)
        editable.free()
        mesh.update()

        uv = mesh.uv_layers.new(name="UVMap").uv
        projection = ((1, 2), (0, 2), (0, 1))
        for face in mesh.polygons:
            axis = max(range(3), key=lambda index: abs(face.normal[index]))
            u, v = projection[axis]
            for loop_index in face.loop_indices:
                point = mesh.vertices[mesh.loops[loop_index].vertex_index].co
                uv[loop_index].vector = (point[u] * 9, point[v] * 9)

        part = bpy.data.objects.new(self.name, mesh)
        self.parent.users_collection[0].objects.link(part)
        part.parent = self.parent
        return part


def box_rings(
    center: Point,
    dimensions: Point,
    radius: float,
    *,
    tilt: float = 0.0,
    bevel_segments: int = 4,
) -> list[list[Point]]:
    half_x, half_y, half_z = (value / 2 for value in dimensions)
    bevel = min(radius, half_x * 0.92, half_y * 0.92, half_z * 0.92)
    end_angle = pi / 2
    profile = [(-half_z, bevel * 0.12), (-half_z + bevel * 0.25, bevel * 0.68)]
    profile.extend(((-half_z + bevel, bevel), (half_z - bevel, bevel)))
    profile.extend(((half_z - bevel * 0.25, bevel * 0.68), (half_z, bevel * 0.12)))
    rings: list[list[Point]] = []
    for height, ring_radius in profile:
        ring: list[Point] = []
        for corner, (sign_x, sign_y) in enumerate(((1, 1), (-1, 1), (-1, -1), (1, -1))):
            for index in range(bevel_segments + 1):
                angle = end_angle * (corner + index / bevel_segments)
                x = (half_x - bevel) * sign_x + ring_radius * cos(angle)
                y = (half_y - bevel) * sign_y + ring_radius * sin(angle)
                ring.append((
                    center[0] + x,
                    center[1] + y * cos(tilt) - height * sin(tilt),
                    center[2] + y * sin(tilt) + height * cos(tilt),
                ))
        rings.append(ring)
    return rings


def rounded(
    batch: MeshBatch,
    material: Material,
    center: Point,
    dimensions: Point,
    radius: float,
    *,
    tilt: float = 0.0,
    segments: int = 3,
) -> None:
    batch.loft(material, box_rings(center, dimensions, radius, tilt=tilt, bevel_segments=segments))


def sweep(
    batch: MeshBatch,
    material: Material,
    points: Sequence[Point],
    radius: float | Sequence[float],
    *,
    segments: int = 12,
    closed: bool = False,
) -> None:
    centers = [Vector(point) for point in points]
    rings: list[list[Point]] = []
    last = len(centers) - 1
    normal: Vector | None = None
    for index, point in enumerate(centers):
        previous = centers[(index - 1) % len(centers) if closed else max(0, index - 1)]
        following = centers[(index + 1) % len(centers) if closed else min(last, index + 1)]
        tangent = (following - previous).normalized()
        if normal is None:
            normal = tangent.orthogonal().normalized()
        else:
            normal = (normal - tangent * tangent.dot(normal)).normalized()
        binormal = tangent.cross(normal)
        width = radius if isinstance(radius, (int, float)) else radius[index]
        rings.append([
            tuple(point + (cos(angle) * normal + sin(angle) * binormal) * width)
            for step in range(segments)
            for angle in (tau * step / segments,)
        ])
    batch.loft(material, rings, closed=closed)


def pipe(
    batch: MeshBatch,
    material: Material,
    points: Sequence[Point],
    radius: float,
    *,
    sections: int = 4,
    segments: int = 12,
) -> None:
    control = [Vector(point) for point in (points[0], *points, points[-1])]
    curve: list[Point] = []
    for a, b, c, d in zip(control, control[1:], control[2:], control[3:]):
        for step in range(sections):
            t = step / sections
            curve.append(tuple(0.5 * (
                2 * b + (c - a) * t + (2 * a - 5 * b + 4 * c - d) * t**2
                + (d - a + 3 * (b - c)) * t**3
            )))
    curve.append(points[-1])
    sweep(batch, material, curve, radius, segments=segments)


def ring_points(
    center: Point, radius: float, steps: int, plane: str = "xz"
) -> list[Point]:
    x, y, z = center
    if plane == "xy":
        return [(x + radius * cos(tau*i/steps), y + radius * sin(tau*i/steps), z) for i in range(steps)]
    return [(x + radius * cos(tau*i/steps), y, z + radius * sin(tau*i/steps)) for i in range(steps)]


def surface(
    name: str,
    color: Point,
    roughness: float,
    *,
    metallic: float = 0,
    emission: bool = False,
    texture: str = "",
) -> Material:
    existing = bpy.data.materials.get(name)
    if existing is not None:
        return existing
    value = bpy.data.materials.new(name)
    value.diffuse_color = (*color, 1)
    value.use_nodes = True
    shader = value.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metallic
    if emission:
        shader.inputs["Emission Color"].default_value = (0.20, 0.42, 0.32, 1)
        shader.inputs["Emission Strength"].default_value = 0.14
    if texture:
        apply_texture(value, shader, texture, roughness)
    return value


def apply_texture(
    material: Material, shader: bpy.types.Node, pattern: str, roughness: float
) -> None:
    size = 1024
    axis = np.linspace(0, tau, size, endpoint=False, dtype=np.float32)
    u, v = np.meshgrid(axis, axis)
    rng = np.random.default_rng(1967)
    noise = rng.random((size, size), dtype=np.float32) - 0.5
    if pattern == "vinyl":
        grain = np.sin(39*u + np.cos(29*v)) * np.cos(31*v + np.sin(24*u))
        grain += 0.32 * np.cos(78*u - 17*v) * np.sin(39*v + 10*u)
        height = 0.65*grain + 0.15*noise
    else:
        weave = np.sin(64*u) * np.cos(62*v) + 0.33 * np.cos(127*u + 2*v)
        height = 0.75*weave + 0.40*noise

    dx = np.roll(height, 1, 1) - np.roll(height, -1, 1)
    dy = np.roll(height, 1, 0) - np.roll(height, -1, 0)
    vector = np.dstack((dx, dy, np.full_like(dx, 2.3)))
    normal = 0.5 + 0.5 * vector / np.linalg.norm(vector, axis=2, keepdims=True)
    rough = np.clip(roughness + height * 0.095, 0, 1)
    images = (("Normal", normal), ("Roughness", np.repeat(rough[:, :, None], 3, axis=2)))
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    for kind, channels in images:
        image = bpy.data.images.new(f"{material.name}_{kind}_{size}", width=size, height=size, alpha=False)
        image.colorspace_settings.name = "Non-Color"
        pixels = np.dstack((channels, np.ones((size, size), dtype=np.float32)))
        image.pixels.foreach_set(pixels.ravel())
        image.pack()
        node = nodes.new("ShaderNodeTexImage")
        node.image = image
        if kind == "Normal":
            converter = nodes.new("ShaderNodeNormalMap")
            links.new(node.outputs["Color"], converter.inputs["Color"])
            links.new(converter.outputs["Normal"], shader.inputs[kind])
        else:
            links.new(node.outputs["Color"], shader.inputs[kind])


@dataclass(frozen=True)
class Finishes:
    leather: Material
    insert: Material
    carpet: Material
    plastic: Material
    seam: Material
    satin: Material
    chrome: Material
    lens: Material
    dash_glow: Material
    red: Material
    steel: Material
    cast: Material
    coat: Material
    heat: Material
    hose: Material


def finishes(detail: int) -> Finishes:
    return Finishes(
        leather=surface("Cabin charcoal vinyl", (0.022, 0.021, 0.024), 0.59, texture="vinyl" if detail < 2 else ""),
        insert=surface("Cabin seat inserts", (0.035, 0.031, 0.029), 0.74),
        carpet=surface("Cabin low-pile carpet", (0.021, 0.019, 0.017), 0.89, texture="carpet" if detail < 2 else ""),
        plastic=surface("Cabin matte phenolic", (0.011, 0.011, 0.015), 0.62),
        seam=surface("Cabin topstitch", (0.12, 0.112, 0.102), 0.83),
        satin=surface("Brushed cabin aluminium", (0.35, 0.37, 0.40), 0.37, metallic=0.8),
        chrome=surface("Polished chrome hardware", (0.70, 0.73, 0.75), 0.19, metallic=0.92),
        lens=surface("Instrument glass face", (0.012, 0.020, 0.023), 0.22),
        dash_glow=surface("DashEmission", (0.48, 0.54, 0.48), 0.52, emission=True),
        red=surface("Gauge needles and belt latches", (0.58, 0.029, 0.018), 0.43),
        steel=surface("Satin steel", (0.37, 0.385, 0.40), 0.29, metallic=0.85),
        cast=surface("Textured dark cast iron", (0.11, 0.12, 0.125), 0.49, metallic=0.72),
        coat=surface("RB26 champagne alloy covers", (0.35, 0.33, 0.255), 0.31, metallic=0.66),
        heat=surface("Heat-stained exhaust alloy", (0.21, 0.132, 0.079), 0.42, metallic=0.76),
        hose=surface("Engine elastomer", (0.014, 0.015, 0.017), 0.64),
    )


def lettering(
    name: str,
    parent: Object,
    material: Material,
    center: Point,
    text: str,
    size: float,
    rotation: Point,
) -> None:
    font = bpy.data.curves.new(name, "FONT")
    font.body = text
    font.size = size
    font.align_x = "CENTER"
    font.align_y = "CENTER"
    font.resolution_u = 3
    font.extrude = 0.00012
    stamp = bpy.data.objects.new(name, font)
    parent.users_collection[0].objects.link(stamp)
    stamp.parent = parent
    stamp.matrix_parent_inverse = parent.matrix_world.inverted()
    stamp.location = center
    stamp.rotation_euler = Euler(rotation)
    font.materials.append(material)
    view_layer = bpy.context.view_layer
    view_layer.update()
    graph = bpy.context.evaluated_depsgraph_get()
    engraved = bpy.data.meshes.new_from_object(stamp.evaluated_get(graph))
    editable = bmesh.new()
    editable.from_mesh(engraved)
    bmesh.ops.remove_doubles(editable, verts=list(editable.verts), dist=0.000001)
    bmesh.ops.dissolve_degenerate(editable, edges=list(editable.edges), dist=0.000001)
    bmesh.ops.triangulate(editable, faces=list(editable.faces))
    bmesh.ops.delete(editable, geom=[face for face in editable.faces if face.calc_area() <= 1e-12], context="FACES_ONLY")
    bmesh.ops.delete(editable, geom=[edge for edge in editable.edges if not edge.link_faces], context="EDGES")
    editable.to_mesh(engraved)
    editable.free()
    if not engraved.uv_layers:
        uv = engraved.uv_layers.new(name="UVMap").uv
        for loop in engraved.loops:
            uv[loop.index].vector = engraved.vertices[loop.vertex_index].co.xy
    else:
        engraved.uv_layers.active.name = "UVMap"
    badge = bpy.data.objects.new(name, engraved)
    parent.users_collection[0].objects.link(badge)
    badge.parent = parent
    badge.matrix_basis = parent.matrix_world.inverted() @ stamp.matrix_world
    bpy.data.objects.remove(stamp, do_unlink=True)
    bpy.data.curves.remove(font)


def build_floor(parent: Object, m: Finishes) -> None:
    floor = MeshBatch("Cabin floor, lining and parcel shelf", parent)
    outline = (
        (-0.71, -1.26, 0.467), (0.71, -1.26, 0.467), (0.71, 0.56, 0.467),
        (0.48, 0.69, 0.467), (-0.48, 0.69, 0.467), (-0.71, 0.56, 0.467),
    )
    floor.panel(m.carpet, outline, (0, 0, -0.035))
    tunnel = (
        (-0.19, 0.63, 0.475), (0.19, 0.63, 0.475), (0.167, 0.63, 0.574),
        (0.11, 0.63, 0.61), (-0.11, 0.63, 0.61), (-0.167, 0.63, 0.574),
    )
    floor.loft(m.carpet, (tunnel, [(x*0.88, -0.93, z-0.027) for x, _, z in tunnel]), smooth=False)
    rounded(floor, m.carpet, (0, -1.245, 0.760), (1.20, 0.14, 0.045), 0.015)
    lining = [(-0.64,0.588,1.208,1.244),(-0.52,0.619,1.228,1.267),
              (-0.30,0.633,1.238,1.282),(-0.10,0.632,1.238,1.277),(0.057,0.603,1.212,1.248)]
    rings = []
    for y, width, edge, crown in lining:
        section = [(x, y, crown-(crown-edge)*(abs(x)/width)**2.6) for index in range(17) for x in (width*(index/8-1),)]
        rings.append([*section,*[(x, y, z-0.009) for x,y,z in reversed(section)]])
    floor.loft(m.carpet,rings)
    for side in (-1, 1):
        floor.panel(m.leather, (
            (side*0.692, -1.255, 0.49), (side*0.720, -1.255, 0.80),
            (side*0.722, -0.74, 0.93), (side*0.743, -0.59, 0.88),
            (side*0.740, -0.53, 0.48),
        ), (-side*0.036, 0, 0))
        rounded(floor, m.satin, (side*0.738, 0.006, 0.482), (0.054, 1.10, 0.012), 0.004)
    floor.finish()


def build_seats(parent: Object, m: Finishes, detail: int) -> None:
    seats = MeshBatch("Pleated front buckets and folding rear seats", parent)
    for x in (-0.36, 0.36):
        rounded(seats, m.leather, (x, -0.218, 0.548), (0.476, 0.526, 0.129), 0.058)
        rounded(seats, m.insert, (x, -0.198, 0.601), (0.358, 0.407, 0.043), 0.015)
        rounded(seats, m.leather, (x, -0.451, 0.768), (0.453, 0.124, 0.383), 0.056, tilt=0.22)
        rounded(seats, m.insert, (x, -0.392, 0.772), (0.334, 0.045, 0.287), 0.017, tilt=0.22)
        rounded(seats, m.leather, (x, -0.505, 0.963), (0.305, 0.110, 0.071), 0.031, tilt=0.22)
        for offset in (-0.17, 0.17):
            rounded(seats, m.cast, (x+offset, -0.217, 0.486), (0.035, 0.431, 0.029), 0.005)
        if detail >= 2:
            continue
        for step in range(-6, 7):
            rib_x = x + step*0.024
            pipe(seats, m.leather, ((rib_x, -0.388, 0.614), (rib_x, -0.27, 0.622), (rib_x, -0.058, 0.621), (rib_x, -0.02, 0.61)), 0.0038, segments=5)
            pipe(seats, m.leather, ((rib_x, -0.344, 0.639), (rib_x, -0.361, 0.733), (rib_x, -0.394, 0.885)), 0.0036, segments=5)
        for sign in (-1, 1):
            pipe(seats, m.seam, ((x+sign*0.169, -0.405, 0.609), (x+sign*0.180, -0.372, 0.613), (x+sign*0.180, -0.056, 0.615), (x+sign*0.167, 0.006, 0.607)), 0.00115, segments=5)
            pipe(seats, m.seam, ((x+sign*0.159, -0.339, 0.633), (x+sign*0.170, -0.353, 0.709), (x+sign*0.168, -0.403, 0.903)), 0.00115, segments=5)

    rounded(seats, m.leather, (0, -0.977, 0.541), (1.223, 0.460, 0.133), 0.055)
    rounded(seats, m.leather, (0, -1.178, 0.668), (1.218, 0.113, 0.242), 0.041, tilt=0.29)
    if detail < 2:
        for x in (-0.306, 0.306):
            rounded(seats, m.insert, (x, -0.955, 0.600), (0.446, 0.326, 0.033), 0.010)
            rounded(seats, m.insert, (x, -1.122, 0.677), (0.444, 0.037, 0.168), 0.012, tilt=0.29)
    seats.finish()


def build_door_card(parent: Object, m: Finishes, sign: int, detail: int) -> None:
    name = "Left" if sign < 0 else "Right"
    card = MeshBatch(f"{name} door vinyl, armrest, crank and latch", parent)
    profile = ((-0.728, 0.475), (0.38, 0.476), (0.535, 0.534), (0.560, 0.779),
               (0.487, 0.824), (-0.661, 0.816), (-0.751, 0.782))
    card.panel(m.leather, [(sign*0.758, y, z) for y, z in profile], (-sign*0.034, 0, 0))
    if detail < 2:
        top = [(-0.700, 0.719), (-0.678, 0.760), (-0.615, 0.788), (0.412, 0.796), (0.493, 0.761)]
        pipe(card, m.satin, [(sign*0.716, y, z) for y, z in top], 0.004, segments=8)
        pipe(card, m.satin, [(sign*0.715, y, z) for y,z in ((-0.54, 0.62), (-0.30, 0.612), (0.31, 0.612), (0.49, 0.674))], 0.003, segments=8)
        rounded(card, m.leather, (sign*0.708, -0.094, 0.727), (0.070, 0.380, 0.068), 0.028)
        rounded(card, m.plastic, (sign*0.667, -0.094, 0.727), (0.015, 0.297, 0.033), 0.006)
        sweep(card, m.satin, ((sign*0.725, 0.387, 0.749), (sign*0.701, 0.387, 0.749)), 0.029, segments=18)
        pipe(card, m.chrome, ((sign*0.710, 0.387, 0.749), (sign*0.691, 0.377, 0.740), (sign*0.685, 0.316, 0.716)), 0.0065, segments=10)
        sweep(card, m.plastic, ((sign*0.695, 0.316, 0.716), (sign*0.672, 0.316, 0.716)), 0.012, segments=14)
        rounded(card, m.satin, (sign*0.717, 0.170, 0.748), (0.017, 0.137, 0.030), 0.008)
        sweep(card, m.chrome, ((sign*0.703, 0.213, 0.749), (sign*0.696, 0.140, 0.753)), 0.005, segments=8)
        sweep(card, m.chrome, ((sign*0.742, -0.619, 0.794), (sign*0.742, -0.619, 0.830)), 0.0057, segments=8)
    card.finish()


def build_dash(parent: Object, m: Finishes, detail: int, *, fascia: Material | None = None) -> None:
    dash = MeshBatch("Twin-cowl dash, instruments and glovebox", parent)
    fascia = m.plastic if fascia is None else fascia
    lower = [(-0.70, 0.756), (-0.55, 0.742), (-0.21, 0.742), (0, 0.747),
             (0.22, 0.748), (0.63, 0.757), (0.70, 0.804)]
    upper = [(0.693, 0.920), (0.60, 0.977), (0.23, 0.977), (0.09, 0.936),
             (-0.12, 0.936), (-0.21, 0.983), (-0.51, 0.983), (-0.66, 0.94), (-0.711, 0.865)]
    outline = [(x, 0.480, z) for x, z in (*lower, *upper)]
    dash.loft(m.leather, (outline, [(x*0.99, 0.521, z+0.018) for x,_,z in outline],
                          [(x*0.91, 0.675, min(0.972,z)+0.009) for x,_,z in outline]))
    dash.panel(fascia, [(-0.688, 0.473, 0.803), (-0.620, 0.473, 0.928),
                           (-0.510, 0.473, 0.964), (-0.241, 0.473, 0.964),
                           (-0.103, 0.473, 0.908), (-0.124, 0.473, 0.787), (-0.587, 0.473, 0.777)],
               (0, 0.017, 0))
    glovebox = [(0.123, 0.807), (0.218, 0.772), (0.597, 0.784), (0.656, 0.827),
                (0.632, 0.929), (0.533, 0.948), (0.224, 0.939)]
    dash.panel(fascia, [(x, 0.472, z) for x,z in glovebox], (0, 0.017, 0))
    sweep(dash, m.satin, [(x, 0.467, z) for x,z in glovebox], 0.0021, segments=6, closed=True)
    rounded(dash, m.chrome, (0.524, 0.458, 0.863), (0.045, 0.016, 0.014), 0.003)

    gauges = ((-0.545, 0.865, 0.043, 21), (-0.426, 0.873, 0.060, 25),
              (-0.294, 0.874, 0.055, 23), (-0.180, 0.850, 0.035, 15))
    for index, (x, z, radius, ticks) in enumerate(gauges):
        add_gauge(dash, m, (x, 0.463, z), radius, ticks, index, detail)
    rounded(dash, m.plastic, (0.010, 0.480, 0.840), (0.223, 0.048, 0.160), 0.015)
    rounded(dash, m.satin, (0.010, 0.454, 0.818), (0.187, 0.009, 0.058), 0.004)
    rounded(dash, m.plastic, (0.010, 0.448, 0.820), (0.112, 0.009, 0.032), 0.004)
    rounded(dash, m.dash_glow, (0.010, 0.442, 0.824), (0.036, 0.003, 0.005), 0.001)
    if detail < 2:
        for x in (-0.064, 0.084):
            sweep(dash, m.chrome, ((x, 0.454, 0.818), (x, 0.447, 0.818)), 0.008, segments=12)
            sweep(dash, m.plastic, ((x, 0.447, 0.818), (x, 0.441, 0.818)), 0.0065, segments=12)
        for x in (-0.036, 0.056):
            rounded(dash, m.plastic, (x, 0.454, 0.890), (0.078, 0.015, 0.049), 0.005)
            for z in (0.876, 0.886, 0.896, 0.907):
                rounded(dash, m.satin, (x, 0.446, z), (0.061, 0.004, 0.003), 0.001, segments=1)
    dash.finish()
    if detail == 0:
        lettering("Fuel gauge typography", parent, m.dash_glow, (-0.545, 0.451, 0.848), "FUEL", 0.008, (pi/2, 0, 0))
        lettering("Speedometer typography", parent, m.dash_glow, (-0.426, 0.451, 0.851), "MPH", 0.012, (pi/2, 0, 0))
        lettering("Tachometer typography", parent, m.dash_glow, (-0.294, 0.451, 0.852), "RPM", 0.010, (pi/2, 0, 0))
        lettering("Temperature gauge typography", parent, m.dash_glow, (-0.180, 0.451, 0.837), "TEMP", 0.007, (pi/2, 0, 0))


def add_gauge(
    dash: MeshBatch, m: Finishes, center: Point, radius: float, ticks: int, index: int, detail: int,
) -> None:
    x, y, z = center
    steps = 40 if detail == 0 else 24
    sweep(dash, m.lens, ((x, y+0.012, z), (x, y-0.009, z)), radius, segments=steps)
    sweep(dash, m.chrome, ring_points((x,y-0.012,z),radius,steps), 0.0036, segments=8, closed=True)
    if detail >= 2:
        return
    for tick in range(ticks):
        angle = -pi * 0.76 + pi * 1.52 * tick / (ticks-1)
        full = radius * 0.83
        short = radius * (0.66 if tick % 4 == 0 else 0.74)
        sweep(dash,m.dash_glow,
              ((x+sin(angle)*short,y-0.011,z+cos(angle)*short), (x+sin(angle)*full,y-0.011,z+cos(angle)*full)),
              0.00105 if tick%4 == 0 else 0.00067, segments=4)
    angle = (-0.45, -1.83, -0.97, 0.43)[index]
    sweep(dash, m.red, ((x, y-0.014, z), (x+sin(angle)*radius*0.71, y-0.014, z+cos(angle)*radius*0.71)), (0.0019, 0.0007), segments=5)
    sweep(dash, m.satin, ((x,y-0.010,z),(x,y-0.015,z)), 0.0046, segments=10)


def build_steering(parent: Object, steering: Object, m: Finishes, detail: int) -> None:
    fixed = MeshBatch("Steering column and stalk", parent)
    sweep(fixed, m.plastic, ((-0.36, 0.417, 0.86), (-0.36, 0.593, 0.768)), (0.036, 0.028), segments=18)
    pipe(fixed, m.chrome, ((-0.37, 0.464, 0.834), (-0.448, 0.445, 0.831), (-0.473, 0.438, 0.845)), 0.0047)
    fixed.finish()

    wheel = MeshBatch("Three-spoke steering wheel and horn", steering)
    x, y, z = tuple(steering.matrix_world.translation)
    center = (x, y-0.015, z)
    sweep(wheel, m.leather, ring_points(center, 0.169, 64 if detail == 0 else 40), 0.0132, closed=True)
    sweep(wheel, m.chrome, ((x,y+0.023,z),(x,y-0.020,z)), (0.036, 0.044), segments=26)
    sweep(wheel, m.plastic, ((x,y-0.016,z),(x,y-0.029,z)), 0.030, segments=24)
    sweep(wheel, m.satin, ring_points((x,y-0.030,z),0.026,32), 0.00185, closed=True, segments=8)
    for side in (-1, 1):
        wheel.panel(m.satin, [(x+side*a, y-0.017, z+b) for a,b in ((0.027,0.031),(0.153,0.061),(0.157,0.033),(0.034,-0.004))], (0,0.010,0))
        pipe(wheel, m.chrome, [(x+side*a, y-0.013, z+b) for a,b in ((0.022,-0.025),(0.037,-0.109),(0.049,-0.161))], 0.0058, segments=8)
    if detail == 0:
        sweep(wheel, m.seam, ring_points((x,y+0.0005,z),0.169,80), 0.0009, closed=True, segments=5)
    wheel.finish()


def build_cabin_hardware(parent: Object, m: Finishes) -> None:
    cabin = MeshBatch("Console, pedals, belts and interior mirror", parent)
    rounded(cabin,m.leather,(0,-0.009,0.602),(0.268,0.710,0.100),0.039)
    rounded(cabin,m.satin,(0,0.199,0.650),(0.192,0.230,0.017),0.007)
    for step in range(5):
        ring = ring_points((0.003,0.199,0.656+0.009*step),0.063-0.008*step,28,"xy")
        sweep(cabin,m.hose,ring,0.006,segments=7,closed=True)
    pipe(cabin,m.chrome,((0.003,0.199,0.683),(0.005,0.192,0.718),(0.011,0.176,0.771)),0.0075,segments=12)
    cabin.loft(m.plastic,[ring_points((.011,.176,z),radius,20,"xy") for z,radius in
                         ((.761,.010),(.767,.017),(.782,.020),(.796,.015),(.802,.007))])
    sweep(cabin,m.satin,((.011,.176,.800),(.011,.176,.803)),.007,segments=12)
    pipe(cabin,m.chrome,((0.086,-0.148,0.656),(0.089,-0.034,0.710),(0.090,0.082,0.729)),0.0085)
    sweep(cabin,m.leather,((0.090,0.073,0.728),(0.090,0.184,0.742)),0.016,segments=14)
    for x, width in ((-0.54,0.060),(-0.445,0.061),(-0.347,0.044)):
        pipe(cabin,m.cast,((x,0.624,0.689),(x,0.578,0.589),(x,0.548,0.540)),0.0065,segments=8)
        rounded(cabin,m.hose,(x,0.541,0.541),(width,0.018,0.083),0.007,tilt=-0.42)
        for z in (0.520,0.538,0.556):
            rounded(cabin,m.cast,(x,0.530,z),(width*0.83,0.003,0.003),0.001,segments=1)
    for side in (-1,1):
        strap = [(side*0.68,-0.515,0.870),(side*0.61,-0.455,0.748),(side*0.58,-0.371,0.528),(side*0.56,-0.273,0.485)]
        for first, second in zip(strap, strap[1:]):
            cabin.panel(m.plastic, (first,second,(second[0]+side*0.032,*second[1:]),(first[0]+side*0.032,*first[1:])), (0,0,0.0033))
        rounded(cabin,m.plastic,(side*0.139,-0.334,0.608),(0.038,0.063,0.045),0.007,tilt=-0.3)
        rounded(cabin,m.red,(side*0.139,-0.306,0.626),(0.022,0.012,0.007),0.002)
    rounded(cabin,m.plastic,(0,0.311,1.165),(0.254,0.037,0.066),0.015)
    rounded(cabin,m.chrome,(0,0.293,1.166),(0.236,0.010,0.049),0.004)
    pipe(cabin,m.cast,((0,0.325,1.170),(0,0.359,1.198),(0,0.389,1.215)),0.009)
    cabin.finish()


def hollow_tube(
    batch: MeshBatch,
    material: Material,
    start: Point,
    end: Point,
    profile: tuple[float, float, float],
    steps: int = 32,
) -> None:
    a, b = Vector(start), Vector(end)
    axle = (b-a).normalized()
    across = axle.orthogonal().normalized()
    up = axle.cross(across)
    inner, entry, exit = profile
    rings = []
    for center, radius in ((a, entry), (b, exit), (b, inner), (a, inner)):
        rings.append([tuple(center + radius*(cos(tau*i/steps)*across+sin(tau*i/steps)*up)) for i in range(steps)])
    batch.loft(material, rings, closed=True)


def build_engine_bay(parent: Object, m: Finishes, detail: int) -> None:
    bay = MeshBatch("Engine bay firewall, shock towers and cooling pack", parent)
    enamel = surface("Engine bay olive enamel", (0.033, 0.052, 0.034), 0.34, metallic=0.4)
    bay.panel(enamel, [(-0.695,0.724,0.472),(0.695,0.724,0.472),(0.674,0.724,0.802),
                      (0.594,0.724,0.863),(-0.594,0.724,0.863),(-0.674,0.724,0.802)], (0,0.019,0))
    for side in (-1, 1):
        profile = ((0.752,0.492),(0.868,0.738),(1.101,0.798),(1.628,0.825),
                   (1.910,0.758),(2.012,0.508),(1.812,0.414),(1.035,0.414))
        bay.panel(enamel, [(side*0.694,y,z) for y,z in profile], (-side*0.021,0,0))
        sweep(bay,enamel,((side*0.583,1.353,0.46),(side*0.573,1.355,0.671),
                          (side*0.556,1.358,0.785),(side*0.556,1.358,0.805)),(0.074,0.116,0.116,0.086),segments=26)
        sweep(bay,m.cast,((side*0.556,1.358,0.799),(side*0.556,1.358,0.813)),0.071,segments=24)
        sweep(bay,m.steel,((side*0.556,1.358,0.811),(side*0.556,1.358,0.833)),0.025,segments=18)
        if detail < 2:
            pipe(bay,m.steel,((side*0.554,1.357,0.823),(side*0.447,1.170,0.832),(side*0.222,0.752,0.843)),0.017,segments=12)
            for angle in (0.1, 2.2, 4.3):
                x, y = side*0.556+0.050*cos(angle),1.358+0.050*sin(angle)
                sweep(bay,m.steel,((x,y,0.807),(x,y,0.822)),0.0088,segments=6)
    sweep(bay,m.steel,((-0.556,1.350,0.827),(0.556,1.350,0.827)),0.014,segments=18)
    rounded(bay,m.cast,(0,1.974,0.611),(0.951,0.067,0.325),0.023)
    rounded(bay,m.steel,(0,1.980,0.785),(0.987,0.082,0.036),0.015)
    rounded(bay,m.steel,(0,1.980,0.439),(0.987,0.074,0.035),0.014)
    if detail < 2:
        for step in range(51):
            x = -0.452 + step*0.0181
            rounded(bay,m.steel,(x,1.936,0.612),(0.004,0.006,0.278),0.001,segments=1)
        for x in (-0.225,0.225):
            hollow_tube(bay,m.hose,(x,1.933,0.623),(x,1.896,0.623),(0.138,0.151,0.148))
            sweep(bay,m.cast,((x,1.933,0.623),(x,1.894,0.623)),0.038,segments=18)
            for step in range(7):
                angle = tau*step/7
                offsets = ((0.030,0.00),(0.075,0.10),(0.126,0.22),(0.134,0.44),(0.098,0.41),(0.056,0.23))
                bay.panel(m.plastic,[(x+radius*cos(angle+offset),1.902,0.623+radius*sin(angle+offset)) for radius,offset in offsets],(0,0.009,0))
        rounded(bay,m.hose,(0.487,0.895,0.604),(0.220,0.273,0.160),0.018)
        rounded(bay,m.plastic,(0.487,0.895,0.683),(0.231,0.287,0.032),0.010)
        for x, material in ((0.548,m.red),(0.424,m.cast)):
            sweep(bay,material,((x,0.960,0.693),(x,0.960,0.719)),0.022,segments=16)
            pipe(bay,m.hose,((x,0.960,0.711),(x+0.025,1.064,0.710),(0.638,1.112,0.688)),0.0077)
        sweep(bay,m.hose,((-0.481,0.734,0.748),(-0.481,0.818,0.748)),0.078,segments=26)
        rounded(bay,m.cast,(-0.482,0.854,0.749),(0.083,0.104,0.066),0.011)
        rounded(bay,m.steel,(-0.482,0.849,0.791),(0.096,0.085,0.030),0.008)
        for offset in (-0.027,0.018):
            pipe(bay,m.steel,((-0.446,0.867+offset,0.751),(-0.393,0.904+offset,0.709),(-0.375,0.871+offset,0.541),(-0.461,0.784+offset,0.433)),0.0038,segments=7)
    bay.finish()


def build_engine(parent: Object, m: Finishes, detail: int) -> None:
    engine = MeshBatch("RB26 cylinder block, cam covers and accessories", parent)
    rounded(engine,m.cast,(0,1.292,0.543),(0.312,0.885,0.256),0.035)
    rounded(engine,m.steel,(0,1.296,0.691),(0.339,0.909,0.091),0.027)
    rounded(engine,m.hose,(0,1.247,0.422),(0.329,0.649,0.112),0.032)
    rounded(engine,m.cast,(0.010,1.375,0.394),(0.260,0.361,0.096),0.036)
    for x in (-0.086,0.086):
        rounded(engine,m.coat,(x,1.290,0.763),(0.169,0.890,0.108),0.032)
        rounded(engine,m.coat,(x,1.306,0.792),(0.108,0.764,0.047),0.018)
    rounded(engine,m.steel,(0,1.277,0.804),(0.044,0.670,0.022),0.006)
    rounded(engine,m.coat,(0,1.750,0.720),(0.339,0.099,0.185),0.039)
    sweep(engine,m.hose,((0.106,1.612,0.804),(0.106,1.612,0.824)),0.033,segments=20)
    sweep(engine,m.coat,((0.106,1.612,0.823),(0.106,1.612,0.828)),0.022,segments=12)
    pulley_centers = ((0.001,1.804,0.524,0.078),(-0.121,1.807,0.578,0.046),(0.109,1.807,0.618,0.055))
    for x,y,z,radius in pulley_centers:
        sweep(engine,m.cast,((x,y-0.022,z),(x,y+0.019,z)),radius, segments=26)
        sweep(engine,m.steel,((x,y+0.014,z),(x,y+0.024,z)),radius*0.72,segments=20)
        if detail < 2:
            sweep(engine,m.coat,((x,y+0.023,z),(x,y+0.031,z)),radius*0.23,segments=10)
            for channel in (-0.012, -0.001, 0.008):
                sweep(engine,m.hose,ring_points((x,y+channel,z),radius,30),0.0021,segments=6,closed=True)
    if detail < 2:
        sweep(engine,m.hose,((0.001,1.811,0.448),(-0.143,1.811,0.534),(-0.165,1.811,0.577),
                             (-0.148,1.811,0.620),(0.102,1.811,0.672),(0.157,1.811,0.643),
                             (0.158,1.811,0.595),(0.058,1.811,0.471)),0.0066,segments=6,closed=True)
        for y in (0.936,1.069,1.207,1.343,1.481,1.618):
            for x in (-0.162,0.162):
                rounded(engine,m.cast,(x,y,0.556),(0.044,0.063,0.216),0.009,segments=2)
            for x in (-0.115,0.115):
                sweep(engine,m.steel,((x,y,0.806),(x,y,0.814)),0.0059,segments=8)
        for side in (-1,1):
            pipe(engine,m.cast,((side*0.123,1.142,0.510),(side*0.239,1.157,0.451),(side*0.341,1.183,0.415)),0.036,segments=10)
        pipe(engine,m.hose,((0.135,1.762,0.699),(0.258,1.840,0.691),(0.409,1.905,0.752),(0.433,1.964,0.759)),0.028)
        pipe(engine,m.hose,((-0.129,0.961,0.781),(-0.105,0.841,0.785),(0.038,0.829,0.789),(0.136,0.881,0.783)),0.017)
    engine.finish()
    if detail == 0:
        lettering("Nissan cam cover plate lettering",parent,m.plastic,(0,1.108,0.8154),"NISSAN",0.033,(0,0,pi/2))
        lettering("Twin cam plate lettering",parent,m.red,(0,1.373,0.8154),"TWIN CAM 24 VALVE",0.018,(0,0,pi/2))
        lettering("RB26 timing cover lettering",parent,m.steel,(-0.069,1.800,0.755),"RB26",0.023,(pi/2,0,pi))


def build_induction(parent: Object, m: Finishes, detail: int) -> None:
    induction = MeshBatch("Intake manifold, fuel rail and single turbo", parent)
    plenum = ((0.264,0.910,0.665),(0.263,1.037,0.672),(0.300,1.423,0.673),
              (0.317,1.642,0.674),(0.310,1.720,0.657))
    sweep(induction,m.steel,plenum,(0.045,0.074,0.101,0.081,0.047),segments=28)
    hollow_tube(induction,m.chrome,(0.308,1.717,0.657),(0.307,1.778,0.650),(0.041,0.054,0.051))
    flow = ((0.306,1.767,0.652),(0.321,1.864,0.646),(0.399,1.925,0.565),(0.482,2.012,0.431))
    pipe(induction,m.steel,flow,0.041,segments=20)
    for index in range(6):
        y = 0.983 + index*0.127
        pipe(induction,m.steel,((0.157,y,0.632),(0.207,y,0.627),(0.245,y-0.013,0.641),(0.303,y-0.012,0.655)),0.0235)
        pipe(induction,m.heat,((-0.147,y,0.622),(-0.220,y,0.599),(-0.281,max(1.10,y),0.557),(-0.363,1.472+index*0.023,0.610)),0.0195)
        if detail < 2:
            sweep(induction,m.coat,((0.195,y,0.660),(0.195,y,0.713)),0.0106,segments=12)
            pipe(induction,m.hose,((0.197,y,0.705),(0.204,y+0.025,0.742),(0.170,y+0.045,0.749)),0.0039,segments=8)
    sweep(induction,m.satin,((0.195,0.938,0.710),(0.195,1.665,0.710)),0.011,segments=14)

    turbo_z, turbo_x, turbo_y = 0.668, -0.414, 1.603
    scroll = [(turbo_x+sin(angle)*0.074,turbo_y+0.023*step/28,turbo_z+cos(angle)*0.074)
              for step in range(29) for angle in (tau*0.91*step/28,)]
    sweep(induction,m.steel,scroll,[0.032-0.012*step/28 for step in range(29)],segments=16)
    sweep(induction,m.heat,((turbo_x,turbo_y-0.092,turbo_z),(turbo_x,turbo_y-0.015,turbo_z)),(0.083,0.066),segments=24)
    hollow_tube(induction,m.chrome,(turbo_x,turbo_y-0.016,turbo_z),(turbo_x,turbo_y+0.077,turbo_z),(0.038,0.058,0.054))
    sweep(induction,m.cast,((turbo_x,turbo_y-0.001,turbo_z),(turbo_x,turbo_y+0.011,turbo_z)),0.038,segments=24)
    if detail < 2:
        for index in range(9):
            angle = tau*index/9
            outlines = ((0.010,0.09),(0.025,0.17),(0.035,0.42),(0.033,0.55),(0.020,0.37))
            induction.panel(m.satin,[(turbo_x+radius*cos(angle+offset),turbo_y+0.016,turbo_z+radius*sin(angle+offset)) for radius,offset in outlines],(0,-0.004,0))
    pipe(induction,m.steel,((turbo_x-0.007,1.625,0.733),(-0.503,1.683,0.734),(-0.535,1.831,0.617),(-0.505,2.001,0.444)),0.038,segments=18)
    downpipe = ((turbo_x,1.524,0.667),(-0.407,1.407,0.681),(-0.390,1.190,0.611),(-0.366,1.095,0.407),(-0.342,0.953,0.328))
    pipe(induction,m.heat,downpipe,0.041,segments=18)
    if detail < 2:
        wrap = surface("Turbo heat-wrap weave", (0.25,0.186,0.128), 0.95)
        pipe(induction,wrap,downpipe[:-1],0.044,segments=18)
        for x,y,z in ((0.307,1.795,0.648),(0.344,1.892,0.616),(-0.509,1.716,0.715),(-0.524,1.891,0.551)):
            sweep(induction,m.chrome,ring_points((x,y,z),0.045,28),0.004,segments=6,closed=True)
    induction.finish()


def build_trunk(parent: Object, lid: Object, m: Finishes, detail: int) -> None:
    trunk = MeshBatch("Trunk lining, wheel tubs and latch", parent)
    trunk.panel(m.carpet,[(-0.551,-2.192,0.511),(0.551,-2.192,0.511),(0.624,-1.607,0.511),
                         (-0.624,-1.607,0.511)],(0,0,-0.034))
    trunk.panel(m.plastic,[(-0.55,-2.196,0.51),(0.55,-2.196,0.51),(0.66,-2.197,0.786),
                          (-0.66,-2.197,0.786)],(0,0.020,0))
    trunk.panel(m.carpet,[(-0.615,-1.588,0.51),(0.615,-1.588,0.51),(0.667,-1.588,0.841),
                         (-0.667,-1.588,0.841)],(0,-0.022,0))
    for side in (-1,1):
        shell = [(side*0.59,-2.168,0.52),(side*0.671,-2.168,0.796),(side*0.688,-1.620,0.833),
                 (side*0.630,-1.621,0.71),(side*0.568,-1.626,0.52)]
        trunk.panel(m.carpet,shell,(-side*0.017,0,0))
        rounded(trunk,m.carpet,(side*0.605,-1.685,0.574),(0.190,0.181,0.123),0.046)
    if detail < 2:
        rounded(trunk,m.cast,(0,-2.163,0.782),(0.101,0.059,0.036),0.010)
        pipe(trunk,m.steel,((-0.023,-2.157,0.789),(-0.023,-2.139,0.815),(0.023,-2.139,0.815),(0.023,-2.157,0.789)),0.0048,segments=8)
        for x in (-0.15,0.0,0.15):
            rounded(trunk,m.leather,(x,-1.94,0.530),(0.010,0.351,0.008),0.003)
    trunk.finish()

    frame = MeshBatch("Deck lid inner ribs and latch tongue", lid)
    for x in (-0.31,0.31):
        pipe(frame,m.cast,((x,-1.634,0.839),(x*1.28,-1.785,0.822),(x*1.1,-2.105,0.812)),0.019,segments=9)
    sweep(frame,m.cast,((-0.558,-2.110,0.814),(0.558,-2.110,0.814)),0.019,segments=10)
    rounded(frame,m.steel,(0,-2.121,0.804),(0.070,0.064,0.023),0.008)
    frame.finish()


def spring(batch: MeshBatch, material: Material, center: Point, length: float, radius: float) -> None:
    x,y,z = center
    turns = 6
    count = turns * 13
    winding = [(x+radius*cos(tau*turns*index/count),y+radius*sin(tau*turns*index/count),z+length*index/count)
               for index in range(count+1)]
    sweep(batch,material,winding,0.0077,segments=8)


def build_running_gear(parent: Object, m: Finishes, detail: int) -> None:
    gear = MeshBatch("Transmission, exhaust, propshaft and suspension", parent)
    sweep(gear,m.cast,((0,0.913,0.505),(0,0.746,0.491),(0,0.639,0.478),(0,0.529,0.460)),
          (0.139,0.150,0.121,0.085),segments=22)
    rounded(gear,m.cast,(0,0.319,0.418),(0.198,0.509,0.203),0.065)
    for y in (0.281,0.344,0.406,0.468):
        rounded(gear,m.cast,(0,y,0.415),(0.204,0.018,0.214),0.009)
    sweep(gear,m.cast,((0,0.116,0.410),(0,0.056,0.382),(0,-0.022,0.362)),(0.087,0.060,0.045),segments=20)
    sweep(gear,m.steel,((0,-0.002,0.366),(0,-1.224,0.335)),0.035,segments=20)
    for y,z in ((-0.05,0.366),(-1.192,0.336)):
        sweep(gear,m.cast,((0,y-0.048,z),(0,y+0.047,z)),0.054,segments=14)
    sweep(gear,m.cast,((0,-1.184,0.337),(0,-1.281,0.335),(0,-1.369,0.335),(0,-1.453,0.335)),
          (0.060,0.105,0.138,0.105),segments=24)
    sweep(gear,m.cast,((-0.735,-1.372,0.335),(0.735,-1.372,0.335)),0.037,segments=16)
    rounded(gear,m.cast,(0,1.352,0.322),(1.17,0.156,0.112),0.030)
    sweep(gear,m.cast,((-0.56,1.455,0.370),(0.56,1.455,0.370)),0.023,segments=15)
    for side in (-1,1):
        x = side*0.55
        for y in (1.251,1.506):
            pipe(gear,m.cast,((side*0.392,y,0.349),(side*0.556,(y+1.372)/2,0.328),
                              (side*0.729,1.372,0.320)),0.021,segments=12)
            pipe(gear,m.cast,((side*0.507,y,0.583),(side*0.642,(y+1.372)/2,0.562),
                              (side*0.721,1.372,0.506)),0.017,segments=10)
        sweep(gear,m.steel,((x,1.455,0.370),(side*0.733,1.448,0.349)),0.010,segments=10)
        sweep(gear,m.hose,((side*0.506,1.454,0.371),(side*0.583,1.454,0.367)),(0.034,0.022),segments=14)
        sweep(gear,m.cast,((x,1.371,0.408),(x,1.371,0.584)),0.027,segments=14)
        sweep(gear,m.steel,((x,1.371,0.557),(x,1.371,0.755)),0.013,segments=12)
        spring(gear,m.cast,(x,1.371,0.438),0.304,0.055)
        pipe(gear,m.cast,((side*0.67,1.394,0.338),(side*0.507,1.604,0.299),(side*0.40,1.677,0.301)),0.013,segments=10)
        sweep(gear,m.cast,((side*0.57,-1.446,0.333),(side*0.509,-1.532,0.499)),0.027,segments=14)
        sweep(gear,m.steel,((side*0.519,-1.512,0.462),(side*0.468,-1.598,0.602)),0.012,segments=12)
        for leaf in range(4 if detail == 0 else 2):
            end = 0.67-leaf*0.095
            points = [(side*0.553,-1.372+end*(index/5-1),0.310+0.071*(index/5-1)**2-leaf*0.013,
                       ) for index in range(11)]
            rings = [[(x-0.030,y,z-0.006),(x+0.030,y,z-0.006),(x+0.030,y,z+0.006),(x-0.030,y,z+0.006)]
                     for x,y,z in points]
            gear.loft(m.cast,rings,smooth=False)
        for y in (-2.044,-0.7):
            sweep(gear,m.cast,((side*0.513,y,0.382),(side*0.592,y,0.382)),0.027,segments=14)

    exhaust = ((-0.342,0.953,0.328),(-0.368,0.597,0.278),(-0.295,0.135,0.279),(-0.287,-0.462,0.276),
               (-0.274,-0.890,0.285),(-0.254,-1.209,0.401),(-0.232,-1.468,0.423),
               (0.012,-1.630,0.378),(0.437,-1.750,0.336),(0.560,-1.935,0.339),(0.560,-2.042,0.339))
    pipe(gear,m.heat,exhaust,0.035,segments=16)
    rounded(gear,m.cast,(-0.286,-0.527,0.277),(0.167,0.449,0.135),0.054)
    hollow_tube(gear,m.chrome,(0.560,-2.041,0.340),(0.560,-2.228,0.318),(0.030,0.041,0.039))
    gear.finish()


def build_mechanicals(context: VehicleContext) -> None:
    """Build closed-rest assemblies against the existing animation pivots."""
    bpy.context.view_layer.update()
    materials = finishes(context.detail)
    build_floor(context.root, materials)
    build_seats(context.root,materials,context.detail)
    build_dash(context.root,materials,context.detail)
    build_steering(context.root,context.steering,materials,context.detail)
    for name, sign in (("L",-1),("R",1)):
        build_door_card(context.doors[name],materials,sign,context.detail)
    build_trunk(context.root,context.trunk,materials,context.detail)
    if context.detail < 2:
        build_cabin_hardware(context.root,materials)
        build_engine_bay(context.root,materials,context.detail)
        build_engine(context.engine,materials,context.detail)
        build_induction(context.engine,materials,context.detail)
        build_running_gear(context.root,materials,context.detail)
