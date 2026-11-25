import {
  Group, MathUtils, Mesh, MeshPhysicalMaterial, MeshStandardMaterial, Object3D, Quaternion, SpotLight, Vector3,
} from "three"
import { clamp, HALF_TRACK, REAR_AXLE_Z, WHEELBASE, type VehiclePhysics } from "./physics.ts"
import { Shock } from "./shock.ts"
import { Underglow, type Neon } from "./underglow.ts"
import type { StripeLayout } from "./body-stripes.ts"
import type { CircuitRun } from "./circuit-run.ts"

export type Side = "L" | "R"
export type Indicator = "off" | "left" | "right" | "hazards"
export type Panel = "doorL" | "doorR" | "hood" | "trunk"
export type Headlights = "off" | "low" | "high"

const AXIS_X = new Vector3(1, 0, 0)
const AXIS_Y = new Vector3(0, 1, 0)
const AXIS_Z = new Vector3(0, 0, 1)
const CORNERS = ["FL", "FR", "RL", "RR"] as const
const PANEL_NODES = {
  doorL: { name: "Door_L", axis: AXIS_Y, angle: -Math.PI * 62 / 180 },
  doorR: { name: "Door_R", axis: AXIS_Y, angle: Math.PI * 62 / 180 },
  hood: { name: "Hood", axis: AXIS_X, angle: 0.92 },
  trunk: { name: "Trunk", axis: AXIS_X, angle: -0.99 },
} as const
const DOOR_TRAVEL_SECONDS = 0.72

function settle(value: number, target: number, weight: number) {
  const next = MathUtils.lerp(value, target, weight)
  return Math.abs(next - target) < 0.002 ? target : next
}

const LAMPS = [
  "HeadlightEmission", "HighBeamEmission", "FrontIndicator_L", "FrontIndicator_R",
  "RearIndicator_L", "RearIndicator_R", "TailEmission", "BrakeEmission",
  "ReverseEmission", "DashEmission",
] as const
type Lamp = typeof LAMPS[number]

function findNode(root: Object3D, name: string) {
  const node = root.getObjectByName(name)
  if (!node) throw new Error(`The model is missing its ${name} rig node.`)
  return node
}

export class VehicleRig {
  readonly group = new Group()
  private readonly chassis: Object3D
  private readonly chassisRest: Quaternion
  private readonly chassisHeight: number
  private readonly underglow: Underglow
  private readonly shocks: Shock[]
  private readonly panels
  private readonly windows
  private readonly wheelCorners
  private readonly steeringWheel
  private readonly engine
  private readonly exhaustOutlet
  private readonly exhaustAim
  private readonly headlightsBeams: SpotLight[]
  private readonly lamps = new Map<Lamp, Set<MeshStandardMaterial>>()
  private readonly workRotation = new Quaternion()
  private readonly rollRotation = new Quaternion()
  private readonly tiltChassis: boolean
  private headlights: Headlights = "off"
  private indicator: Indicator = "off"
  private brakeOverride: boolean | undefined
  private indicatorTime = 0
  private locked = false
  private enginePhase = 0

  constructor(model: Object3D) {
    this.group.add(model)
    const root = findNode(model, "Vehicle")
    this.chassis = findNode(root, "Chassis")
    this.chassisRest = this.chassis.quaternion.clone()
    this.chassisHeight = this.chassis.position.y
    this.panels = {
      doorL: this.makePanel(root, "doorL"),
      doorR: this.makePanel(root, "doorR"),
      hood: this.makePanel(root, "hood"),
      trunk: this.makePanel(root, "trunk"),
    }
    this.windows = { L: this.makeWindow(root, "L"), R: this.makeWindow(root, "R") }
    this.wheelCorners = CORNERS.map((corner) => {
      const suspension = findNode(root, `Suspension_${corner}`)
      const steer = findNode(suspension, `Steer_${corner}`)
      const wheel = findNode(steer, `Wheel_${corner}`)
      return { suspension, height: suspension.position.y, steer, steerRest: steer.quaternion.clone(), wheel, wheelRest: wheel.quaternion.clone() }
    })
    this.tiltChassis = this.wheelCorners.every(({ suspension }) => suspension.parent !== this.chassis)
    this.shocks = this.tiltChassis ? this.wheelCorners.map(({ suspension }) => new Shock(this.group, suspension)) : []
    const steering = root.getObjectByName("SteeringWheel")
    this.steeringWheel = steering && { node: steering, rest: steering.quaternion.clone() }
    const engine = root.getObjectByName("Engine")
    this.engine = engine && { node: engine, rest: engine.quaternion.clone() }
    this.exhaustOutlet = root.getObjectByName("Exhaust_Outlet")
    this.exhaustAim = root.getObjectByName("Exhaust_Outlet_Aim")
    const adjusted = new Set<MeshStandardMaterial>()
    model.traverse((node) => {
      if (!(node instanceof Mesh)) return
      const materials: unknown[] = Array.isArray(node.material) ? node.material : [node.material]
      const glass = materials.some((material) => material instanceof MeshStandardMaterial &&
        /glass/i.test(material.name) && (material.transparent || material.opacity < 1 ||
          (material instanceof MeshPhysicalMaterial && material.transmission > 0)))
      node.castShadow = !glass
      node.receiveShadow = !glass
      for (const material of materials) {
        if (!(material instanceof MeshStandardMaterial) || adjusted.has(material)) continue
        adjusted.add(material)
        if (material.name === "Jet black lacquer" && material.normalMap) material.normalScale.clampLength(0, 0.31)
        if (material instanceof MeshPhysicalMaterial && material.name === "Clear automotive glass") {
          material.roughness = Math.min(material.roughness, 0.035)
          material.ior = 1.22
        }
        const lamp = LAMPS.find((name) => material.name === name)
        if (!lamp) continue
        const group = this.lamps.get(lamp) ?? new Set<MeshStandardMaterial>()
        group.add(material)
        this.lamps.set(lamp, group)
        material.emissiveIntensity = 0
      }
    })
    this.headlightsBeams = [-0.722, 0.722].map((x) => {
      const lamp = new SpotLight(0xffe8c5, 0, 55, 0.32, 0.55, 1.9)
      lamp.position.set(x, 0.53, -2.00)
      lamp.target.position.set(x * 1.2, 0.1, -20)
      this.chassis.add(lamp, lamp.target)
      return lamp
    })
    this.underglow = new Underglow(this.chassis, this.group, this.panels.hood?.node, this.panels.trunk?.node)
  }

  hasPanel(panel: Panel) { return this.panels[panel] !== undefined }

  get isArticulating() {
    return Object.values(this.panels).some((panel) => panel && panel.value !== panel.target) ||
      Object.values(this.windows).some((window) => window && window.value !== window.target)
  }

  setPanel(panel: Panel, open: boolean) {
    const part = this.panels[panel]
    if (!part) return false
    if (open && this.locked && (panel === "doorL" || panel === "doorR")) return false
    part.target = Number(open)
    return true
  }

  hasWindow(side: Side) { return this.windows[side] !== undefined }

  setWindow(side: Side, openness: number) {
    const window = this.windows[side]
    if (window) window.target = clamp(openness, 0, 1)
  }

  setDoorLock(locked: boolean) {
    this.locked = locked
    if (locked) {
      this.setPanel("doorL", false)
      this.setPanel("doorR", false)
    }
  }

  setHeadlights(mode: Headlights) { this.headlights = mode }
  setNeon(mode: Neon, layout: StripeLayout) { this.underglow.set(mode, layout) }

  sampleExhaust(position: Vector3, direction: Vector3) {
    if (!this.exhaustOutlet || !this.exhaustAim) return false
    this.exhaustOutlet.getWorldPosition(position)
    this.exhaustAim.getWorldPosition(direction).sub(position).normalize()
    return true
  }

  setIndicator(indicator: Indicator) {
    if (this.indicator !== indicator) this.indicatorTime = 0
    this.indicator = indicator
  }

  setBrakeLights(enabled?: boolean) { this.brakeOverride = enabled }

  hasBrakeLights() { return this.lamps.has("BrakeEmission") || this.lamps.has("TailEmission") }

  hasIndicator(direction: Exclude<Indicator, "off">) {
    const left = this.lamps.has("FrontIndicator_L") || this.lamps.has("RearIndicator_L")
    const right = this.lamps.has("FrontIndicator_R") || this.lamps.has("RearIndicator_R")
    return direction === "hazards" ? left && right : direction === "left" ? left : right
  }

  update(delta: number, vehicle: VehiclePhysics, brake: number, reducedMotion: boolean, running: boolean,
    crash?: CircuitRun) {
    const overturn = crash?.rollAngle ?? 0
    const height = .625 * (Math.abs(Math.cos(overturn)) - Math.cos(overturn))
      + .92 * Math.abs(Math.sin(overturn)) + (crash?.rollBounce ?? 0)
    this.group.position.set(vehicle.x, height, vehicle.z)
    this.group.rotation.set(0, vehicle.yaw, overturn, "YXZ")
    this.underglow.setPower(!crash || crash.phase === "driving")
    const smooth = reducedMotion ? 1 : 1 - Math.exp(-delta * 6.5)
    if (this.tiltChassis) {
      const { suspension } = vehicle
      const squat = (suspension[0] + suspension[1] + suspension[2] + suspension[3]) * .25
      const rearPivotRise = Math.sin(vehicle.launchPitch) * REAR_AXLE_Z
      this.chassis.position.y = this.chassisHeight - squat + rearPivotRise
      this.workRotation.setFromAxisAngle(AXIS_X, vehicle.pitch * 1.16 + vehicle.launchPitch)
      this.rollRotation.setFromAxisAngle(AXIS_Z, vehicle.roll * 1.18)
      this.chassis.quaternion.copy(this.chassisRest).multiply(this.workRotation).multiply(this.rollRotation)
    }
    for (const [name, panel] of Object.entries(this.panels)) {
      if (!panel) continue
      if (panel.isDoor) {
        const step = reducedMotion ? 1 : delta / DOOR_TRAVEL_SECONDS
        panel.value += clamp(panel.target - panel.value, -step, step)
      } else {
        panel.value = settle(panel.value, panel.target, smooth)
      }
      const fraction = panel.isDoor ? MathUtils.smoothstep(panel.value, 0, 1) : panel.value
      const impactDamage = name === "hood" ? crash?.frontDamage : name === "trunk" ? crash?.rearDamage : 0
      this.rotate(panel.node, panel.rest, panel.axis, Math.max(fraction, (impactDamage ?? 0) * .62) * panel.angle)
    }
    for (const window of Object.values(this.windows)) {
      if (!window) continue
      window.value = settle(window.value, window.target, smooth)
      window.node.position.copy(window.rest)
      window.node.position.y -= window.travel * window.value
      window.node.position.x += window.drift * window.value
    }
    const steeringTangent = Math.tan(vehicle.steerAngle)
    this.wheelCorners.forEach(({ suspension, height, steer, steerRest, wheel, wheelRest }, corner) => {
      suspension.position.y = height + (corner < 2 ? vehicle.frontLift : 0)
      this.shocks[corner]?.update(this.chassis)
      const side = corner === 0 ? 1 : -1
      const wheelSteer = Math.atan2(steeringTangent, 1 - steeringTangent * side * HALF_TRACK / WHEELBASE)
      this.rotate(steer, steerRest, AXIS_Y, corner < 2 ? wheelSteer : 0)
      this.rotate(wheel, wheelRest, AXIS_X, vehicle.wheelAngle[corner])
    })
    if (this.steeringWheel) {
      this.rotate(this.steeringWheel.node, this.steeringWheel.rest, AXIS_Z, vehicle.steerAngle * 14)
    }
    if (this.engine) {
      this.enginePhase = (this.enginePhase + delta * Math.PI * vehicle.rpm / 75) % (2 * Math.PI)
      const vibration = running && !reducedMotion ? Math.sin(this.enginePhase) * 0.0016 : 0
      this.rotate(this.engine.node, this.engine.rest, AXIS_Z, vibration)
    }
    this.updateLights(delta, this.brakeOverride ?? brake > 0.12, vehicle.gear === -1)
  }

  private updateLights(delta: number, brake: boolean, reverse: boolean) {
    this.indicatorTime = (this.indicatorTime + delta) % 0.82
    const blink = this.indicatorTime < 0.43
    const left = blink && (this.indicator === "left" || this.indicator === "hazards")
    const right = blink && (this.indicator === "right" || this.indicator === "hazards")
    const beamsOn = this.headlights !== "off"
    const high = this.headlights === "high"
    const sharedBrakeLamp = brake && !this.lamps.has("BrakeEmission")
    this.setLamp("HeadlightEmission", beamsOn ? 1.7 : 0)
    this.setLamp("HighBeamEmission", high ? 3.0 : 0)
    this.setLamp("TailEmission", sharedBrakeLamp ? 2.6 : beamsOn ? 0.60 : 0)
    this.setLamp("BrakeEmission", brake ? 2.6 : 0)
    this.setLamp("ReverseEmission", reverse ? 1.5 : 0)
    this.setLamp("DashEmission", beamsOn ? 1.05 : 0)
    this.setLamp("FrontIndicator_L", left ? 2.0 : 0)
    this.setLamp("RearIndicator_L", left ? 2.0 : 0)
    this.setLamp("FrontIndicator_R", right ? 2.0 : 0)
    this.setLamp("RearIndicator_R", right ? 2.0 : 0)
    for (const beam of this.headlightsBeams) {
      beam.intensity = high ? 570 : beamsOn ? 205 : 0
      beam.target.position.y = high ? 0.65 : -0.70
    }
  }

  private setLamp(lamp: Lamp, strength: number) {
    this.lamps.get(lamp)?.forEach((material) => {
      const nominal = Math.max(material.emissive.r, material.emissive.g, material.emissive.b, 0.02)
      material.emissiveIntensity = strength / nominal
    })
  }

  private makePanel(root: Object3D, panel: Panel) {
    const { name, axis, angle } = PANEL_NODES[panel]
    const node = root.getObjectByName(name)
    if (!node) return undefined
    const isDoor = panel === "doorL" || panel === "doorR"
    const travel: unknown = node.userData.travelDegrees
    const openAngle = isDoor && typeof travel === "number" && Number.isFinite(travel)
      ? Math.sign(angle) * MathUtils.degToRad(travel) : angle
    return { node, axis, angle: openAngle, isDoor, rest: node.quaternion.clone(), value: 0, target: 0 }
  }

  private makeWindow(root: Object3D, side: Side) {
    const node = root.getObjectByName(`Window_${side}`)
    if (!node) return undefined
    const { travelMeters, outwardMeters }: { travelMeters?: unknown; outwardMeters?: unknown } = node.userData
    const travel = typeof travelMeters === "number" && Number.isFinite(travelMeters) ? travelMeters : 0.365
    const outward = typeof outwardMeters === "number" && Number.isFinite(outwardMeters) ? outwardMeters : 0.03
    return { node, rest: node.position.clone(), travel, drift: side === "L" ? -outward : outward, value: 0, target: 0 }
  }

  private rotate(node: Object3D, rest: Quaternion, axis: Vector3, angle: number) {
    node.quaternion.copy(rest).multiply(this.workRotation.setFromAxisAngle(axis, angle))
  }
}
