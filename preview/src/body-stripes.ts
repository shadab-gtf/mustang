import {
  BufferGeometry, Float32BufferAttribute, Matrix3, Mesh, MeshPhysicalMaterial, Vector3, type Object3D,
} from "three"

export type StripeLayout = "triple" | "single"

const LANES = [
  [-.228, -.093, "outer"],
  [-.093, -.069, "gap"],
  [-.069, .069, "center"],
  [.069, .093, "gap"],
  [.093, .228, "outer"],
] as const
const PAINT = "Jet black lacquer"

interface SurfaceVertex {
  point: Vector3
  normal: Vector3
}

interface Section {
  start: number
  end: number
  minimum: number
  scoop?: boolean
}

function clip(face: SurfaceVertex[], axis: "x" | "y" | "z", edge: number, direction: 1 | -1) {
  const result: SurfaceVertex[] = []
  for (let index = 0; index < face.length; index++) {
    const a = face[index]
    const b = face[(index + 1) % face.length]
    const distanceA = (a.point[axis] - edge) * direction
    const distanceB = (b.point[axis] - edge) * direction
    if (distanceA >= 0) result.push(a)
    if ((distanceA < 0 && distanceB > 0) || (distanceA > 0 && distanceB < 0)) {
      const t = distanceA / (distanceA - distanceB)
      result.push({
        point: a.point.clone().lerp(b.point, t),
        normal: a.normal.clone().lerp(b.normal, t),
      })
    }
  }
  return result
}

function collectStripeFaces(mesh: Mesh, section: Section, lanes: SurfaceVertex[][]) {
  const positions = mesh.geometry.getAttribute("position")
  const normals = mesh.geometry.getAttribute("normal")
  const indices = mesh.geometry.getIndex()
  const world = Array.from({ length: positions.count }, (_, i) =>
    new Vector3().fromBufferAttribute(positions, i).applyMatrix4(mesh.matrixWorld))
  const normalMatrix = new Matrix3().getNormalMatrix(mesh.matrixWorld)
  const surfaceNormal = new Vector3()
  const edge = new Vector3()
  for (let index = 0; index < (indices?.count ?? positions.count); index += 3) {
    const a = indices?.getX(index) ?? index
    const b = indices?.getX(index + 1) ?? index + 1
    const c = indices?.getX(index + 2) ?? index + 2
    const [p, q, r] = [world[a], world[b], world[c]]
    const left = Math.min(p.x, q.x, r.x)
    const right = Math.max(p.x, q.x, r.x)
    if (left >= .228 || right <= -.228 || Math.min(p.z, q.z, r.z) >= section.end ||
        Math.max(p.z, q.z, r.z) <= section.start || Math.max(p.y, q.y, r.y) <= section.minimum) continue
    surfaceNormal.subVectors(q, p).cross(edge.subVectors(r, p)).normalize()
    if (surfaceNormal.y < .08) continue

    const face = [a, b, c].map((vertex) => ({
      point: world[vertex],
      normal: new Vector3().fromBufferAttribute(normals, vertex).applyNormalMatrix(normalMatrix),
    }))
    const panelFace = clip(clip(clip(face, "z", section.start, 1), "z", section.end, -1), "y", section.minimum, 1)
    for (const [lane, [start, end]] of LANES.entries()) {
      if (left >= end || right <= start) continue
      const strip = clip(clip(panelFace, "x", start, 1), "x", end, -1)
      for (let i = 1; i + 1 < strip.length; i++) lanes[lane].push(strip[0], strip[i], strip[i + 1])
    }
  }
}

export class BodyStripes {
  private readonly materials = LANES.map(() => new MeshPhysicalMaterial({
    roughness: .34,
    metalness: .03,
    specularIntensity: .46,
    clearcoat: .56,
    clearcoatRoughness: .25,
    emissiveIntensity: .37,
    polygonOffset: true,
    polygonOffsetFactor: -1,
    polygonOffsetUnits: -1,
  }))

  constructor(chassis: Object3D, hood?: Object3D, trunk?: Object3D) {
    chassis.updateWorldMatrix(true, true)
    // End each section at a panel seam or glass edge.
    // The leading edge follows the hood stamping, including the center point.
    this.addSection(hood, { start: -2.38, end: -.895, minimum: .61, scoop: true })
    this.addSection(chassis, { start: -.252, end: .977, minimum: 1.18 })
    this.addSection(chassis, { start: 1.684, end: 1.758, minimum: .93 })
    this.addSection(trunk, { start: 1.781, end: 2.247, minimum: .86 })
  }

  set(layout: StripeLayout, color: number, center: number, visible: boolean) {
    this.materials.forEach((material, index) => {
      const role = LANES[index][2]
      material.visible = visible && (layout === "single" || role !== "gap")
      const tint = role === "center" && layout === "triple" ? center : color
      material.color.setHex(tint).multiplyScalar(.47)
      material.emissive.setHex(tint)
    })
  }

  private addSection(panel: Object3D | undefined, section: Section) {
    if (!panel) return
    const lanes: SurfaceVertex[][] = this.materials.map(() => [])
    panel.traverse((object) => {
      if (!(object instanceof Mesh) || Array.isArray(object.material)) return
      const scoopShell = section.scoop && object.material.name === "Satin black trim and chassis" &&
        object.name.endsWith("Object_50")
      if (object.material.name === PAINT || scoopShell) {
        collectStripeFaces(object, section, lanes)
      }
    })
    const geometry = new BufferGeometry()
    const vertices: number[] = []
    const normals: number[] = []
    const inverse = panel.matrixWorld.clone().invert()
    const localNormal = new Matrix3().getNormalMatrix(inverse)
    for (const [lane, faces] of lanes.entries()) {
      geometry.addGroup(vertices.length / 3, faces.length, lane)
      for (const { point, normal } of faces) {
        const position = point.clone().addScaledVector(normal, .00045).applyMatrix4(inverse)
        const direction = normal.clone().applyNormalMatrix(localNormal)
        vertices.push(position.x, position.y, position.z)
        normals.push(direction.x, direction.y, direction.z)
      }
    }
    geometry.setAttribute("position", new Float32BufferAttribute(vertices, 3))
    geometry.setAttribute("normal", new Float32BufferAttribute(normals, 3))
    const stripes = new Mesh(geometry, this.materials)
    stripes.name = "Center racing stripes"
    panel.add(stripes)
  }
}
