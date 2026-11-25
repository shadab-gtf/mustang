import {
  BufferAttribute, BufferGeometry, DynamicDrawUsage, Group, InstancedBufferAttribute, InstancedBufferGeometry,
  Mesh, MeshBasicMaterial, PlaneGeometry, ShaderMaterial, Vector3,
} from "three"
import { clamp, HALF_TRACK, REAR_AXLE_Z, type VehiclePhysics } from "./physics.ts"
import { ExhaustFlare } from "./exhaust-flare.ts"

const PUFF_CAPACITY = 100
const MARK_CAPACITY = 700
const MARK_Y = 0.007

interface Puff {
  x: number
  y: number
  z: number
  vx: number
  vy: number
  vz: number
  age: number
  life: number
  size: number
  opacity: number
}

interface Mark {
  x: number
  z: number
  connected: boolean
}

export interface ExhaustEmission {
  position: Vector3
  direction: Vector3
  rpm: number
  throttle: number
}

export class VehicleEffects {
  readonly group = new Group()
  private readonly offset = new Vector3()
  private readonly flare = new ExhaustFlare()
  private readonly lastMarks: [Mark, Mark] = [
    { x: 0, z: 0, connected: false }, { x: 0, z: 0, connected: false },
  ]
  private readonly puffs: Puff[] = Array.from({ length: PUFF_CAPACITY }, () => (
    { x: 0, y: 0, z: 0, vx: 0, vy: 0, vz: 0, age: 1, life: 1, size: 0, opacity: 0 }
  ))
  private readonly locations = new InstancedBufferAttribute(new Float32Array(PUFF_CAPACITY * 3), 3).setUsage(DynamicDrawUsage)
  private readonly visuals = new InstancedBufferAttribute(new Float32Array(PUFF_CAPACITY * 2), 2).setUsage(DynamicDrawUsage)
  private readonly marks = new BufferAttribute(new Float32Array(MARK_CAPACITY * 18), 3).setUsage(DynamicDrawUsage)
  private readonly markGeometry = new BufferGeometry()
  private readonly smokeMaterial: ShaderMaterial
  private nextPuff = 0
  private nextMark = 0
  private markCount = 0
  private nextSmoke = 0
  private nextExhaust = 0
  private nextDamageSmoke = 0
  private nextFlare = 0
  private previousThrottle = 0
  private seed = 227

  constructor() {
    const plane = new PlaneGeometry(1, 1)
    const smoke = new InstancedBufferGeometry()
    smoke.setIndex(plane.getIndex())
    smoke.setAttribute("position", plane.getAttribute("position"))
    smoke.setAttribute("uv", plane.getAttribute("uv"))
    smoke.setAttribute("puffLocation", this.locations)
    smoke.setAttribute("puffVisual", this.visuals)
    smoke.instanceCount = PUFF_CAPACITY
    this.smokeMaterial = new ShaderMaterial({
      uniforms: { brightness: { value: 0.70 } },
      vertexShader: `
        attribute vec3 puffLocation;
        attribute vec2 puffVisual;
        varying vec2 particleUV;
        varying float alpha;
        varying vec3 seed;
        void main() {
          particleUV = uv * 2.0 - 1.0;
          alpha = puffVisual.y;
          seed = puffLocation;
          vec4 center = modelViewMatrix * vec4(puffLocation, 1.0);
          center.xy += position.xy * puffVisual.x;
          gl_Position = projectionMatrix * center;
        }
      `,
      fragmentShader: `
        uniform float brightness;
        varying vec2 particleUV;
        varying float alpha;
        varying vec3 seed;
        void main() {
          float detail = sin(particleUV.x * 11.0 + seed.x * 2.0)
            * cos(particleUV.y * 10.0 + seed.z * 2.0) * 0.12;
          float shape = 1.0 - smoothstep(0.07, 0.99, length(particleUV) + detail);
          gl_FragColor = vec4(vec3(brightness * 0.96, brightness, brightness * 1.06), shape * shape * alpha);
          #include <tonemapping_fragment>
          #include <colorspace_fragment>
        }
      `,
      depthWrite: false, transparent: true,
    })
    const smokeMesh = new Mesh(smoke, this.smokeMaterial)
    smokeMesh.frustumCulled = false
    smokeMesh.renderOrder = 2
    this.markGeometry.setAttribute("position", this.marks)
    this.markGeometry.setDrawRange(0, 0)
    const markMesh = new Mesh(this.markGeometry, new MeshBasicMaterial({
      color: 0x111315, transparent: true, opacity: 0.72, depthWrite: false,
    }))
    markMesh.frustumCulled = false
    this.group.add(markMesh, smokeMesh, this.flare.group)
  }

  setNight(enabled: boolean) { this.smokeMaterial.uniforms.brightness.value = enabled ? 0.20 : 0.70 }

  reset() {
    for (const mark of this.lastMarks) mark.connected = false
    for (const puff of this.puffs) puff.age = puff.life
    this.nextMark = this.markCount = this.nextSmoke = this.nextExhaust = this.nextDamageSmoke = 0
    this.nextFlare = this.previousThrottle = 0
    this.flare.reset()
    this.markGeometry.setDrawRange(0, 0)
  }

  update(delta: number, vehicle: VehiclePhysics, enabled: boolean, reducedMotion: boolean,
    exhaust?: ExhaustEmission, damage = 0) {
    const isSkidding = enabled && vehicle.rearSlip > 0.25 && Math.abs(vehicle.forwardSpeed) > 2
    this.nextSmoke -= delta
    this.nextExhaust -= delta
    for (let side = 0; side < 2; side++) {
      const lateral = (side === 0 ? -1 : 1) * HALF_TRACK
      this.worldOffset(vehicle, lateral, REAR_AXLE_Z)
      if (isSkidding) {
        this.addMark(this.lastMarks[side], this.offset.x, this.offset.z)
        if (this.nextSmoke <= 0 && !reducedMotion) this.spawn(this.offset.x, 0.18, this.offset.z, 0.45, 1.55, 0.50)
      } else {
        this.lastMarks[side].connected = false
      }
    }
    if (this.nextSmoke <= 0) this.nextSmoke = 0.11 - vehicle.rearSlip * 0.045
    this.nextDamageSmoke -= delta
    if (damage > .36 && this.nextDamageSmoke <= 0 && !reducedMotion) {
      this.worldOffset(vehicle, -.23, -1.35)
      this.spawn(this.offset.x, .81, this.offset.z, .40 + damage * .24, 2.65, .50)
      this.nextDamageSmoke = .24 - damage * .14
    }
    this.nextFlare -= delta
    if (exhaust && !reducedMotion) this.updateExhaust(exhaust)
    this.previousThrottle = exhaust?.throttle ?? 0
    if (reducedMotion) this.flare.reset()
    this.flare.update(delta)
    for (let i = 0; i < this.puffs.length; i++) {
      const puff = this.puffs[i]
      if (puff.age < puff.life) {
        puff.age += delta
        puff.x += puff.vx * delta
        puff.z += puff.vz * delta
        puff.y += delta * puff.vy
        this.locations.setXYZ(i, puff.x, puff.y, puff.z)
      }
      const phase = Math.min(1, puff.age / puff.life)
      const density = Math.min(1, phase * 9) * (1 - phase) * puff.opacity
      this.visuals.setXY(i, puff.size * (0.8 + phase * 2.5), reducedMotion ? 0 : density)
    }
    this.locations.needsUpdate = this.visuals.needsUpdate = true
  }

  private updateExhaust({ position, direction, rpm, throttle }: ExhaustEmission) {
    const load = clamp((rpm - 850) / 6600, 0, 1)
    if (this.nextExhaust <= 0) {
      const puff = this.spawn(position.x, position.y, position.z, .095 + load * .07, .53 + load * .26, .22 + load * .27)
      const pressure = .65 + load * 2.2
      puff.vx = direction.x * pressure + puff.vx * .26
      puff.vy = direction.y * pressure + .18
      puff.vz = direction.z * pressure + puff.vz * .26
      this.nextExhaust = .17 - load * .095
    }
    const lift = this.previousThrottle > .72 && throttle < .18
    if (this.nextFlare <= 0 && ((rpm > 4550 && lift) || (rpm > 6900 && throttle > .88))) {
      this.flare.burst(position, direction, () => this.random())
      this.nextFlare = .48
    }
  }

  private random() {
    this.seed = (Math.imul(this.seed, 1_664_525) + 1_013_904_223) >>> 0
    return this.seed / 4_294_967_295
  }

  private worldOffset(vehicle: VehiclePhysics, x: number, z: number) {
    const sine = Math.sin(vehicle.yaw)
    const cosine = Math.cos(vehicle.yaw)
    this.offset.set(vehicle.x + x * cosine + z * sine, 0, vehicle.z - x * sine + z * cosine)
  }

  private spawn(x: number, y: number, z: number, size: number, life: number, opacity: number) {
    const puff = this.puffs[this.nextPuff]
    this.nextPuff = (this.nextPuff + 1) % this.puffs.length
    const spread = this.random()
    puff.x = x
    puff.y = y
    puff.z = z
    puff.vx = (spread - 0.50) * 1.35
    puff.vy = .46
    puff.vz = (0.64 - spread) * 0.9
    puff.age = 0
    puff.life = life * (0.83 + spread * 0.30)
    puff.size = size * (0.85 + spread * 0.40)
    puff.opacity = opacity
    return puff
  }

  private addMark(mark: Mark, x: number, z: number) {
    if (mark.connected) {
      const dx = x - mark.x
      const dz = z - mark.z
      const length = Math.hypot(dx, dz)
      if (length < 0.19) return
      if (length < 3) {
        const ox = -dz / length * 0.097
        const oz = dx / length * 0.097
        const vertices = this.nextMark * 6
        this.marks.setXYZ(vertices, mark.x - ox, MARK_Y, mark.z - oz)
        this.marks.setXYZ(vertices + 1, mark.x + ox, MARK_Y, mark.z + oz)
        this.marks.setXYZ(vertices + 2, x + ox, MARK_Y, z + oz)
        this.marks.setXYZ(vertices + 3, mark.x - ox, MARK_Y, mark.z - oz)
        this.marks.setXYZ(vertices + 4, x + ox, MARK_Y, z + oz)
        this.marks.setXYZ(vertices + 5, x - ox, MARK_Y, z - oz)
        this.nextMark = (this.nextMark + 1) % MARK_CAPACITY
        this.markCount = Math.min(MARK_CAPACITY, this.markCount + 1)
        this.markGeometry.setDrawRange(0, this.markCount * 6)
        this.marks.needsUpdate = true
      }
    }
    mark.x = x
    mark.z = z
    mark.connected = true
  }
}
