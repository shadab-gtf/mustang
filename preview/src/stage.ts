import {
  ACESFilmicToneMapping, CanvasTexture, Color, DirectionalLight, FogExp2, Group, HemisphereLight,
  InstancedMesh, LinearFilter, Matrix4, Mesh, MeshBasicMaterial, MeshStandardMaterial, PCFShadowMap, PlaneGeometry, PMREMGenerator,
  RepeatWrapping, RingGeometry, Scene, SRGBColorSpace, WebGLRenderer,
} from "three"
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js"
import { buildCircuitStage } from "./circuit-stage.ts"

const DAY = 0x374047
const NIGHT = 0x152033
const FLOOR_SIZE = 840
const FLOOR_TILES = 240
const FLOOR_SHIFT = FLOOR_SIZE / 10
const LANE_PERIOD = 8
const LANE_RADIUS = 24

function surfaceTexture() {
  const surface = document.createElement("canvas")
  surface.width = surface.height = 128
  const context = surface.getContext("2d")
  if (!context) throw new Error("Your browser couldn't create the test pad texture.")
  const pixels = context.createImageData(128, 128)
  let seed = 2049
  for (let offset = 0; offset < pixels.data.length; offset += 4) {
    seed = (Math.imul(seed, 1_664_525) + 1_013_904_223) >>> 0
    const shade = 198 + (seed >>> 25) * 0.24
    pixels.data.set([shade, shade, shade - 5, 255], offset)
  }
  context.putImageData(pixels, 0, 0)
  const texture = new CanvasTexture(surface)
  texture.colorSpace = SRGBColorSpace
  texture.wrapS = texture.wrapT = RepeatWrapping
  texture.magFilter = LinearFilter
  texture.repeat.set(FLOOR_TILES, FLOOR_TILES)
  return texture
}

function lineCircle(radius: number, width: number, opacity: number, phiSegments = 192) {
  const mesh = new Mesh(
    new RingGeometry(radius, radius + width, phiSegments),
    new MeshBasicMaterial({ color: 0xcbbd9e, transparent: true, opacity, depthWrite: false }),
  )
  mesh.rotation.x = -Math.PI / 2
  mesh.position.y = 0.003
  return mesh
}

export function buildStage(canvas: HTMLCanvasElement) {
  const renderer = new WebGLRenderer({ canvas, antialias: true })
  renderer.outputColorSpace = SRGBColorSpace
  renderer.toneMapping = ACESFilmicToneMapping
  renderer.toneMappingExposure = 0.96
  renderer.transmissionResolutionScale = 0.80
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = PCFShadowMap

  const scene = new Scene()
  scene.background = new Color(DAY)
  const fog = new FogExp2(DAY, 0.021)
  scene.fog = fog

  const pmrem = new PMREMGenerator(renderer)
  const room = new RoomEnvironment()
  const reflection = pmrem.fromScene(room, 0.06)
  scene.environment = reflection.texture
  scene.environmentIntensity = 0.93
  room.dispose()
  pmrem.dispose()

  const hemisphere = new HemisphereLight(0xe4efff, 0x675b48, 0.98)
  const sun = new DirectionalLight(0xffefd9, 2.05)
  sun.position.set(-4, 7, -5)
  sun.castShadow = true
  sun.shadow.mapSize.set(1536, 1536)
  sun.shadow.camera.left = sun.shadow.camera.bottom = -7
  sun.shadow.camera.right = sun.shadow.camera.top = 7
  sun.shadow.camera.near = 0.5
  sun.shadow.camera.far = 22
  sun.shadow.normalBias = 0.012
  sun.shadow.bias = -0.00025
  const backlight = new DirectionalLight(0xdbe5fe, 1.3)
  backlight.position.set(5, 3, 4)

  const groundTexture = surfaceTexture()
  const asphalt = new MeshStandardMaterial({ color: 0x41464a, roughness: 0.87, map: groundTexture })
  const floor = new Mesh(new PlaneGeometry(FLOOR_SIZE, FLOOR_SIZE), asphalt)
  floor.rotation.x = -Math.PI / 2
  floor.receiveShadow = true
  const graphics = new Group()
  graphics.add(lineCircle(4.60, 0.028, 0.26))
  const trackPaint = new Group()
  trackPaint.visible = false
  const largeRing = lineCircle(19.5, 0.11, 0.42)
  largeRing.position.z = -21
  trackPaint.add(largeRing)
  const laneMaterial = new MeshBasicMaterial({ color: 0xcbbd9e, transparent: true, opacity: 0.52, depthWrite: false })
  const laneGeometry = new PlaneGeometry(0.12, 3.2).rotateX(-Math.PI / 2)
  const lanes = new InstancedMesh(laneGeometry, laneMaterial, 2 * (2 * LANE_RADIUS + 1))
  const marker = new Matrix4()
  let laneIndex = 0
  for (const x of [-4.25, 4.25]) {
    for (let segment = -LANE_RADIUS; segment <= LANE_RADIUS; segment++) {
      lanes.setMatrixAt(laneIndex++, marker.makeTranslation(x, 0.004, segment * LANE_PERIOD))
    }
  }
  trackPaint.add(lanes)
  scene.add(sun, sun.target, hemisphere, backlight, floor, graphics, trackPaint)
  let circuit: Group | undefined
  let racing = false
  let night = false

  return {
    renderer, scene,
    setLighting(enabled: boolean) {
      night = enabled
      const tone = night ? NIGHT : DAY
      if (scene.background instanceof Color) scene.background.setHex(tone)
      fog.color.setHex(tone)
      scene.environmentIntensity = night ? 0.34 : 0.93
      hemisphere.intensity = night ? 0.43 : 0.98
      sun.intensity = night ? 0.56 : 2.05
      sun.color.setHex(night ? 0xb1c8ff : 0xffefd9)
      backlight.intensity = night ? 1.02 : 1.3
      asphalt.color.setHex(racing ? (night ? 0x263126 : 0x3d5137) : (night ? 0x363d50 : 0x41464a))
    },
    setDriveMode(drive: boolean, onCircuit: boolean) {
      racing = drive && onCircuit
      if (racing && !circuit) {
        circuit = buildCircuitStage(groundTexture, FLOOR_SIZE)
        scene.add(circuit)
      }
      if (circuit) circuit.visible = racing
      graphics.visible = !drive
      trackPaint.visible = drive && !racing
      fog.density = racing ? .0068 : .021
      asphalt.color.setHex(racing ? (night ? 0x263126 : 0x3d5137) : (night ? 0x363d50 : 0x41464a))
    },
    followShadow(x: number, z: number) {
      sun.position.set(x - 4, 7, z - 5)
      sun.target.position.set(x, 0, z)
      if (trackPaint.visible || racing) {
        // Reposition by whole texture and lane periods so markings stay fixed against the ground.
        floor.position.set(Math.round(x / FLOOR_SHIFT) * FLOOR_SHIFT, racing ? -.06 : 0, Math.round(z / FLOOR_SHIFT) * FLOOR_SHIFT)
        lanes.position.z = Math.round(z / LANE_PERIOD) * LANE_PERIOD
      } else {
        floor.position.set(0, 0, 0)
        lanes.position.z = 0
      }
    },
  }
}
