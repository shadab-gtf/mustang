import { spawnSync } from "node:child_process"
import { mkdir, readFile, writeFile } from "node:fs/promises"
import { pack } from "gltfpack"
import { readGlb } from "../pipeline/gltf_checks.mjs"

const source = new URL("../assets/mustang-jet-black.glb", import.meta.url)
const output = new URL("./public/models/mustang.glb", import.meta.url)
const aligned = (size) => Math.ceil(size / 4) * 4

function resizePng(bytes) {
  const resized = spawnSync("ffmpeg", [
    "-hide_banner", "-loglevel", "error", "-f", "png_pipe", "-i", "pipe:0",
    "-vf", "scale=iw/2:ih/2:flags=area", "-frames:v", "1", "-c:v", "png",
    "-threads", "1", "-f", "image2pipe", "pipe:1",
  ], { input: bytes, maxBuffer: 8 * 1024 * 1024 })
  if (resized.error) throw resized.error
  if (resized.status !== 0 || !resized.stdout.length) {
    throw new Error(`Could not resize the procedural texture: ${resized.stderr.toString().trim()}`)
  }
  return resized.stdout
}

function resizeFinishMaps(gltf, binary) {
  const maps = new Set(gltf.images.filter(({ name, mimeType }) =>
    mimeType === "image/png" && /^(Jet black lacquer|Charcoal interior|Ground steel rotors) (Normal|Roughness)$/.test(name)
  ).map(({ bufferView }) => bufferView))
  let length = 0
  const chunks = gltf.bufferViews.map((view, index) => {
    const start = view.byteOffset ?? 0
    const raw = binary.subarray(start, start + view.byteLength)
    const bytes = maps.has(index) ? resizePng(raw) : raw
    view.byteOffset = length
    view.byteLength = bytes.length
    length += aligned(bytes.length)
    return bytes
  })
  gltf.buffers[0].byteLength = length
  const json = Buffer.from(JSON.stringify(gltf))
  const jsonLength = aligned(json.length)
  const file = Buffer.alloc(28 + jsonLength + length)
  file.write("glTF")
  file.writeUInt32LE(2, 4)
  file.writeUInt32LE(file.length, 8)
  file.writeUInt32LE(jsonLength, 12)
  file.write("JSON", 16)
  file.fill(0x20, 20, 20 + jsonLength)
  json.copy(file, 20)
  file.writeUInt32LE(length, 20 + jsonLength)
  file.write("BIN\0", 24 + jsonLength)
  chunks.forEach((bytes, index) => bytes.copy(file, 28 + jsonLength + gltf.bufferViews[index].byteOffset))
  return file
}

const { gltf, binary } = readGlb(await readFile(source))
const resized = resizeFinishMaps(gltf, binary)
let compressed
await pack([
  "-i", "mustang-source.glb", "-o", "mustang.glb",
  "-cc", "-kn", "-km", "-ke", "-vpf", "-vp", "16", "-vt", "14", "-vn", "12", "-si", "0.59", "-slb",
], {
  read: (path) => {
    if (path !== "mustang-source.glb") throw new Error(`Unexpected gltfpack input: ${path}`)
    return resized
  },
  write: (path, bytes) => {
    if (path !== "mustang.glb") throw new Error(`Unexpected gltfpack output: ${path}`)
    compressed = Buffer.from(bytes)
  },
})
if (!compressed) throw new Error("gltfpack did not produce a model.")
await mkdir(new URL("./public/models/", import.meta.url), { recursive: true })
await writeFile(output, compressed)
console.log(`Preview model: ${(compressed.length / 1_000_000).toFixed(2)} MB`)
