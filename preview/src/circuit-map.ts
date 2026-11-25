import { circuitSamples, nearestRoad, nextCircuitTurn, type RoadContact } from "./circuit-layout.ts"

export function createCircuitMap(canvas: HTMLCanvasElement) {
  const context = canvas.getContext("2d")
  if (!context) return () => ""
  const minX = Math.min(...circuitSamples.map(({ x }) => x))
  const maxX = Math.max(...circuitSamples.map(({ x }) => x))
  const minZ = Math.min(...circuitSamples.map(({ z }) => z))
  const maxZ = Math.max(...circuitSamples.map(({ z }) => z))
  const scale = Math.min((canvas.width - 24) / (maxX - minX), (canvas.height - 24) / (maxZ - minZ))
  const offsetX = (canvas.width - (minX + maxX) * scale) / 2
  const offsetZ = (canvas.height - (minZ + maxZ) * scale) / 2
  const route = new Path2D()
  const start = circuitSamples[0]
  route.moveTo(start.x * scale + offsetX, start.z * scale + offsetZ)
  for (const { x, z } of circuitSamples.slice(1)) route.lineTo(x * scale + offsetX, z * scale + offsetZ)
  route.closePath()
  const arrow = new Path2D()
  arrow.moveTo(0, -12)
  arrow.lineTo(7, 7)
  arrow.lineTo(0, 4)
  arrow.lineTo(-7, 7)
  arrow.closePath()
  const contact: RoadContact = { index: 0, distance: 0, nx: 0, nz: 0 }

  return (x: number, z: number, yaw: number) => {
    context.clearRect(0, 0, canvas.width, canvas.height)
    context.strokeStyle = "#d7ddd8"
    context.lineWidth = 4
    context.lineJoin = "round"
    context.stroke(route)
    nearestRoad(x, z, contact)
    const next = new Path2D()
    for (let step = 0; step <= 52; step++) {
      const point = circuitSamples[(contact.index + step) % circuitSamples.length]
      const px = point.x * scale + offsetX
      const py = point.z * scale + offsetZ
      if (step === 0) next.moveTo(px, py)
      else next.lineTo(px, py)
    }
    context.strokeStyle = "#f9a36e"
    context.lineWidth = 6
    context.stroke(next)
    context.fillStyle = "#f6f7f1"
    context.fillRect(start.x * scale + offsetX - 3.5, start.z * scale + offsetZ - 4, 7, 8)
    context.save()
    context.translate(x * scale + offsetX, z * scale + offsetZ)
    context.rotate(-yaw)
    context.fillStyle = "#f9a36e"
    context.strokeStyle = "#1f2723"
    context.lineWidth = 2
    context.fill(arrow)
    context.stroke(arrow)
    context.restore()
    const turn = nextCircuitTurn(contact.index)
    if (!turn) return "Straight ahead"
    const arrowLabel = turn.direction === "left" ? "← Left" : "Right →"
    return turn.distance < 20 ? arrowLabel : `${arrowLabel} in ${Math.round(turn.distance / 10) * 10} m`
  }
}
