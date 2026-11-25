import assert from "node:assert/strict"
import { test } from "node:test"
import { VehiclePhysics, type DriveInput } from "./physics.ts"
import { BARRIER_OFFSET, circuitSpawn } from "./circuit-layout.ts"
import { CircuitRun } from "./circuit-run.ts"

const IDLE: DriveInput = { throttle: 0, brake: 0, steer: 0, handbrake: 0 }

function advance(car: VehiclePhysics, seconds: number, input: Partial<DriveInput>) {
  const controls = { ...IDLE, ...input }
  for (let frame = 0; frame < Math.round(seconds * 120); frame++) {
    car.step(1 / 120, controls)
  }
}

test("straight-line throttle moves the car forward without introducing side slip", () => {
  const car = new VehiclePhysics()
  advance(car, 4, { throttle: 1 })
  assert.ok(car.forwardSpeed > 11)
  assert.ok(car.z < -22)
  assert.equal(car.x, 0)
  assert.equal(car.yaw, 0)
})

test("automatic drive reaches and holds 300 km/h on a straight", () => {
  const car = new VehiclePhysics()
  advance(car, 55, { throttle: 1 })
  assert.equal(car.gear, 5)
  assert.equal(car.forwardSpeed * 3.6, 300)
  advance(car, 2, {})
  assert.ok(car.forwardSpeed * 3.6 < 295)
})

test("braking stops forward travel without engaging reverse", () => {
  const car = new VehiclePhysics()
  advance(car, 4, { throttle: 1 })
  advance(car, 4, { brake: 1 })
  assert.ok(Math.abs(car.forwardSpeed) < 0.1)
  assert.equal(car.gear, 1)
})

test("reverse gear applies drive torque in the other direction", () => {
  const car = new VehiclePhysics()
  car.shiftGear(-1)
  advance(car, 2, { throttle: 0.7 })
  assert.ok(car.forwardSpeed < -3)
  assert.ok(car.z > 3)
})

test("front steering curves the car away from its straight-line trajectory", () => {
  const car = new VehiclePhysics()
  advance(car, 2, { throttle: 1 })
  advance(car, 1, { throttle: 0.3, steer: 0.6 })
  assert.ok(car.yaw > 0.15)
  assert.ok(car.x < -0.5)
})

test("full steering input builds progressively at 300 km/h", () => {
  const car = new VehiclePhysics()
  car.forwardSpeed = 300 / 3.6
  advance(car, .1, { steer: 1 })
  assert.ok(car.steerAngle < .003)
  advance(car, .6, { steer: 1 })
  assert.ok(car.steerAngle > .003 && car.steerAngle < .007)
  assert.ok(car.yaw > 0 && car.yaw < .15)
})

test("handbrake creates sustained rear slip during a turn", () => {
  const grip = new VehiclePhysics()
  const drift = new VehiclePhysics()
  advance(grip, 3, { throttle: 1 })
  advance(drift, 3, { throttle: 1 })
  advance(grip, 0.75, { steer: 0.72, throttle: 0.6 })
  advance(drift, 0.75, { steer: 0.72, throttle: 0.6, handbrake: 0.92 })
  assert.ok(Math.abs(drift.slipAngle) > Math.abs(grip.slipAngle) + 0.1)
  assert.ok(drift.rearSlip > 0.4)
})

test("a stationary vehicle cannot acquire speed through brake or handbrake", () => {
  const car = new VehiclePhysics()
  advance(car, 2, { brake: 1, handbrake: 1, steer: 1 })
  assert.ok(Math.abs(car.forwardSpeed) < 1e-7)
  assert.ok(Math.abs(car.lateralSpeed) < 1e-7)
})

test("a street launch extends the front suspension while keeping the tires planted", () => {
  const car = new VehiclePhysics()
  advance(car, .8, { throttle: 1 })
  assert.ok(car.suspension[0] < -.012)
  assert.ok(car.suspension[2] > .012)
  assert.equal(car.frontLift, 0)
})

test("a drag launch lifts only under sufficient torque and settles after throttle release", () => {
  const car = new VehiclePhysics()
  car.dragLaunch = true
  advance(car, .5, { throttle: .25 })
  assert.equal(car.frontLift, 0)
  advance(car, .85, { throttle: 1 })
  assert.ok(car.frontLift > .06 && car.frontLift < .22)
  advance(car, .9, {})
  assert.equal(car.frontLift, 0)
})

function approachBarrier(lateralSpeed: number) {
  const car = new VehiclePhysics()
  const run = new CircuitRun()
  run.reset(car, true)
  car.x += Math.cos(car.yaw) * (BARRIER_OFFSET - 1.1)
  car.z -= Math.sin(car.yaw) * (BARRIER_OFFSET - 1.1)
  car.forwardSpeed = 9
  car.lateralSpeed = lateralSpeed
  return { car, run }
}

test("a glancing barrier hit damages the car and pushes it away from the wall", () => {
  const { car, run } = approachBarrier(9)
  for (let step = 0; step < 24; step++) run.step(car, 1 / 120, IDLE)
  assert.equal(run.phase, "driving")
  assert.ok(run.damage > .04 && run.damage < .15)
  assert.ok(car.lateralSpeed < 0)
})

test("a side impact overturns the car and only a reset allows the run to continue", () => {
  const { car, run } = approachBarrier(22)
  for (let step = 0; step < 16; step++) run.step(car, 1 / 120, IDLE)
  assert.equal(run.phase, "rolling")
  assert.ok(Math.abs(run.rollAngle) > 0 && Math.abs(run.rollAngle) < Math.PI)
  for (let step = 0; step < 240; step++) run.step(car, 1 / 120, IDLE)
  assert.equal(run.phase, "finished")
  assert.equal(run.reason, "Rollover")
  assert.equal(Math.abs(run.rollAngle), Math.PI)
  const stoppedAt = [car.x, car.z]
  run.step(car, 1 / 120, { ...IDLE, throttle: 1 })
  assert.deepEqual([car.x, car.z], stoppedAt)
  car.reset()
  run.reset(car, true)
  assert.equal(run.phase, "driving")
  assert.equal(run.damage, 0)
  assert.equal(run.rollAngle, 0)
  assert.deepEqual([car.x, car.z], [circuitSpawn.x, circuitSpawn.z])
})
