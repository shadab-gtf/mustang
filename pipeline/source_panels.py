from collections import defaultdict
from dataclasses import dataclass, field

import bpy
from bpy.types import Mesh, Object

from geometry import parent_world, pivot


Point = tuple[float, float, float]
FaceMap = dict[Object, list[int]]
MATERIALS = ("carpaint", "windowglass", "black", "chrome", "mirror")


@dataclass
class Island:
    faces: FaceMap = field(default_factory=lambda: defaultdict(list))
    count: int = 0
    minimum: list[float] = field(default_factory=lambda: [float("inf")] * 3)
    maximum: list[float] = field(default_factory=lambda: [-float("inf")] * 3)

    def include(self, position: Point) -> None:
        for axis, value in enumerate(position):
            self.minimum[axis] = min(value, self.minimum[axis])
            self.maximum[axis] = max(value, self.maximum[axis])


def material_islands(objects: list[Object], material: str) -> list[Island]:
    """Find connected faces without welding UVs or split normals in the source."""
    positions: list[Point] = []
    parent: list[int] = []
    by_position: dict[tuple[int, int, int], int] = {}
    faces: list[tuple[Object, int, int]] = []

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def register(position: Point) -> int:
        key = tuple(round(value * 1_000_000) for value in position)
        existing = by_position.get(key)
        if existing is not None:
            return existing
        index = len(positions)
        by_position[key] = index
        parent.append(index)
        positions.append(position)
        return index

    for obj in objects:
        mesh = obj.data
        slots = {index for index, item in enumerate(mesh.materials) if item.name == material}
        if not slots:
            continue
        indices = [register(tuple(vertex.co)) for vertex in mesh.vertices]
        for polygon in mesh.polygons:
            if polygon.material_index not in slots:
                continue
            first, *others = (indices[index] for index in polygon.vertices)
            first_root = root(first)
            for index in others:
                parent[root(index)] = first_root
            faces.append((obj, polygon.index, first))

    islands: dict[int, Island] = {}
    for obj, face, index in faces:
        connected = root(index)
        if connected not in islands:
            islands[connected] = Island()
        island = islands[connected]
        island.faces[obj].append(face)
        island.count += 1
    for index, position in enumerate(positions):
        island = islands.get(root(index))
        if island is not None:
            island.include(position)
    return list(islands.values())


def target_for(material: str, island: Island) -> str | None:
    left_x, rear_y, low_z = island.minimum
    right_x, front_y, high_z = island.maximum
    side = "L" if right_x < -0.60 else "R" if left_x > 0.60 else None
    triangles = island.count
    if material == "carpaint":
        if side and triangles == 5824 and rear_y > -0.67 and front_y < 0.69:
            return f"Door_{side}"
        if triangles == 8512 and rear_y > 0.87 and front_y > 2.31:
            return "Hood"
        if triangles == 7168 and rear_y < -2.24 and front_y < -1.76:
            return "Trunk"
    if material == "windowglass" and side and triangles == 2880 and rear_y > -0.56 and front_y > 0.50:
        return f"Window_{side}"

    # The scoop, its grille and the rear wing are separate original materials.
    if material == "black":
        scoop = triangles in {18080, 6080, 56} and left_x > -0.19 and right_x < 0.19 and rear_y > 0.92 and front_y < 1.60 and low_z > 0.75
        rear_wing = triangles in {5120, 2112, 1024, 640} and rear_y > -2.19 and front_y < -1.98 and low_z > 0.84
        if scoop:
            return "Hood"
        if rear_wing:
            return "Trunk"
    if material == "chrome":
        trunk_badge = (triangles in {1080, 672, 752, 680, 800, 952, 648}
                       and rear_y > -2.252 and front_y < -2.230
                       and low_z > .797 and high_z < .826
                       and left_x > -.39 and right_x < .40)
        if trunk_badge:
            return "Trunk"
        hood_pins = triangles in {832, 500} and left_x > -0.44 and right_x < 0.44 and rear_y > 2.05 and front_y < 2.16 and low_z > 0.67
        hood_edge = triangles == 2624 and rear_y > 2.08 and front_y > 2.33 and low_z > 0.61 and high_z < 0.66
        rear_wing_mount = triangles == 480 and rear_y > -2.15 and front_y < -2.13 and low_z > 0.92 and high_z < 0.94
        if hood_pins or hood_edge:
            return "Hood"
        if rear_wing_mount:
            return "Trunk"

    if not side:
        return None

    if material == "black":
        belt_seal = triangles == 1248 and rear_y > -0.62 and front_y < 0.54 and low_z > 0.80
        mirror_stalk = triangles == 2816 and rear_y > 0.37 and front_y < 0.45 and high_z < 0.86
        if belt_seal or mirror_stalk:
            return f"Door_{side}"
    if material == "chrome":
        handle = triangles == 7040 and rear_y > -0.61 and front_y < -0.41
        lock = triangles == 162 and rear_y > -0.59 and front_y < -0.53
        mirror_shell = triangles == 3520 and rear_y > 0.34 and front_y < 0.48 and low_z > 0.81
        handle_hardware = triangles in {2024, 944} and rear_y > -0.18 and front_y < 0.32 and low_z > 0.58
        if handle or lock or mirror_shell or handle_hardware:
            return f"Door_{side}"
    if material == "mirror" and triangles == 1152 and rear_y > 0.34 and front_y < 0.41:
        return f"Door_{side}"
    return None


def extract_mesh(source: Mesh, face_indices: list[int], name: str) -> Mesh:
    """Copy only the selected polygons while retaining original corner data."""
    vertices: list[Point] = []
    index_map: dict[int, int] = {}
    faces: list[list[int]] = []
    corner_ids: list[int] = []
    slots: list[int] = []
    smooth: list[bool] = []
    polygons = source.polygons
    coords = source.vertices
    for index in face_indices:
        polygon = polygons[index]
        face = []
        for old in polygon.vertices:
            mapped = index_map.get(old)
            if mapped is None:
                mapped = len(vertices)
                index_map[old] = mapped
                vertices.append(tuple(coords[old].co))
            face.append(mapped)
        faces.append(face)
        corner_ids.extend(polygon.loop_indices)
        slots.append(polygon.material_index)
        smooth.append(polygon.use_smooth)

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    for material in source.materials:
        mesh.materials.append(material)
    mesh.polygons.foreach_set("material_index", slots)
    mesh.polygons.foreach_set("use_smooth", smooth)
    for layer in source.uv_layers:
        uv_values = layer.uv
        destination = mesh.uv_layers.new(name=layer.name)
        flattened = [value for index in corner_ids for value in uv_values[index].vector]
        destination.uv.foreach_set("vector", flattened)
    if source.has_custom_normals:
        normals = source.corner_normals
        mesh.normals_split_custom_set([tuple(normals[index].vector) for index in corner_ids])
    mesh.update()
    return mesh


def build_panels(chassis: Object, objects: list[Object]) -> dict[str, Object]:
    """Install pivots on the intact 1969 mesh without changing its closed pose."""
    destinations: dict[Object, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    primary = set()
    for material in MATERIALS:
        for island in material_islands(objects, material):
            name = target_for(material, island)
            if name is None:
                continue
            for obj, indices in island.faces.items():
                destinations[obj][name].extend(indices)
            if material in {"carpaint", "windowglass"}:
                primary.add(name)

    hinge_locations = {
        "Door_L": (-0.811, 0.690, 0.625),
        "Door_R": (0.811, 0.690, 0.625),
        "Hood": (0.0, 0.891, 0.812),
        "Trunk": (0.0, -1.785, 0.931),
    }
    pivots = {name: pivot(name, location, chassis) for name, location in hinge_locations.items() if name in primary}
    for side in ("L", "R"):
        name = f"Window_{side}"
        door = pivots.get(f"Door_{side}")
        if door is not None and name in primary:
            door["travelDegrees"] = 62
            part = pivot(name, (0, 0, 0), door)
            part["travelMeters"] = 0.365
            part["outwardMeters"] = 0.030
            pivots[name] = part

    for obj, groups in destinations.items():
        source = obj.data
        removed = set()
        for name, indices in groups.items():
            if name not in pivots:
                continue
            child_name = f"{name} • {source.materials[0].name} • {obj.name}"
            mesh = extract_mesh(source, sorted(indices), child_name)
            child = bpy.data.objects.new(child_name, mesh)
            obj.users_collection[0].objects.link(child)
            parent_world(child, pivots[name])
            removed.update(indices)
        if removed:
            remaining = [face.index for face in source.polygons if face.index not in removed]
            if remaining:
                obj.data = extract_mesh(source, remaining, source.name + " fixed")
            else:
                obj.data = bpy.data.meshes.new(source.name + " extracted")
    return pivots
