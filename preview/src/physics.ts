export interface DriveInput {
  throttle: number
  brake: number
  steer: number
  handbrake: number
}

export interface VehicleTuning {
  mass: number
  engineTorque: number
  steeringSensitivity: number
  tireGrip: number
  driftAssistance: number
  suspensionStiffness: number
  brakeForce: number
  differentialLock: number
}

export type Gear = -1 | 0 | 1 | 2 | 3 | 4 | 5
export type Transmission = Gear | "auto"
export const TOP_SPEED_KPH = 300
const WHEEL_RADIUS = 0.2977
export const HALF_TRACK = 0.7416
export const FRONT_AXLE_Z = -1.4026
export const REAR_AXLE_Z = 1.2921
export const WHEELBASE = REAR_AXLE_Z - FRONT_AXLE_Z
export const FIXED_STEP = 1 / 120

const FRONT_ARM = 1.27
const REAR_ARM = WHEELBASE - FRONT_ARM
const STREET_CG_HEIGHT = .53
const DRAG_REAR_ARM = 1.03
const DRAG_CG_HEIGHT = .75
const GRAVITY = 9.80665
const FINAL_DRIVE = 3.73
const WHEEL_RPM_PER_MPS = 60 / (2 * Math.PI * WHEEL_RADIUS)
const AUTO_UPSHIFT_RPM = 7000
const AUTO_DOWNSHIFT_RPM = 3450
const FORWARD_GEARS = [1, 2, 3, 4, 5] as const
const GEAR_RATIOS: Record<Gear, number> = { [-1]: -3.35, 0: 0, 1: 3.19, 2: 1.98, 3: 1.30, 4: 0.94, 5: 0.67 }
const DEFAULTS: VehicleTuning = {
  mass: 1540, engineTorque: 590, steeringSensitivity: 1, tireGrip: 1.03,
  driftAssistance: 0.18, suspensionStiffness: 34_000, brakeForce: 14_000, differentialLock: 0.46,
}

export function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value))
}

function combinedLateral(slip: number, load: number, grip: number, longitudinal: number) {
  const limit = load * grip
  const remaining = Math.sqrt(Math.max(0, limit * limit - longitudinal * longitudinal))
  return -Math.tanh(7.8 * slip) * remaining
}

/** Planar axle-force model. Engine torque acts at the rear axle, with per-corner visual travel. */
export class VehiclePhysics {
  readonly tuning: VehicleTuning
  readonly suspension = [0, 0, 0, 0]
  readonly wheelAngle = [0, 0, 0, 0]
  private readonly suspensionVelocity = [0, 0, 0, 0]
  x = 0
  z = 0
  yaw = 0
  yawRate = 0
  forwardSpeed = 0
  lateralSpeed = 0
  steerAngle = 0
  slipAngle = 0
  rearSlip = 0
  rpm = 850
  pitch = 0
  roll = 0
  launchPitch = 0
  frontLift = 0
  gear: Gear = 1
  transmission: Transmission = "auto"
  driftMode = false
  dragLaunch = false
  private longitudinalAcceleration = 0
  private launchPitchRate = 0

  constructor(tuning: Partial<VehicleTuning> = {}) {
    this.tuning = { ...DEFAULTS, ...tuning }
  }

  shiftGear(transmission: Transmission) {
    this.transmission = transmission
    if (transmission !== "auto") {
      this.gear = transmission
      return
    }
    const outputRpm = Math.max(0, this.forwardSpeed) * WHEEL_RPM_PER_MPS * FINAL_DRIVE
    this.gear = FORWARD_GEARS.find((gear) => outputRpm * GEAR_RATIOS[gear] < AUTO_UPSHIFT_RPM) ?? 5
  }

  reset() {
    this.x = this.z = this.yaw = this.yawRate = 0
    this.forwardSpeed = this.lateralSpeed = this.steerAngle = 0
    this.slipAngle = this.rearSlip = this.pitch = this.roll = this.longitudinalAcceleration = 0
    this.launchPitch = this.launchPitchRate = this.frontLift = 0
    this.rpm = 850
    this.shiftGear("auto")
    this.suspension.fill(0)
    this.suspensionVelocity.fill(0)
    this.wheelAngle.fill(0)
  }

  step(dt: number, input: DriveInput, surfaceGrip = 1) {
    const { mass, tireGrip, engineTorque, brakeForce, steeringSensitivity, differentialLock, driftAssistance } = this.tuning
    const forward = this.forwardSpeed
    const lateral = this.lateralSpeed
    const speed = Math.hypot(forward, lateral)
    const outputRpm = Math.abs(forward) * WHEEL_RPM_PER_MPS * FINAL_DRIVE
    if (this.transmission === "auto") this.shiftAutomatically(outputRpm)
    // The bicycle model's curvature limit keeps commanded lateral acceleration near tire grip.
    const steeringLimit = Math.atan(1.13 * GRAVITY * WHEELBASE * surfaceGrip / Math.max(48, speed * speed))
    const steeringRate = 8.5 - 4.5 * clamp(speed / 65, 0, 1)
    const steeringTarget = clamp(input.steer * steeringSensitivity, -1, 1) * steeringLimit
    this.steerAngle += (steeringTarget - this.steerAngle) * (1 - Math.exp(-dt * steeringRate))
    const cosine = Math.cos(this.steerAngle)
    const sine = Math.sin(this.steerAngle)
    const dragSetup = this.dragLaunch && this.gear === 1 && speed < 19 &&
      Math.abs(this.steerAngle) < .14 && input.handbrake < .08
    const height = dragSetup ? DRAG_CG_HEIGHT : STREET_CG_HEIGHT
    const rearArm = dragSetup ? DRAG_REAR_ARM : REAR_ARM
    const frontArm = WHEELBASE - rearArm

    const frontLateral = lateral - frontArm * this.yawRate
    const rearLateral = lateral + rearArm * this.yawRate
    const frontRolling = forward * cosine - frontLateral * sine
    const frontSlip = Math.atan2(frontLateral * cosine + forward * sine, Math.max(2.6, Math.abs(frontRolling)))
    const rearSlip = Math.atan2(rearLateral, Math.max(2.6, Math.abs(forward)))
    const weight = mass * GRAVITY
    const transfer = mass * this.longitudinalAcceleration * height / WHEELBASE
    const frontLoad = this.frontLift > 0 ? 0 : clamp(weight * rearArm / WHEELBASE - transfer, 0, weight * .86)
    const rearLoad = weight - frontLoad
    const frontGrip = tireGrip * surfaceGrip
    const rearGrip = frontGrip * (1 - input.handbrake * 0.60) * (dragSetup ? 2.42 : this.driftMode ? .78 : 1)
    const ratio = GEAR_RATIOS[this.gear] * FINAL_DRIVE
    const drivelineRpm = outputRpm * Math.abs(GEAR_RATIOS[this.gear])
    const targetRpm = clamp(Math.max(drivelineRpm, 850 + input.throttle * (this.gear === 0 ? 6300 : 2100)), 850, 7900)
    this.rpm += (targetRpm - this.rpm) * (1 - Math.exp(-dt * 8))
    const torqueFraction = (0.75 + 0.25 * Math.sin(clamp((this.rpm - 850) / 6050, 0, 1) * Math.PI))
      * clamp((7900 - this.rpm) / 1150, 0, 1)
    const driveTorque = engineTorque * (dragSetup ? 2.15 : 1)
    const rearDrive = driveTorque * torqueFraction * ratio * .87 * input.throttle
      * (1 - input.handbrake * .88) / WHEEL_RADIUS
    const brakeDemand = Math.min(brakeForce * input.brake, Math.abs(forward) * mass / dt)
    const frontBrake = -Math.sign(frontRolling) * brakeDemand * 0.66
    const rearBrake = -Math.sign(forward) * (brakeDemand * 0.34 + Math.min(Math.abs(forward) * mass / dt, 7_400 * input.handbrake))
    const rearDemand = rearDrive + rearBrake
    const rearLongitudinal = clamp(rearDemand, -rearLoad * rearGrip, rearLoad * rearGrip)
    const frontLongitudinal = clamp(frontBrake, -frontLoad * frontGrip, frontLoad * frontGrip)
    const frontSide = combinedLateral(frontSlip, frontLoad, frontGrip, frontLongitudinal)
    const rearSide = combinedLateral(rearSlip, rearLoad, rearGrip, rearLongitudinal)
    const forceRightFront = frontSide * cosine - frontLongitudinal * sine
    const forceForward = rearLongitudinal + frontLongitudinal * cosine + frontSide * sine
    const rollingResistance = -Math.tanh(forward * 2.5) * (135 + 0.44 * forward * forward + (1 - surfaceGrip) * 1300)
    const forceRight = forceRightFront + rearSide
    const yawMoment = -frontArm * forceRightFront + rearArm * rearSide
    const yawAssist = -this.yawRate * (95 + 950 * driftAssistance * clamp(Math.abs(rearSlip) * 3, 0, 1))
    this.yawRate += (yawMoment + yawAssist) / (mass * 1.56) * dt
    const acceleration = (forceForward + rollingResistance) / mass
    const velocity = forward + (acceleration - this.yawRate * lateral) * dt
    this.forwardSpeed = Math.min(velocity, TOP_SPEED_KPH / 3.6)
    this.lateralSpeed += (forceRight / mass + this.yawRate * forward) * dt
    this.yaw += this.yawRate * dt
    this.x += (-this.forwardSpeed * Math.sin(this.yaw) + this.lateralSpeed * Math.cos(this.yaw)) * dt
    this.z += (-this.forwardSpeed * Math.cos(this.yaw) - this.lateralSpeed * Math.sin(this.yaw)) * dt

    this.slipAngle = Math.atan2(this.lateralSpeed, Math.max(0.8, Math.abs(this.forwardSpeed)))
    const excessDrive = Math.max(0, Math.abs(rearDrive) - rearLoad * rearGrip)
    const wheelspin = clamp(excessDrive / (rearLoad * rearGrip) * (0.65 + differentialLock * 0.7), 0, 2.25)
    this.rearSlip = clamp(Math.abs(rearSlip) * 2.8 + wheelspin + input.handbrake * 0.8, 0, 1) * clamp(speed / 2.8, 0, 1)
    const limitedAcceleration = acceleration - (velocity - this.forwardSpeed) / dt
    this.longitudinalAcceleration += (limitedAcceleration - this.longitudinalAcceleration) * (1 - Math.exp(-dt * 12))
    this.updateSuspension(dt, forceRight / mass, wheelspin, input.handbrake, height)
    this.updateLaunchPitch(dt, height, rearArm)
  }

  private shiftAutomatically(outputRpm: number) {
    const gearIndex = this.gear - 1
    const rpm = outputRpm * GEAR_RATIOS[this.gear]
    const higher = FORWARD_GEARS[gearIndex + 1]
    const lower = FORWARD_GEARS[gearIndex - 1]
    if (higher && rpm >= AUTO_UPSHIFT_RPM) this.gear = higher
    else if (lower && rpm <= AUTO_DOWNSHIFT_RPM) this.gear = lower
  }

  private updateLaunchPitch(dt: number, height: number, rearArm: number) {
    if (this.forwardSpeed <= 0 && this.launchPitch === 0) {
      this.launchPitch = this.launchPitchRate = this.frontLift = 0
      return
    }
    // Compute pitch moment about the rear contact patch. The tires lift once drive moment exceeds gravity.
    const theta = this.launchPitch
    const lever = rearArm * Math.cos(theta) - height * Math.sin(theta)
    const centerHeight = height * Math.cos(theta) + rearArm * Math.sin(theta)
    const momentPerMass = this.longitudinalAcceleration * centerHeight - GRAVITY * lever
    this.launchPitchRate += (momentPerMass / (1.54 + rearArm ** 2) - 4.8 * this.launchPitchRate - 11 * theta) * dt
    const next = theta + this.launchPitchRate * dt
    this.launchPitch = clamp(next, 0, .10)
    if (next !== this.launchPitch) this.launchPitchRate = 0
    this.frontLift = Math.max(0, WHEELBASE * Math.sin(this.launchPitch) - .062)
  }

  private updateSuspension(dt: number, lateralAcceleration: number, wheelspin: number, handbrake: number, height: number) {
    const { mass, suspensionStiffness, differentialLock } = this.tuning
    const sprungMass = mass * 0.22
    const driftLoad = this.rearSlip * clamp(Math.hypot(this.forwardSpeed, this.lateralSpeed) / 7, 0, 1)
    const foreAftLoad = mass * this.longitudinalAcceleration * height / (2 * WHEELBASE)
    const sideLoad = mass * lateralAcceleration * height / (4 * HALF_TRACK)
    for (let corner = 0; corner < 4; corner++) {
      const isFront = corner < 2
      const isLeft = corner % 2 === 0
      const load = foreAftLoad * (isFront ? -1 : 1) + sideLoad * (isLeft ? 1 : -1)
      const flex = driftLoad * (isFront ? 0.48 : 1)
      const rate = suspensionStiffness * (1 - 0.27 * flex)
      const damping = (1.5 - 0.62 * flex) * Math.sqrt(rate * sprungMass)
      const springForce = load - this.suspension[corner] * rate - this.suspensionVelocity[corner] * damping
      this.suspensionVelocity[corner] += springForce / sprungMass * dt
      const travel = this.suspension[corner] + this.suspensionVelocity[corner] * dt
      this.suspension[corner] = clamp(travel, -0.065 - 0.026 * flex, 0.075 + 0.029 * flex)
      if (this.suspension[corner] !== travel) this.suspensionVelocity[corner] = 0
      const wheelDifferential = (isLeft ? -1 : 1) * this.yawRate * HALF_TRACK * (isFront ? 1 : 1 - differentialLock)
      const rollingSpeed = this.forwardSpeed + wheelDifferential
      const tireSpeed = isFront ? rollingSpeed : rollingSpeed * (1 - handbrake) + wheelspin * Math.sign(this.gear) * 8
      this.wheelAngle[corner] = (this.wheelAngle[corner] - tireSpeed / WHEEL_RADIUS * dt) % (2 * Math.PI)
    }
    this.pitch = (this.suspension[2] + this.suspension[3] - this.suspension[0] - this.suspension[1]) / (2 * WHEELBASE)
    this.roll = (this.suspension[0] + this.suspension[2] - this.suspension[1] - this.suspension[3]) / (4 * HALF_TRACK)
  }
}
