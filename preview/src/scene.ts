import { MathUtils, PerspectiveCamera, Vector3 } from "three"
import { OrbitControls } from "three/addons/controls/OrbitControls.js"
import { MeshoptDecoder } from "three/addons/libs/meshopt_decoder.module.js"
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js"
import { VehicleAudio } from "./audio.ts"
import { VehicleEffects, type ExhaustEmission } from "./effects.ts"
import { clamp, FIXED_STEP, VehiclePhysics, type DriveInput, type Gear, type Transmission } from "./physics.ts"
import { VehicleRig, type Headlights, type Indicator, type Panel, type Side } from "./rig.ts"
import { buildStage } from "./stage.ts"
import type { Neon } from "./underglow.ts"
import type { StripeLayout } from "./body-stripes.ts"
import { CircuitRun, type Course, type CrashReason, type RunPhase } from "./circuit-run.ts"
import { BARRIER_OFFSET, nearestRoad, type RoadContact } from "./circuit-layout.ts"

export { createCircuitMap } from "./circuit-map.ts"

export type CameraView = "front" | "side" | "rear" | "cabin" | "engine" | "trunk"
export interface Telemetry {
  speed: number
  rpm: number
  slipDegrees: number
  gear: Gear
  course: Course
  phase: RunPhase
  reason: CrashReason | undefined
  damage: number
  x: number
  z: number
  yaw: number
}

const VIEWS: Record<CameraView, readonly [Vector3, Vector3]> = {
  front: [new Vector3(-3.60, 2.09, -5.20), new Vector3(0.15, 0.49, -0.29)],
  side: [new Vector3(-7.65, 1.92, -0.65), new Vector3(0, 0.62, 0)],
  rear: [new Vector3(-4.20, 2.37, 5.86), new Vector3(0, 0.64, 0)],
  cabin: [new Vector3(-1.62, 1.20, .61), new Vector3(-.09,.74,-.23)],
  engine: [new Vector3(-1.72, 2.28, -2.96), new Vector3(0,.59,-1.38)],
  trunk: [new Vector3(-1.49, 1.98, 3.19), new Vector3(0,.64,1.93)],
}
const CHASE_OFFSET = new Vector3(-0.7, 3.0, 7.0)
const CHASE_LOOK_AHEAD = 1.15
const UP = new Vector3(0, 1, 0)
const REV_DURATION = 2.05

export async function createPreview(
  canvas: HTMLCanvasElement,
  modelUrl: string,
  telemetry: (data: Telemetry) => void,
) {
  const asset = await new GLTFLoader().setMeshoptDecoder(MeshoptDecoder).loadAsync(modelUrl)
  const rig = new VehicleRig(asset.scene)
  return new DriveScene(canvas, rig, telemetry)
}

export class DriveScene {
  readonly physics = new VehiclePhysics()
  private readonly stage
  private readonly camera
  private readonly orbit
  private readonly effects = new VehicleEffects()
  private readonly exhaust: ExhaustEmission = {
    position: new Vector3(), direction: new Vector3(), rpm: 850, throttle: 0,
  }
  private readonly rig
  private readonly telemetry
  private readonly controls: DriveInput = { throttle: 0, brake: 0, steer: 0, handbrake: 0 }
  private readonly chaseTarget = new Vector3()
  private readonly chaseRoad: RoadContact = { index: 0, distance: 0, nx: 0, nz: 0 }
  private readonly reducedMotion = matchMedia("(prefers-reduced-motion: reduce)")
  private readonly stats: Telemetry = {
    speed: 0, rpm: 850, slipDegrees: 0, gear: 1,
    course: "circuit", phase: "driving", reason: undefined, damage: 0, x: 0, z: 0, yaw: 0,
  }
  private readonly circuitRun = new CircuitRun()
  private course: Course = "circuit"
  private callbackAt = 0
  private time = 0
  private accumulator = 0
  private inspectorCamera: CameraView = "front"
  private until = 0
  private dirty = true
  private blinking = false
  private driving = false
  private chaseYaw = 0
  private speedFov = 0
  private revRemaining = 0
  private audio?: VehicleAudio
  private soundEnabled = false

  constructor(canvas: HTMLCanvasElement, rig: VehicleRig, telemetry: (data: Telemetry) => void) {
    this.rig = rig
    this.telemetry = telemetry
    this.stage = buildStage(canvas)
    this.camera = new PerspectiveCamera(37, 1, 0.04, 410)
    this.stage.scene.add(this.rig.group, this.effects.group)
    this.orbit = new OrbitControls(this.camera, canvas)
    this.orbit.enablePan = false
    this.orbit.enableDamping = true
    this.orbit.dampingFactor = 0.10
    this.orbit.minDistance = 2.4
    this.orbit.maxDistance = 13
    this.orbit.minPolarAngle = 0.27
    this.orbit.maxPolarAngle = Math.PI * 0.45
    this.orbit.addEventListener("change", () => this.wake(0.19))

    const viewport = canvas.parentElement
    if (!viewport) throw new Error("The preview canvas has no viewport.")
    new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect
      if (!width || !height) return
      this.stage.renderer.setPixelRatio(Math.min(devicePixelRatio, 1.6))
      this.stage.renderer.setSize(width, height, false)
      this.camera.aspect = width / height
      this.setCameraFov()
      this.wake()
    }).observe(viewport)
    this.setView("front")
    this.reducedMotion.addEventListener("change", () => {
      this.setCameraFov()
      this.wake(.9)
    })
    this.stage.renderer.setAnimationLoop((now) => this.frame(now))
  }

  accelerate(value: number) { this.controls.throttle = clamp(value, 0, 1) }
  brake(value: number) { this.controls.brake = clamp(value, 0, 1) }
  steer(value: number) { this.controls.steer = clamp(value, -1, 1) }
  handbrake(value: number) { this.controls.handbrake = clamp(value, 0, 1) }
  shiftGear(gear: Transmission) {
    if (this.onCircuit && this.circuitRun.phase !== "driving") return false
    if (gear === -1 && this.physics.forwardSpeed > 0.8) return false
    if ((gear === "auto" || gear > 0) && this.physics.forwardSpeed < -0.8) return false
    this.physics.shiftGear(gear)
    this.wake()
    return true
  }

  setDriftMode(enabled: boolean) { this.physics.driftMode = enabled }
  setDragLaunch(enabled: boolean) { this.physics.dragLaunch = enabled }

  setNeon(mode: Neon, layout: StripeLayout) {
    this.rig.setNeon(mode, layout)
    this.wake()
  }

  revEngine() {
    if (this.driving) return
    this.revRemaining = REV_DURATION
    this.wake(REV_DURATION + 1)
  }

  setDriveMode(enabled: boolean) {
    this.driving = enabled
    this.stage.setDriveMode(enabled, this.onCircuit)
    this.orbit.enabled = !enabled
    this.reset()
  }

  setCourse(course: Course) {
    if (course === this.course) return
    this.course = course
    this.stage.setDriveMode(this.driving, this.onCircuit)
    this.reset()
  }

  private get onCircuit() { return this.driving && this.course === "circuit" }

  setDoor(side: Side, open: boolean) { return this.setPanel(side === "L" ? "doorL" : "doorR", open) }
  hasPanel(panel: Panel) { return this.rig.hasPanel(panel) }
  hasWindow(side: Side) { return this.rig.hasWindow(side) }
  setWindow(side: Side, openness: number) {
    this.rig.setWindow(side, openness)
    this.wake(1)
  }
  setPanel(panel: Panel, open: boolean) {
    this.wake(1)
    return this.rig.setPanel(panel, open)
  }
  setDoorLock(enabled: boolean) {
    this.rig.setDoorLock(enabled)
    this.wake(1)
  }
  toggleHeadlights(enabled: boolean) { this.setHeadlights(enabled ? "low" : "off") }
  toggleHighBeam(enabled: boolean) { this.setHeadlights(enabled ? "high" : "low") }
  setHeadlights(mode: Headlights) {
    this.rig.setHeadlights(mode)
    this.wake()
  }
  setIndicator(direction: Indicator) {
    this.rig.setIndicator(direction)
    this.blinking = direction !== "off"
    this.wake()
  }
  setBrakeLights(enabled?: boolean) {
    this.rig.setBrakeLights(enabled)
    this.wake()
  }
  hasBrakeLights() { return this.rig.hasBrakeLights() }
  hasIndicator(direction: Exclude<Indicator, "off">) { return this.rig.hasIndicator(direction) }

  setNight(enabled: boolean) {
    this.stage.setLighting(enabled)
    this.effects.setNight(enabled)
    this.wake()
  }

  async setSound(enabled: boolean) {
    if (!this.audio && enabled) this.audio = new VehicleAudio()
    await this.audio?.setEnabled(enabled)
    this.soundEnabled = enabled
    this.wake()
  }

  setView(view: CameraView) {
    this.inspectorCamera = view
    if (this.driving) return
    this.orbit.enabled = view === "front" || view === "rear" || view === "side"
    const [position, target] = VIEWS[view]
    this.camera.position.copy(position)
    this.orbit.target.copy(target)
    this.camera.lookAt(target)
    if (this.orbit.enabled) this.orbit.update()
    this.setCameraFov()
    this.wake()
  }

  reset() {
    this.revRemaining = 0
    this.accumulator = 0
    this.speedFov = 0
    this.physics.reset()
    this.circuitRun.reset(this.physics, this.onCircuit)
    this.effects.reset()
    this.accelerate(0)
    this.brake(0)
    this.steer(0)
    this.handbrake(0)
    if (this.driving) {
      this.inspectorCamera = "front"
      this.chaseYaw = this.physics.yaw
      this.updateChase(0)
      this.setCameraFov()
    } else {
      this.setView(this.inspectorCamera)
    }
    this.wake()
  }

  private setCameraFov() {
    const base = this.driving ? 43 + (this.reducedMotion.matches ? 0 : this.speedFov)
      : this.inspectorCamera === "cabin" ? 59 : 37
    this.camera.fov = base + clamp((1.35 - this.camera.aspect) * 22, 0, 15)
    this.camera.updateProjectionMatrix()
  }

  private updateChase(delta: number) {
    const { yaw, x, z } = this.physics
    const headingError = yaw - this.chaseYaw
    const turn = Math.atan2(Math.sin(headingError), Math.cos(headingError))
    this.chaseYaw = this.reducedMotion.matches ? yaw : this.chaseYaw + turn * (1 - Math.exp(-delta * 5.5))

    // Move inside the guardrail as the camera lowers for the overturned car.
    const roll = this.onCircuit ? this.circuitRun.rollAngle : 0
    const crashView = MathUtils.smoothstep(Math.abs(roll), .34, 1.23)
    let viewYaw = this.chaseYaw
    if (crashView > 0) {
      nearestRoad(x, z, this.chaseRoad)
      const insideYaw = Math.atan2(-this.chaseRoad.nx, -this.chaseRoad.nz)
      const angle = insideYaw - viewYaw
      viewYaw += Math.atan2(Math.sin(angle), Math.cos(angle)) * crashView
    }
    this.camera.position.copy(CHASE_OFFSET).applyAxisAngle(UP, viewYaw)
    this.camera.position.y = MathUtils.lerp(CHASE_OFFSET.y, .61, crashView)
    this.camera.position.x += x
    this.camera.position.z += z
    if (crashView > 0) {
      const camera = this.camera.position
      nearestRoad(camera.x, camera.z, this.chaseRoad)
      const { distance, nx, nz } = this.chaseRoad
      if (distance > BARRIER_OFFSET - .65 && Number.isFinite(distance)) {
        camera.x -= nx * (distance - BARRIER_OFFSET + .65)
        camera.z -= nz * (distance - BARRIER_OFFSET + .65)
      }
    }
    this.chaseTarget.set(x - Math.sin(viewYaw) * CHASE_LOOK_AHEAD, MathUtils.lerp(.83, .64, crashView),
      z - Math.cos(viewYaw) * CHASE_LOOK_AHEAD)
    this.camera.lookAt(this.chaseTarget)
    const speed = Math.hypot(this.physics.forwardSpeed, this.physics.lateralSpeed)
    const targetFov = 13 * MathUtils.smoothstep(speed, 6, 83)
    const fov = MathUtils.damp(this.speedFov, targetFov, 5, delta)
    if (Math.abs(fov - this.speedFov) >= .004) {
      this.speedFov = fov
      this.setCameraFov()
    }
    this.stage.followShadow(x, z)
  }

  private wake(seconds = 0.17) {
    this.dirty = true
    if (!this.reducedMotion.matches) this.until = Math.max(this.until, performance.now() + seconds * 1000)
  }

  private frame(now: number) {
    const frameTime = this.time ? (now - this.time) / 1000 : 0
    this.time = now
    const delta = Math.min(frameTime, 0.05)
    if (this.driving) {
      // Catch up during slow rendering without simulating an entire suspended tab interval.
      const driveTime = Math.min(frameTime, .25)
      this.accumulator += driveTime
      while (this.accumulator >= FIXED_STEP) {
        if (this.onCircuit) this.circuitRun.step(this.physics, FIXED_STEP, this.controls)
        else this.physics.step(FIXED_STEP, this.controls)
        this.accumulator -= FIXED_STEP
      }
      this.updateChase(driveTime)
    } else if (this.orbit.enabled) {
      this.orbit.enableDamping = !this.reducedMotion.matches
      this.orbit.update()
    }
    const revving = this.revRemaining > 0
    if (revving) this.revRemaining = Math.max(0, this.revRemaining - delta)
    if (revving && this.revRemaining === 0) this.wake(.9)
    const elapsed = REV_DURATION - this.revRemaining
    const rev = revving ? clamp(Math.min(elapsed / .82, (REV_DURATION - elapsed) / .90), 0, 1) : 0
    this.exhaust.rpm = this.driving ? this.physics.rpm : 850 + rev * 6540
    const activeDrive = this.driving && (!this.onCircuit || this.circuitRun.phase === "driving")
    this.exhaust.throttle = activeDrive ? this.controls.throttle : Number(revving && elapsed < 1.15)
    if (this.driving || revving || this.blinking || this.dirty || this.rig.isArticulating || this.until >= now) {
      this.dirty = false
      const crash = this.onCircuit ? this.circuitRun : undefined
      this.rig.update(delta, this.physics, this.controls.brake, this.reducedMotion.matches, activeDrive, crash)
      const emitting = (activeDrive || revving) && this.rig.sampleExhaust(this.exhaust.position, this.exhaust.direction)
      this.effects.update(delta, this.physics, activeDrive, this.reducedMotion.matches,
        emitting ? this.exhaust : undefined, crash?.damage)
      if (!this.driving) this.stage.followShadow(0, 0)
      this.stage.renderer.render(this.stage.scene, this.camera)
    }
    if (now >= this.callbackAt) {
      this.callbackAt = now + 90
      this.stats.speed = Math.hypot(this.physics.forwardSpeed, this.physics.lateralSpeed) * 3.6
      this.stats.rpm = this.physics.rpm
      this.stats.slipDegrees = MathUtils.radToDeg(this.physics.slipAngle)
      this.stats.gear = this.physics.gear
      this.stats.course = this.course
      this.stats.phase = this.circuitRun.phase
      this.stats.reason = this.circuitRun.reason
      this.stats.damage = this.circuitRun.damage
      this.stats.x = this.physics.x
      this.stats.z = this.physics.z
      this.stats.yaw = this.physics.yaw
      this.telemetry(this.stats)
      if (this.soundEnabled) this.audio?.update(this.exhaust.rpm, this.exhaust.throttle, this.physics.rearSlip)
    }
  }
}
