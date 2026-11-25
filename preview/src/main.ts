import "@fontsource/barlow-condensed/latin-600.css"
import "@fontsource/instrument-sans/latin-400.css"
import "@fontsource/instrument-sans/latin-600.css"
import type { Gear, VehicleTuning } from "./physics.ts"
import type { Headlights, Indicator, Panel } from "./rig.ts"
import type { CameraView, DriveScene, Telemetry } from "./scene.ts"
import type { Neon } from "./underglow.ts"
import type { StripeLayout } from "./body-stripes.ts"

const KEYBOARD: Readonly<Record<string, string>> = {
  KeyW: "KeyW", ArrowUp: "KeyW", KeyS: "KeyS", ArrowDown: "KeyS",
  KeyA: "KeyA", ArrowLeft: "KeyA", KeyD: "KeyD", ArrowRight: "KeyD", Space: "Space",
}
const TUNING: ReadonlyArray<readonly [keyof VehicleTuning, string, number, number, number, string]> = [
  ["mass", "Vehicle mass", 1200, 1900, 10, " kg"],
  ["engineTorque", "Peak engine torque", 260, 650, 5, " Nm"],
  ["steeringSensitivity", "Steering sensitivity", 0.5, 1.35, 0.01, ""],
  ["tireGrip", "Tire grip", 0.65, 1.25, 0.01, ""],
  ["driftAssistance", "Yaw damping", 0, 1, 0.01, ""],
  ["suspensionStiffness", "Spring rate", 22_000, 60_000, 500, " N/m"],
  ["brakeForce", "Brake force", 9_000, 18_000, 100, " N"],
  ["differentialLock", "Differential lock", 0, 1, 0.01, ""],
]
const number = new Intl.NumberFormat(document.documentElement.lang)
let renderRaceStatus: ((data: Telemetry) => void) | undefined

function get<T extends HTMLElement>(id: string, type: { new(): T }) {
  const node = document.getElementById(id)
  if (!(node instanceof type)) throw new Error(`Vehicle preview is missing #${id}.`)
  return node
}

function buttons(attribute: string) {
  return Array.from(document.querySelectorAll<HTMLButtonElement>(`button[${attribute}]`))
}

function pressed(button: HTMLButtonElement) {
  return button.getAttribute("aria-pressed") === "true"
}

function press(button: HTMLButtonElement, active: boolean) {
  button.setAttribute("aria-pressed", String(active))
}

function updateTelemetry(data: Telemetry) {
  speed.textContent = number.format(Math.round(data.speed))
  rpm.textContent = number.format(Math.round(data.rpm))
  slip.textContent = `${number.format(Math.round(data.slipDegrees))}°`
  gear.textContent = data.gear === -1 ? "R" : data.gear === 0 ? "N" : String(data.gear)
  renderRaceStatus?.(data)
}

function connectDriveInputs(scene: DriveScene, driving: () => boolean) {
  const keyboard = new Set<string>()
  const touch = new Map<number, string>()
  const actions = buttons("data-action")
  const active = (action: string) => keyboard.has(action) || Array.from(touch.values()).includes(action)
  const sync = () => {
    scene.accelerate(Number(active("KeyW")))
    scene.brake(Number(active("KeyS")))
    scene.steer(Number(active("KeyA")) - Number(active("KeyD")))
    scene.handbrake(Number(active("Space")))
    for (const button of actions) button.dataset.active = String(active(button.dataset.action ?? ""))
  }
  const clear = () => {
    keyboard.clear()
    touch.clear()
    sync()
  }
  for (const button of actions) {
    const action = button.dataset.action
    if (!action) continue
    button.addEventListener("pointerdown", (event) => {
      button.setPointerCapture(event.pointerId)
      touch.set(event.pointerId, action)
      sync()
    })
    button.addEventListener("lostpointercapture", (event) => {
      touch.delete(event.pointerId)
      sync()
    })
    button.addEventListener("keydown", (event) => {
      if (event.code !== "Enter" && event.code !== "Space") return
      event.preventDefault()
      event.stopPropagation()
      keyboard.add(action)
      sync()
    })
    button.addEventListener("keyup", (event) => {
      if (event.code !== "Enter" && event.code !== "Space") return
      event.preventDefault()
      event.stopPropagation()
      keyboard.delete(action)
      sync()
    })
    button.addEventListener("blur", () => {
      keyboard.delete(action)
      sync()
    })
    button.addEventListener("click", (event) => {
      if (event.detail !== 0) return
      keyboard.add(action)
      sync()
      window.setTimeout(() => { keyboard.delete(action); sync() }, 450)
    })
  }
  window.addEventListener("keydown", (event) => {
    const action = KEYBOARD[event.code]
    if (!action || !driving() || event.metaKey || event.ctrlKey || event.altKey) return
    if (event.target instanceof Element && event.target.closest("input, select, textarea, summary")) return
    if (event.code === "Space" && event.target instanceof HTMLButtonElement) return
    event.preventDefault()
    keyboard.add(action)
    sync()
  })
  window.addEventListener("keyup", (event) => {
    const action = KEYBOARD[event.code]
    if (!action || !keyboard.delete(action)) return
    sync()
  })
  window.addEventListener("blur", clear)
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) clear()
  })
  return clear
}

function connectBodyControls(scene: DriveScene) {
  get("rev-engine", HTMLButtonElement).addEventListener("click", () => scene.revEngine())
  const panels = buttons("data-panel")
  const lock = get("lock", HTMLButtonElement)
  const available = panels.filter((button) => {
    const panel = button.dataset.panel as Panel
    const supported = scene.hasPanel(panel)
    button.disabled = !supported
    return supported
  })
  const doors = available.filter(({ dataset }) => dataset.panel?.startsWith("door"))
  lock.disabled = doors.length === 0
  for (const button of available) {
    button.addEventListener("click", () => {
      const panel = button.dataset.panel as Panel
      const open = !pressed(button)
      if (scene.setPanel(panel, open)) press(button, open)
    })
  }
  for (const side of ["L", "R"] as const) {
    const name = `window-${side.toLowerCase()}`
    const input = get(name, HTMLInputElement)
    const output = get(`${name}-position`, HTMLOutputElement)
    if (!scene.hasWindow(side)) {
      input.disabled = true
      output.value = "Fixed"
      continue
    }
    input.addEventListener("input", () => {
      const value = input.valueAsNumber
      output.value = value === 0 ? "Up" : value === 100 ? "Down" : `${value}% down`
      input.setAttribute("aria-valuetext", output.value)
      scene.setWindow(side, value / 100)
    })
  }
  lock.addEventListener("click", () => {
    const locked = !pressed(lock)
    press(lock, locked)
    scene.setDoorLock(locked)
    for (const button of doors) {
      if (locked) press(button, false)
      button.disabled = locked
    }
  })
  return () => {
    for (const button of available) {
      scene.setPanel(button.dataset.panel as Panel, false)
      press(button, false)
    }
  }
}

function connectEnvironmentControls(scene: DriveScene) {
  const lamps = buttons("data-headlights")
  const lighting = buttons("data-lighting")
  const indicators = buttons("data-indicator")
  const neon = buttons("data-neon")
  const layouts = buttons("data-stripe-layout")
  let color: Neon = "orange"
  let layout: StripeLayout = "triple"
  const updateStripes = () => {
    if (layout === "single" && color === "mixed") color = "orange"
    for (const choice of neon) {
      press(choice, choice.dataset.neon === color)
      choice.disabled = layout === "single" && choice.dataset.neon === "mixed"
    }
    layouts.forEach((choice) => press(choice, choice.dataset.stripeLayout === layout))
    scene.setNeon(color, layout)
  }
  for (const button of neon) button.addEventListener("click", () => {
    color = button.dataset.neon as Neon
    updateStripes()
  })
  for (const button of layouts) button.addEventListener("click", () => {
    layout = button.dataset.stripeLayout as StripeLayout
    updateStripes()
  })
  for (const button of lamps) button.addEventListener("click", () => {
    scene.setHeadlights(button.dataset.headlights as Headlights)
    lamps.forEach((choice) => press(choice, choice === button))
  })
  for (const button of lighting) button.addEventListener("click", () => {
    scene.setNight(button.dataset.lighting === "night")
    lighting.forEach((choice) => press(choice, choice === button))
  })
  for (const button of indicators) {
    const direction = button.dataset.indicator as Exclude<Indicator, "off">
    button.disabled = !scene.hasIndicator(direction)
    button.addEventListener("click", () => {
      const on = !pressed(button)
      scene.setIndicator(on ? direction : "off")
      indicators.forEach((choice) => press(choice, choice === button && on))
    })
  }
  const brakeLamp = get("brake-light", HTMLButtonElement)
  brakeLamp.disabled = !scene.hasBrakeLights()
  brakeLamp.addEventListener("click", () => {
    const on = !pressed(brakeLamp)
    press(brakeLamp, on)
    scene.setBrakeLights(on || undefined)
  })
  const sound = get("sound", HTMLButtonElement)
  const soundFeedback = get("sound-feedback", HTMLParagraphElement)
  sound.addEventListener("click", async () => {
    const on = !pressed(sound)
    sound.disabled = true
    soundFeedback.textContent = ""
    try {
      await scene.setSound(on)
      press(sound, on)
    } catch {
      soundFeedback.textContent = "Sound is unavailable in this browser."
    } finally {
      sound.disabled = false
      sound.focus()
    }
  })
}

function connectTuning(scene: DriveScene) {
  const list = get("tuning-inputs", HTMLDivElement)
  const tuning = scene.physics.tuning
  for (const [key, label, min, max, step, unit] of TUNING) {
    const container = document.createElement("div")
    const input = document.createElement("input")
    const title = document.createElement("label")
    const output = document.createElement("output")
    input.id = `tuning-${key}`
    input.name = key
    input.type = "range"
    input.min = String(min)
    input.max = String(max)
    input.step = String(step)
    input.value = String(tuning[key])
    const markValue = () => {
      output.value = `${number.format(input.valueAsNumber)}${unit}`
      input.setAttribute("aria-valuetext", output.value)
    }
    input.addEventListener("input", () => {
      tuning[key] = input.valueAsNumber
      markValue()
    })
    title.htmlFor = input.id
    title.textContent = label
    output.htmlFor.add(input.id)
    title.append(output)
    container.append(title, input)
    list.append(container)
    markValue()
  }
}

function connectFullscreenDrive(clearDriveInput: () => void) {
  const button = get("fullscreen-drive", HTMLButtonElement)
  const sync = () => {
    const expanded = document.fullscreenElement === viewport || viewport.hasAttribute("data-expanded")
    button.textContent = expanded ? "Exit fullscreen" : "Fullscreen"
    clearDriveInput()
    if (expanded) canvas.focus({ preventScroll: true })
    else if (!button.hidden) button.focus({ preventScroll: true })
  }
  const close = () => {
    if (document.fullscreenElement === viewport) return document.exitFullscreen()
    if (viewport.hasAttribute("data-expanded")) {
      viewport.removeAttribute("data-expanded")
      sync()
    }
  }
  button.addEventListener("click", async () => {
    if (document.fullscreenElement === viewport || viewport.hasAttribute("data-expanded")) {
      await close()
      return
    }
    if (document.fullscreenEnabled) {
      try {
        await viewport.requestFullscreen()
        return
      } catch {
        // Embedded browsers can disallow native fullscreen.
      }
    }
    viewport.setAttribute("data-expanded", "")
    sync()
  })
  document.addEventListener("fullscreenchange", sync)
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && viewport.hasAttribute("data-expanded")) close()
  })
  return (driving: boolean) => {
    button.hidden = !driving
    if (!driving) close()
  }
}

function connectControls(scene: DriveScene, paintMap: (x: number, z: number, yaw: number) => string) {
  let driving = false
  const modeButtons = buttons("data-mode")
  const angles = buttons("data-camera")
  const driveControls = get("drive-controls", HTMLDivElement)
  const driveInput = get("drive-input", HTMLDivElement)
  const inspectionControls = get("inspection-controls", HTMLDivElement)
  const reset = get("reset", HTMLButtonElement)
  const hint = get("orbit-hint", HTMLSpanElement)
  const transmission = get("select-gear", HTMLSelectElement)
  const feedback = get("control-feedback", HTMLParagraphElement)
  const course = get("drive-course", HTMLSelectElement)
  const condition = get("condition", HTMLDivElement)
  const conditionValue = get("condition-value", HTMLElement)
  const guide = get("route-guide", HTMLDivElement)
  const nextTurn = get("next-turn", HTMLParagraphElement)
  const raceOver = get("race-over", HTMLDivElement)
  const reason = get("race-over-reason", HTMLParagraphElement)
  const restart = get("race-restart", HTMLButtonElement)
  const closePanels = connectBodyControls(scene)
  const clearDriveInput = connectDriveInputs(scene, () => driving && raceOver.hidden === true)
  const showFullscreenDrive = connectFullscreenDrive(clearDriveInput)
  const drift = get("drift", HTMLButtonElement)
  const launch = get("drag-launch", HTMLButtonElement)
  launch.addEventListener("click", () => {
    const on = !pressed(launch)
    scene.setDragLaunch(on)
    press(launch, on)
  })
  connectEnvironmentControls(scene)
  connectTuning(scene)
  renderRaceStatus = (data) => {
    const racing = driving && data.course === "circuit"
    const ended = racing && data.phase === "finished"
    guide.hidden = condition.hidden = !racing
    driveInput.hidden = !driving || (racing && data.phase !== "driving")
    if (racing) {
      conditionValue.textContent = `${Math.round((1 - data.damage) * 100)}%`
      const direction = paintMap(data.x, data.z, data.yaw)
      if (nextTurn.textContent !== direction) nextTurn.textContent = direction
    }
    if (ended && raceOver.hidden) {
      reason.textContent = data.reason ?? ""
      raceOver.hidden = false
      clearDriveInput()
      restart.focus({ preventScroll: true })
    } else if (!ended) {
      raceOver.hidden = true
    }
  }
  const chooseCamera = (view: CameraView) => {
    const panel = view === "cabin" ? "doorL" : view === "engine" ? "hood" : view === "trunk" ? "trunk" : undefined
    if (panel && scene.setPanel(panel, true)) {
      const control = buttons("data-panel").find(({ dataset }) => dataset.panel === panel)
      if (control) press(control, true)
    }
    scene.setView(view)
    angles.forEach((button) => press(button, button.dataset.camera === view))
    hint.textContent = panel ? "" : "Drag to orbit. Scroll to zoom."
  }
  for (const button of angles) button.addEventListener("click", () => chooseCamera(button.dataset.camera as CameraView))
  for (const button of modeButtons) button.addEventListener("click", () => {
    const drive = button.dataset.mode === "drive"
    if (driving === drive) return
    driving = drive
    clearDriveInput()
    inspectionControls.hidden = drive
    driveControls.hidden = !drive
    driveInput.hidden = !drive
    showFullscreenDrive(drive)
    get("telemetry", HTMLDivElement).hidden = !drive
    get("angles", HTMLFieldSetElement).hidden = drive
    hint.textContent = drive ? "Chase camera" : "Drag to orbit. Scroll to zoom."
    modeButtons.forEach((mode) => press(mode, mode === button))
    if (drive) closePanels()
    scene.setDriveMode(drive)
    if (drive) canvas.focus({ preventScroll: true })
    else chooseCamera("front")
    transmission.value = "auto"
    feedback.textContent = ""
  })
  const resetDriveControls = () => {
    clearDriveInput()
    raceOver.hidden = true
    transmission.value = "auto"
    feedback.textContent = ""
  }
  reset.addEventListener("click", () => {
    resetDriveControls()
    scene.reset()
    if (!driving) chooseCamera("front")
  })
  restart.addEventListener("click", () => {
    resetDriveControls()
    scene.reset()
    canvas.focus({ preventScroll: true })
  })
  course.addEventListener("change", () => {
    resetDriveControls()
    scene.setCourse(course.value === "pad" ? "pad" : "circuit")
    canvas.focus({ preventScroll: true })
  })
  transmission.addEventListener("change", () => {
    const requested = transmission.value === "auto" ? "auto" : Number(transmission.value) as Gear
    if (scene.shiftGear(requested)) {
      feedback.textContent = ""
      return
    }
    feedback.textContent = "Brake to a stop before changing drive direction."
    transmission.value = String(scene.physics.transmission)
  })
  drift.addEventListener("click", () => {
    const on = !pressed(drift)
    press(drift, on)
    scene.setDriftMode(on)
  })
  get("modes", HTMLFieldSetElement).disabled = false
  get("angles", HTMLFieldSetElement).disabled = false
  get("controls", HTMLFieldSetElement).disabled = false
  reset.disabled = false
}

const speed = get("speed", HTMLSpanElement)
const gear = get("gear", HTMLElement)
const rpm = get("rpm", HTMLElement)
const slip = get("slip", HTMLElement)
const viewport = get("viewport", HTMLDivElement)
const canvas = get("canvas", HTMLCanvasElement)
const loading = get("loading", HTMLDivElement)
const failure = get("failure", HTMLDivElement)
get("retry", HTMLButtonElement).addEventListener("click", () => location.reload())

function showFailure(error: unknown) {
  const reason = error instanceof Error ? error.message : "The model could not be loaded."
  loading.hidden = true
  failure.hidden = false
  get("failure-detail", HTMLParagraphElement).textContent =
    `${reason} Reload the preview or check that your browser supports WebGL 2.`
  viewport.setAttribute("aria-busy", "false")
}

canvas.addEventListener("webglcontextlost", () => {
  showFailure(new Error("The graphics context was lost."))
  get("modes", HTMLFieldSetElement).disabled = true
  get("angles", HTMLFieldSetElement).disabled = true
  get("controls", HTMLFieldSetElement).disabled = true
  get("reset", HTMLButtonElement).disabled = true
})

import("./scene.ts")
  .then(async ({ createPreview, createCircuitMap }) => {
    const scene = await createPreview(canvas, `${import.meta.env.BASE_URL}models/mustang.glb`, updateTelemetry)
    connectControls(scene, createCircuitMap(get("circuit-map", HTMLCanvasElement)))
    viewport.setAttribute("aria-busy", "false")
    loading.hidden = true
  })
  .catch(showFailure)
