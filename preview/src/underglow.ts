import {
  AdditiveBlending, BoxGeometry, CanvasTexture, Group, Mesh, MeshBasicMaterial, PlaneGeometry, type Object3D,
} from "three"
import { BodyStripes, type StripeLayout } from "./body-stripes.ts"

export type Neon = "off" | "orange" | "red" | "violet" | "gray" | "white" | "cream" | "pista" | "mixed"

const ORANGE = 0xff7511
const RED = 0xff172c
const COLORS = {
  orange: ORANGE, red: RED, violet: 0xba4dff, gray: 0xb9bec7, white: 0xf5f6f2, cream: 0xf2dfb7, pista: 0xb8ce91,
} as const

function haloTexture() {
  const canvas = document.createElement("canvas")
  canvas.width = 128
  canvas.height = 128
  const context = canvas.getContext("2d")
  if (!context) throw new Error("Could not create the neon glow texture.")
  const gradient = context.createRadialGradient(64, 64, 0, 64, 64, 64)
  gradient.addColorStop(0, "rgba(255,255,255,.9)")
  gradient.addColorStop(.44, "rgba(255,255,255,.62)")
  gradient.addColorStop(1, "rgba(255,255,255,0)")
  context.fillStyle = gradient
  context.fillRect(0, 0, 128, 128)
  return new CanvasTexture(canvas)
}

export class Underglow {
  private readonly housings = new Group()
  private readonly halos = new Group()
  private readonly strips
  private readonly bodyStripes: BodyStripes
  private enabled = true
  private powered = true

  constructor(chassis: Object3D, ground: Group, hood?: Object3D, trunk?: Object3D) {
    const texture = haloTexture()
    this.strips = [
      { x: -.76, z: -.04, width: .045, length: 1.66 },
      { x: .76, z: -.04, width: .045, length: 1.66 },
      { x: 0, z: 1.94, width: 1.39, length: .045 },
    ].map(({ x, z, width, length }) => {
      const emitter = new MeshBasicMaterial({ toneMapped: false })
      const glow = new MeshBasicMaterial({
        map: texture, transparent: true, depthWrite: false, blending: AdditiveBlending, opacity: .68,
      })
      const bar = new Mesh(new BoxGeometry(width, .014, length), emitter)
      bar.position.set(x, .232, z)
      const halo = new Mesh(new PlaneGeometry(width + 1.06, length + 1.05), glow)
      halo.rotation.x = -Math.PI / 2
      halo.position.set(x, .009, z)
      this.housings.add(bar)
      this.halos.add(halo)
      return { emitter, glow }
    })
    chassis.add(this.housings)
    ground.add(this.halos)
    this.bodyStripes = new BodyStripes(chassis, hood, trunk)
    this.set("orange", "triple")
  }

  set(mode: Neon, layout: StripeLayout) {
    this.enabled = mode !== "off"
    this.setPower(this.powered)
    const color = mode === "off" || mode === "mixed" ? ORANGE : COLORS[mode]
    this.bodyStripes.set(layout, color, mode === "mixed" ? RED : color, mode !== "off")
    this.strips.forEach(({ emitter, glow }, index) => {
      const glowColor = mode === "mixed" && index === 2 ? RED : color
      glow.color.setHex(glowColor)
      emitter.color.setHex(glowColor).multiplyScalar(1.35)
    })
  }

  setPower(powered: boolean) {
    this.powered = powered
    this.housings.visible = this.halos.visible = this.enabled && powered
  }
}
