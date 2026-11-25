from math import cos, pi, sin

import bmesh
import bpy
from mathutils import Vector


def sample(stations, value):
    """Interpolate one or more values with a shape-preserving cubic."""
    def slope(index, column):
        if index == 0 or index == len(stations) - 1:
            first = min(max(index - 1, 0), len(stations) - 2)
            return (stations[first + 1][column] - stations[first][column]) / (
                stations[first + 1][0] - stations[first][0]
            )
        a, b, c = stations[index - 1:index + 2]
        m0 = (b[column] - a[column]) / (b[0] - a[0])
        m1 = (c[column] - b[column]) / (c[0] - b[0])
        return 2 * m0 * m1 / (m0 + m1) if m0 * m1 > 0 else 0

    next_index = next((index for index, row in enumerate(stations[1:], 1) if value <= row[0]),
                      len(stations) - 1)
    a, b = stations[next_index - 1:next_index + 1]
    length = b[0] - a[0]
    t = max(0, min(1, (value - a[0]) / length))
    return tuple(
        (2*t**3 - 3*t*t + 1) * a[column] + (t**3 - 2*t*t + t) * length * slope(next_index - 1, column)
        + (-2*t**3 + 3*t*t) * b[column] + (t**3 - t*t) * length * slope(next_index, column)
        for column in range(1, len(a))
    )


def parent_world(obj, parent):
    if parent is not None:
        bpy.context.view_layer.update()
        obj.parent = parent
        obj.matrix_parent_inverse = parent.matrix_world.inverted()
    return obj


def pivot(name, location, parent=None):
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    obj.empty_display_size = .09
    return parent_world(obj, parent)


def mesh(name, vertices, faces, material, parent, *, uv=None, smooth=True, enclosed=True):
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.update()
    if enclosed:
        bm = bmesh.new()
        bm.from_mesh(data)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(data)
        bm.free()
    layer = data.uv_layers.new(name="UVMap")
    for polygon in data.polygons:
        polygon.use_smooth = smooth
        values = [uv[data.loops[index].vertex_index] for index in polygon.loop_indices] if uv else []
        for order, index in enumerate(polygon.loop_indices):
            if values:
                u, v = values[order]
                if max(point[0] for point in values) - min(point[0] for point in values) > .8:
                    u += 1 if u < .2 else 0
                layer.data[index].uv = (u, v)
            else:
                point = data.vertices[data.loops[index].vertex_index].co
                axis = max(range(3), key=lambda direction: abs(polygon.normal[direction]))
                layer.data[index].uv = tuple(point[direction] for direction in range(3) if direction != axis)
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    data.materials.append(material)
    return parent_world(obj, parent)


def panel(name, coordinates, material, parent, *, thickness=(0, 0, -.008), smooth=True):
    rows, columns = len(coordinates), len(coordinates[0])
    top = [point for row in coordinates for point in row]
    count = len(top)
    vertices = top + [tuple(a+b for a, b in zip(point, thickness)) for point in top]
    faces = []
    for row in range(rows - 1):
        for col in range(columns - 1):
            i = row * columns + col
            q = (i, i + columns, i + columns + 1, i + 1)
            faces.extend((q, tuple(count + index for index in reversed(q))))
    boundary = list(range(columns)) + [row * columns + columns - 1 for row in range(1, rows)]
    boundary += [(rows-1)*columns + col for col in range(columns-2, -1, -1)]
    boundary += [row*columns for row in range(rows-2, 0, -1)]
    for a, b in zip(boundary, boundary[1:] + boundary[:1]):
        faces.append((a, b, b + count, a + count))
    # Keep the panels smooth and retain crisp edges at the stamped lips.
    obj = mesh(name, vertices, faces, material, parent, smooth=smooth,
               uv=[(col/(columns-1), row/(rows-1)) for row in range(rows) for col in range(columns)] * 2)
    for polygon in obj.data.polygons:
        if polygon.index >= 2*(rows-1)*(columns-1):
            polygon.use_smooth = False
    return obj


def tube(name, points, radius, material, parent, *, sides=10, closed=False):
    points = [Vector(point) for point in points]
    vertices = []
    for index, point in enumerate(points):
        previous = points[index - 1] if index or closed else point
        following = points[(index + 1) % len(points)] if index < len(points) - 1 or closed else point
        direction = (following - previous).normalized()
        axis = Vector((0, 0, 1)) if abs(direction.z) < .85 else Vector((0, 1, 0))
        across = direction.cross(axis).normalized()
        if index:
            projected = old_across - old_across.dot(direction) * direction
            if projected.length > .05:
                across = projected.normalized()
        around = direction.cross(across)
        old_across = across
        for side in range(sides):
            angle = 2*pi*side/sides
            vertices.append(tuple(point + radius * (cos(angle) * across + sin(angle) * around)))
    faces = []
    for row in range(len(points) - 1 + int(closed)):
        a, b = row * sides, ((row + 1) % len(points)) * sides
        for side in range(sides):
            following = (side + 1) % sides
            faces.append((a+side, b+side, b+following, a+following))
    if not closed:
        faces.extend((tuple(reversed(range(sides))), tuple(range(len(vertices)-sides, len(vertices)))))
    return mesh(name, vertices, faces, material, parent)


def bevel(obj, radius, segments=3):
    if radius:
        edge = obj.modifiers.new("Edge radius", "BEVEL")
        edge.width = radius
        edge.segments = segments
        edge.harden_normals = True
        normals = obj.modifiers.new("Weighted corner normals", "WEIGHTED_NORMAL")
        normals.keep_sharp = True
    return obj


def box(name, center, dimensions, material, parent, *, radius=.006, segments=3):
    x, y, z = center
    a, b, c = (dimension / 2 for dimension in dimensions)
    vertices = [(x+dx*a, y+dy*b, z+dz*c) for dx,dy,dz in
                ((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))]
    faces = [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    edge_radius = min(radius, min(dimensions)*.48)
    return bevel(mesh(name, vertices, faces, material, parent, smooth=False), edge_radius, segments)


def lathe(name, center, profile, axis, material, parent, *, segments=64, radius_offset=None):
    vertices, uv, faces = [], [], []
    for band, (offset, radius) in enumerate(profile):
        for segment in range(segments):
            angle = 2*pi*segment/segments
            outer = radius + (radius_offset(offset, angle) if radius_offset else 0)
            coords = [0., 0., 0.]
            coords[axis] = offset
            coords[(axis+1) % 3] = cos(angle)*outer
            coords[(axis+2) % 3] = sin(angle)*outer
            vertices.append(tuple(a+b for a, b in zip(center, coords)))
            uv.append((segment/segments, band/len(profile)))
    for band in range(len(profile)):
        a, b = band*segments, ((band+1) % len(profile))*segments
        for segment in range(segments):
            following = (segment+1) % segments
            faces.append((a+segment, a+following, b+following, b+segment))
    return mesh(name, vertices, faces, material, parent, uv=uv)


def plate(name, contour, material, parent, depth=(0, -.009, 0), radius=.004):
    n = len(contour)
    back = [tuple(a+b for a, b in zip(point, depth)) for point in contour]
    faces = [tuple(range(n)), tuple(reversed(range(n, 2*n)))]
    for index in range(n):
        after = (index+1) % n
        faces.append((index, after, after+n, index+n))
    return bevel(mesh(name, list(contour)+back, faces, material, parent, smooth=False), radius)
