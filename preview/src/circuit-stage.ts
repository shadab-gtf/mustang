import {
  BoxGeometry, BufferGeometry, CanvasTexture, DoubleSide, Float32BufferAttribute, Group, InstancedMesh,
  Matrix4, Mesh, MeshStandardMaterial, PlaneGeometry, Shape, ShapeGeometry, SRGBColorSpace, type Texture,
} from "three"
import { BARRIER_OFFSET, circuitSamples, CIRCUIT_SPACING, fromCircuitImage, ROAD_HALF_WIDTH } from "./circuit-layout.ts"

function material(color: number, roughness = .85) {
  return new MeshStandardMaterial({ color, roughness, side: DoubleSide })
}

export function buildCircuitStage(roadTexture: Texture, textureWorldSize: number) {
  const circuit = new Group()
  circuit.name = "Reference circuit"
  const band = (
    name: string, finish: MeshStandardMaterial, left: number, right: number,
    low: number, high = low, stripe?: 0 | 1,
  ) => {
    const vertices: number[] = []
    const indices: number[] = []
    const uv: number[] = []
    for (const [index, sample] of circuitSamples.entries()) {
      const { x, z, nx, nz } = sample
      vertices.push(x + nx * left, low, z + nz * left, x + nx * right, high, z + nz * right)
      if (finish.map) uv.push((x + nx * left) / textureWorldSize, (z + nz * left) / textureWorldSize,
        (x + nx * right) / textureWorldSize, (z + nz * right) / textureWorldSize)
      if (stripe !== undefined && index % 2 !== stripe) continue
      const current = index * 2
      const next = ((index + 1) % circuitSamples.length) * 2
      indices.push(current, current + 1, next, next, current + 1, next + 1)
    }
    const geometry = new BufferGeometry()
    geometry.setAttribute("position", new Float32BufferAttribute(vertices, 3))
    if (uv.length) geometry.setAttribute("uv", new Float32BufferAttribute(uv, 2))
    geometry.setIndex(indices)
    geometry.computeVertexNormals()
    const mesh = new Mesh(geometry, finish)
    mesh.name = name
    mesh.receiveShadow = true
    circuit.add(mesh)
  }

  const asphalt = material(0x373a3e)
  asphalt.map = roadTexture
  const gravel = material(0x8f826a)
  const grass = material(0x506747)
  const white = material(0xece8dc)
  white.polygonOffset = true
  white.polygonOffsetFactor = -1
  white.polygonOffsetUnits = -2
  const red = material(0xad3834)
  const concrete = material(0x858b8e)
  const rail = material(0xdbe0e1, .57)
  const reflectors = material(0xe7af61)
  band("Asphalt", asphalt, -ROAD_HALF_WIDTH, ROAD_HALF_WIDTH, .003)
  for (const side of [-1, 1]) {
    const edge = side * ROAD_HALF_WIDTH
    const wall = side * BARRIER_OFFSET
    band("Grass verge", grass, edge, side * (ROAD_HALF_WIDTH + 2.3), .001)
    band("Gravel runoff", gravel, side * (ROAD_HALF_WIDTH + 2.3), wall, .001)
    band("White edge line", white, edge - side * .32, edge - side * .13, .006)
    band("Red kerb", red, edge, edge + side * .8, .013, .023, 0)
    band("White kerb", white, edge, edge + side * .8, .013, .023, 1)
    band("Barrier", concrete, wall, wall, 0, .88)
    band("Guardrail", rail, wall, wall, .88, 1.37)
    band("Reflective markers", reflectors, wall - side * .012, wall - side * .012, .96, 1.09, 0)
    band("Barrier coping", concrete, wall, wall + side * .45, 1.37)
    band("Barrier exterior", concrete, wall + side * .45, wall + side * .45, 0, 1.37)
  }

  const post = new Matrix4()
  const postCount = Math.ceil(circuitSamples.length / 2)
  const barrierPosts = new InstancedMesh(new BoxGeometry(.30, 1.48, .34), material(0x42474a), postCount * 2)
  for (let index = 0; index < postCount; index++) {
    const { x, z, nx, nz } = circuitSamples[index * 2]
    for (const [sideIndex, side] of [-1, 1].entries()) {
      const offset = side * (BARRIER_OFFSET + .05)
      barrierPosts.setMatrixAt(index * 2 + sideIndex, post.makeTranslation(x + nx * offset, .74, z + nz * offset))
    }
  }
  barrierPosts.name = "Guardrail posts"
  circuit.add(barrierPosts)

  const turns = [
    [990,513], [1002,574], [1126,704], [177,710], [445,411], [464,360], [421,328], [294,288],
    [274,251], [81,173], [181,49], [235,140], [365,252], [431,220], [645,324], [503,520],
  ]
  const turnSamples = turns.map(([px, py]) => {
    const point = fromCircuitImage(px, py)
    let closest = Infinity
    let selected = 0
    for (const [index, sample] of circuitSamples.entries()) {
      const sq = (sample.x - point.x) ** 2 + (sample.z - point.z) ** 2
      if (sq >= closest) continue
      closest = sq
      selected = index
    }
    return selected
  })
  const board = new PlaneGeometry(1.6, .88)
  for (const distance of [150, 100, 50]) {
    const label = document.createElement("canvas")
    label.width = 128
    label.height = 64
    const context = label.getContext("2d")
    if (!context) continue
    context.fillStyle = "#fbf8e9"
    context.fillRect(0, 0, 128, 64)
    context.font = "bold 48px sans-serif"
    context.textBaseline = "middle"
    context.textAlign = "center"
    context.fillStyle = "#191d1e"
    context.fillText(String(distance), 64, 34)
    const map = new CanvasTexture(label)
    map.colorSpace = SRGBColorSpace
    const placard = new MeshStandardMaterial({ map, side: DoubleSide, roughness: .82 })
    for (const finishIndex of turnSamples) {
      const index = (finishIndex + circuitSamples.length - distance / CIRCUIT_SPACING) % circuitSamples.length
      const { x, z, nx, nz } = circuitSamples[index]
      const marker = new Mesh(board, placard)
      marker.position.set(x + nx * 15.32, 1.77, z + nz * 15.32)
      marker.rotation.y = Math.atan2(-nz, nx)
      circuit.add(marker)
    }
  }

  const start = circuitSamples[0]
  const finishTile = new PlaneGeometry(.69, .69).rotateX(-Math.PI / 2)
  const darkTile = material(0x141516)
  darkTile.polygonOffset = true
  darkTile.polygonOffsetFactor = -1
  darkTile.polygonOffsetUnits = -2
  for (let row = 0; row < 3; row++) {
    for (let column = 0; column < 24; column++) {
      const lateral = (column - 11.5) * .69
      const forward = (row - 1) * .69
      const tile = new Mesh(finishTile, (column + row) % 2 ? darkTile : white)
      tile.rotation.y = Math.atan2(-start.nx, start.nz)
      tile.position.set(start.x + start.nx * lateral + start.nz * forward, .009,
        start.z + start.nz * lateral - start.nx * forward)
      circuit.add(tile)
    }
  }

  const pond = (outline: ReadonlyArray<readonly [number, number]>) => {
    const shape = new Shape()
    outline.forEach(([x, y], index) => {
      const point = fromCircuitImage(x, y)
      if (index === 0) shape.moveTo(point.x, -point.z)
      else shape.lineTo(point.x, -point.z)
    })
    shape.closePath()
    const water = new Mesh(new ShapeGeometry(shape).rotateX(-Math.PI / 2), material(0x287796, .26))
    water.position.y = .005
    circuit.add(water)
  }
  pond([[326,652],[333,620],[382,572],[489,595],[495,652],[407,661],[360,657]])
  pond([[920,532],[939,527],[950,564],[964,607],[993,655],[941,660],[929,605]])

  const buildings = material(0x8b8884)
  for (const [px, py, width, depth, height, rotation] of [
    [694,473,520,68,17,.09], [654,574,245,58,8,.07], [806,553,235,54,10,.14],
    [727,590,62,64,8,0], [572,398,142,21,8,.81], [922,461,154,31,7,.1],
    [154,221,254,26,6,-.37], [613,247,255,28,7,-.36], [344,497,180,22,7,-.78],
  ]) {
    const { x, z } = fromCircuitImage(px, py)
    const structure = new Mesh(new BoxGeometry(width, height, depth), buildings)
    structure.position.set(x, height / 2, z)
    structure.rotation.y = rotation
    structure.receiveShadow = true
    circuit.add(structure)
  }
  return circuit
}
