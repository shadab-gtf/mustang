import { BARRIER_OFFSET, circuitSpawn, nearestRoad, ROAD_HALF_WIDTH, type RoadContact } from "./circuit-layout.ts"
import { clamp, type DriveInput, type VehiclePhysics } from "./physics.ts"

export type Course = "circuit" | "pad"
export type RunPhase = "driving" | "rolling" | "finished"
export type CrashReason = "Rollover" | "Car too damaged to continue"

const HALF_BODY_LENGTH = 2.31
const HALF_BODY_WIDTH = .93

export class CircuitRun {
  phase: RunPhase = "driving"
  reason: CrashReason | undefined
  frontDamage = 0
  rearDamage = 0
  rollAngle = 0
  rollBounce = 0
  private rollDirection = 1
  private rollElapsed = 0
  private rollRate = 0
  private upwardSpeed = 0
  private readonly road: RoadContact = { index: 0, distance: 0, nx: 0, nz: 0 }

  get damage() { return Math.min(1, this.frontDamage + this.rearDamage) }

  reset(vehicle: VehiclePhysics, onCircuit: boolean) {
    this.phase = "driving"
    this.reason = undefined
    this.frontDamage = this.rearDamage = this.rollAngle = this.rollBounce = this.rollElapsed = this.rollRate = 0
    this.upwardSpeed = 0
    if (onCircuit) Object.assign(vehicle, circuitSpawn)
  }

  step(vehicle: VehiclePhysics, dt: number, input: DriveInput) {
    if (this.phase === "finished") return
    if (this.phase === "rolling") {
      this.advanceRollover(vehicle, dt)
      return
    }
    nearestRoad(vehicle.x, vehicle.z, this.road)
    const surfaceGrip = this.road.distance >= ROAD_HALF_WIDTH ? .55 : 1
    const controls = this.damage > 0 ? { ...input, throttle: input.throttle * (1 - this.damage * .62) } : input
    vehicle.step(dt, controls, surfaceGrip)
    this.hitBarrier(vehicle)
  }

  private hitBarrier(vehicle: VehiclePhysics) {
    nearestRoad(vehicle.x, vehicle.z, this.road)
    const { distance, nx, nz } = this.road
    if (distance < BARRIER_OFFSET - HALF_BODY_LENGTH - HALF_BODY_WIDTH || !Number.isFinite(distance)) return
    const sine = Math.sin(vehicle.yaw)
    const cosine = Math.cos(vehicle.yaw)
    const front = -nx * sine - nz * cosine
    const side = nx * cosine - nz * sine
    const reach = Math.abs(front) * HALF_BODY_LENGTH + Math.abs(side) * HALF_BODY_WIDTH
    const penetration = distance + reach - BARRIER_OFFSET
    if (penetration <= 0) return
    vehicle.x -= nx * (penetration + .01)
    vehicle.z -= nz * (penetration + .01)
    const impact = vehicle.forwardSpeed * front + vehicle.lateralSpeed * side
    if (impact <= 0) return

    vehicle.forwardSpeed = (vehicle.forwardSpeed - impact * front * 1.16) * .94
    vehicle.lateralSpeed = (vehicle.lateralSpeed - impact * side * 1.16) * .94
    vehicle.yawRate += clamp(impact * front * side * .06, -1.3, 1.3)
    if (this.phase !== "driving" || impact < 3.4) return
    const damage = clamp((impact - 3.4) ** 2 / 540, .015, 1)
    if (front >= 0) this.frontDamage = Math.min(1, this.frontDamage + damage)
    else this.rearDamage = Math.min(1, this.rearDamage + damage)
    if (Math.abs(side) > .47 && impact >= 14) {
      this.phase = "rolling"
      this.reason = "Rollover"
      this.rollDirection = side >= 0 ? -1 : 1
      this.rollRate = clamp(3.4 + impact * Math.abs(side) * .12, 4.6, 8)
      this.upwardSpeed = clamp(impact * .12, 1.6, 3.5)
    } else if (this.damage >= 1) {
      this.finish(vehicle, "Car too damaged to continue")
    }
  }

  private advanceRollover(vehicle: VehiclePhysics, dt: number) {
    this.rollElapsed += dt
    const angle = Math.abs(this.rollAngle)
    // Gravity resists the initial lift and assists the fall once the car goes over its side.
    this.rollRate += (-3.6 * Math.cos(angle) - 1.16 * this.rollRate) * dt
    const next = Math.min(Math.PI, angle + this.rollRate * dt)
    this.rollAngle = this.rollDirection * next
    this.rollBounce = Math.max(0, (this.upwardSpeed - 4.903 * this.rollElapsed) * this.rollElapsed)
    const damping = Math.exp(-dt * 2.85)
    vehicle.forwardSpeed *= damping
    vehicle.lateralSpeed *= damping
    vehicle.yawRate *= damping
    const sine = Math.sin(vehicle.yaw)
    const cosine = Math.cos(vehicle.yaw)
    vehicle.x += (vehicle.lateralSpeed * cosine - vehicle.forwardSpeed * sine) * dt
    vehicle.z -= (vehicle.forwardSpeed * cosine + vehicle.lateralSpeed * sine) * dt
    vehicle.yaw += vehicle.yawRate * dt
    vehicle.rpm += (850 - vehicle.rpm) * (1 - damping)
    vehicle.rearSlip = 0
    this.hitBarrier(vehicle)
    if (next === Math.PI) {
      this.rollBounce = 0
      this.finish(vehicle, "Rollover")
    }
  }

  private finish(vehicle: VehiclePhysics, reason: CrashReason) {
    this.phase = "finished"
    this.reason = reason
    vehicle.forwardSpeed = vehicle.lateralSpeed = vehicle.yawRate = vehicle.rearSlip = vehicle.slipAngle = 0
    vehicle.rpm = 850
  }
}
