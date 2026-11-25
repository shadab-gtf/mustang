import { CatmullRomCurve3, Vector3 } from "three"

// Centerline traced in the reference image's coordinates, starting at the checkered line.
const TRACE = [
  [745, 514], [864, 502], [944, 486], [976, 489], [990, 513], [994, 554],
  [1010, 606], [1053, 650], [1110, 682], [1130, 700], [1094, 711], [995, 711],
  [816, 713], [624, 716], [410, 722], [208, 726], [177, 715], [175, 696],
  [219, 663], [319, 569], [392, 499], [426, 464], [444, 425], [450, 389],
  [464, 362], [454, 343], [416, 326], [366, 318], [314, 300], [286, 281],
  [275, 253], [226, 226], [167, 207], [110, 193], [81, 175], [68, 149],
  [76, 119], [104, 88], [144, 60], [181, 49], [204, 67], [221, 105],
  [236, 140], [263, 173], [302, 194], [329, 222], [363, 252], [396, 244],
  [431, 220], [467, 218], [523, 245], [580, 268], [626, 298], [645, 324],
  [641, 350], [613, 380], [576, 409], [545, 446], [513, 485], [497, 508],
  [509, 526], [546, 531], [615, 522], [688, 517],
] as const

export const ROAD_HALF_WIDTH = 8.5
export const BARRIER_OFFSET = 15
export const CIRCUIT_SPACING = 5
const SCALE = 3.2
const GRID_SIZE = 64
const SEARCH_MARGIN = BARRIER_OFFSET + 8

export function fromCircuitImage(x: number, y: number) {
  return { x: (x - TRACE[0][0]) * SCALE, z: (y - TRACE[0][1]) * SCALE }
}

const curve = new CatmullRomCurve3(TRACE.map(([x, y]) => {
  const point = fromCircuitImage(x, y)
  return new Vector3(point.x, 0, point.z)
}), true)
curve.arcLengthDivisions = 4096
const nodes = curve.getSpacedPoints(Math.ceil(curve.getLength() / CIRCUIT_SPACING)).slice(0, -1)

export const circuitSamples = nodes.map(({ x, z }, index) => {
  const previous = nodes[(index + nodes.length - 1) % nodes.length]
  const next = nodes[(index + 1) % nodes.length]
  const length = Math.hypot(next.x - previous.x, next.z - previous.z)
  return { x, z, nx: -(next.z - previous.z) / length, nz: (next.x - previous.x) / length }
})

const spawn = circuitSamples[circuitSamples.length - 8]
export const circuitSpawn = { x: spawn.x, z: spawn.z, yaw: Math.atan2(-spawn.nz, spawn.nx) }

interface Segment {
  index: number
  x: number
  z: number
  dx: number
  dz: number
  lengthSq: number
}

export interface RoadContact {
  index: number
  distance: number
  nx: number
  nz: number
}

const cells = new Map<string, Segment[]>()
for (const [index, start] of circuitSamples.entries()) {
  const end = circuitSamples[(index + 1) % circuitSamples.length]
  const dx = end.x - start.x
  const dz = end.z - start.z
  const segment = { index, x: start.x, z: start.z, dx, dz, lengthSq: dx * dx + dz * dz }
  for (let x = Math.floor((Math.min(start.x, end.x) - SEARCH_MARGIN) / GRID_SIZE);
    x <= Math.floor((Math.max(start.x, end.x) + SEARCH_MARGIN) / GRID_SIZE); x++) {
    for (let z = Math.floor((Math.min(start.z, end.z) - SEARCH_MARGIN) / GRID_SIZE);
      z <= Math.floor((Math.max(start.z, end.z) + SEARCH_MARGIN) / GRID_SIZE); z++) {
      const key = `${x},${z}`
      const existing = cells.get(key)
      if (existing) existing.push(segment)
      else cells.set(key, [segment])
    }
  }
}

export function nearestRoad(x: number, z: number, contact: RoadContact) {
  const candidates = cells.get(`${Math.floor(x / GRID_SIZE)},${Math.floor(z / GRID_SIZE)}`)
  let smallest = Infinity
  let index = 0
  let nx = 0
  let nz = 0
  if (candidates) {
    for (const segment of candidates) {
      const dx = x - segment.x
      const dz = z - segment.z
      const t = Math.max(0, Math.min(1, (dx * segment.dx + dz * segment.dz) / segment.lengthSq))
      const ox = dx - segment.dx * t
      const oz = dz - segment.dz * t
      const distanceSq = ox * ox + oz * oz
      if (distanceSq >= smallest) continue
      smallest = distanceSq
      index = segment.index
      nx = ox
      nz = oz
    }
  }
  const distance = Math.sqrt(smallest)
  contact.index = index
  contact.distance = distance
  contact.nx = distance > 0 && Number.isFinite(distance) ? nx / distance : 0
  contact.nz = distance > 0 && Number.isFinite(distance) ? nz / distance : 0
}

export function nextCircuitTurn(index: number) {
  const base = circuitSamples[index]
  for (let steps = 2; steps <= 64; steps++) {
    const ahead = circuitSamples[(index + steps) % circuitSamples.length]
    const angle = Math.atan2(base.nx * ahead.nz - base.nz * ahead.nx, base.nx * ahead.nx + base.nz * ahead.nz)
    if (Math.abs(angle) >= .25) {
      return { direction: angle > 0 ? "right" : "left", distance: Math.max(0, (steps - 3) * CIRCUIT_SPACING) }
    }
  }
  return undefined
}
