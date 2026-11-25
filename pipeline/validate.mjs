import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { basename } from 'node:path';
import { checkUnitVectors, getItem, near, readAccessors, readGlb, readPrimitives, readScene } from './gltf_checks.mjs';

const files = ['mustang.glb', 'mustang-lod1.glb', 'mustang-lod2.glb', 'mustang-lod3.glb', 'mustang-collision.glb'];
const corners = ['FL', 'FR', 'RL', 'RR'];
const lamps = [
  'HeadlightEmission', 'HighBeamEmission', 'FrontIndicator_L', 'FrontIndicator_R',
  'RearIndicator_L', 'RearIndicator_R', 'TailEmission', 'BrakeEmission',
  'ReverseEmission', 'DashEmission',
];
const ranges = {
  length: [4.59, 4.74], width: [1.75, 2.16], height: [1.19, 1.42], ground: [-0.03, 0.05],
};

function checkConvexHull(primitive, name) {
  const { positions, indices, triangles } = primitive;
  const vertices = new Map();
  const edges = new Map();
  const planes = [];
  for (let index = 0; index < triangles * 3; index += 3) {
    const points = [0, 1, 2].map((corner) => {
      const offset = (indices?.[index + corner] ?? (index + corner)) * 3;
      return positions.subarray(offset, offset + 3);
    });
    const keys = points.map((point) => point.join(','));
    for (let corner = 0; corner < 3; corner++) {
      const first = keys[corner];
      const next = keys[(corner + 1) % 3];
      const ordered = first < next;
      const edge = ordered ? `${first}|${next}` : `${next}|${first}`;
      const counts = edges.get(edge) ?? [0, 0];
      counts[Number(ordered)]++;
      edges.set(edge, counts);
      vertices.set(first, points[corner]);
    }
    const [a, b, c] = points;
    const [u, v, w] = b.map((value, axis) => value - a[axis]);
    const [x, y, z] = c.map((value, axis) => value - a[axis]);
    const normal = [v * z - w * y, w * x - u * z, u * y - v * x];
    planes.push({ a, normal });
  }
  assert([...edges.values()].every(([forward, backward]) => forward === 1 && backward === 1),
    `${name} must be a closed mesh with consistent face winding`);
  for (const { a, normal } of planes) {
    const tolerance = Math.hypot(...normal) * 1e-5;
    for (const point of vertices.values()) {
      const distance = normal.reduce((total, value, axis) => total + value * (point[axis] - a[axis]), 0);
      assert(distance <= tolerance, `${name} must be convex with outward-facing triangles`);
    }
  }
}

function checkRig(nodes, materials) {
  function expect(name, parent) {
    const entry = nodes.get(name);
    assert(entry, `missing rig node ${name}`);
    if (parent) assert.equal(entry.parent, parent, `${name} parent`);
    return entry;
  }
  expect('Vehicle');
  expect('Chassis', 'Vehicle');
  for (const name of ['Door_L', 'Door_R', 'Hood', 'Trunk', 'SteeringWheel', 'Engine']) expect(name, 'Chassis');
  expect('Window_L', 'Door_L');
  expect('Window_R', 'Door_R');
  assert(expect('Door_L').position[0] < -0.6 && expect('Door_R').position[0] > 0.6, 'door hinges must be on their respective sides');
  assert(expect('Hood').position[2] < 0 && expect('Trunk').position[2] > 0, 'hood and trunk hinges must be ahead of and behind the cabin');
  for (const corner of corners) {
    const suspension = expect(`Suspension_${corner}`);
    assert(['Vehicle', 'Chassis'].includes(suspension.parent), `Suspension_${corner} must follow the vehicle or chassis`);
    const steer = expect(`Steer_${corner}`, `Suspension_${corner}`);
    const wheel = expect(`Wheel_${corner}`, `Steer_${corner}`);
    const sign = corner.endsWith('L') ? -1 : 1;
    near(wheel.position[0], sign * 0.7366, 0.075, `${corner} track position`);
    near(wheel.position[1], corner.startsWith('F') ? 0.32705 : 0.33755, 0.017, `${corner} axle height`);
    wheel.position.forEach((value, axis) => near(value, steer.position[axis], 0.005, `${corner} wheel and steer centers`));
  }
  for (const side of ['L', 'R']) {
    const first = expect(`Wheel_F${side}`).position[2];
    const last = expect(`Wheel_R${side}`).position[2];
    assert(first < 0 && last > 0, `${side} axles face the incorrect direction`);
    near(last - first, 2.7432, 0.024, `${side} wheelbase`);
  }
  const names = new Set(materials.map((material) => material.name));
  for (const lamp of lamps) assert(names.has(lamp), `missing lamp material ${lamp}`);
}

const expectedClips = {
  Doors: ['Door_L.rotation', 'Door_R.rotation'],
  Windows: ['Window_L.translation', 'Window_R.translation'],
  Hood: ['Hood.rotation'], Trunk: ['Trunk.rotation'],
  Steering: ['Steer_FL.rotation', 'Steer_FR.rotation', 'SteeringWheel.rotation'],
  Suspension: corners.map((corner) => `Suspension_${corner}.translation`),
  Wheel_Rotation: corners.map((corner) => `Wheel_${corner}.rotation`),
  Engine_Idle: ['Engine.rotation'],
};

function checkAnimations(gltf, accessors, scene) {
  const clips = new Set();
  const targets = new Set([...scene.nodes.values()].map((node) => node.index));
  for (const clip of gltf.animations ?? []) {
    assert(clip.name && !clips.has(clip.name), `duplicate or empty animation name ${clip.name}`);
    clips.add(clip.name);
    const changing = new Set();
    const channels = new Set();
    for (const channel of clip.channels) {
      const node = getItem(gltf.nodes, channel.target.node, `${clip.name} target`);
      assert(targets.has(channel.target.node), `${clip.name} target is outside the scene`);
      const track = `${node.name}.${channel.target.path}`;
      assert(!channels.has(track), `${clip.name} has a duplicate ${track}`);
      channels.add(track);
      if (checkChannel(clip, channel, accessors, track)) changing.add(track);
    }
    assert(changing.size > 0, `${clip.name} does not move any target`);
    for (const track of expectedClips[clip.name] ?? []) {
      assert(changing.has(track), `${clip.name} is missing motion for ${track}`);
    }
  }
  for (const name of Object.keys(expectedClips)) assert(clips.has(name), `missing animation ${name}`);
  return clips.size;
}

function checkChannel(clip, channel, accessors, label) {
  const sampler = getItem(clip.samplers, channel.sampler, label);
  const input = getItem(accessors, sampler.input, label);
  const output = getItem(accessors, sampler.output, label);
  assert(input.type === 'SCALAR' && input.componentType === 5126, `${label} invalid animation input`);
  assert(input.values.every((value, index) => index === 0 ? value >= 0 : value > input.values[index - 1]),
    `${label} animation times must increase`);
  const rotation = channel.target.path === 'rotation';
  const interpolation = sampler.interpolation ?? 'LINEAR';
  assert(interpolation === 'LINEAR' || interpolation === 'STEP', `${label} uses unexpected interpolation ${interpolation}`);
  assert(output.count === input.count && output.type === (rotation ? 'VEC4' : 'VEC3') && output.componentType === 5126,
    `${label} animation output format`);
  if (rotation) checkUnitVectors(output, 4, label);
  if (clip.name === 'Windows' && label.startsWith('Window_')) {
    const [initialY] = output.values.subarray(1, 2);
    near(initialY - output.min[1], 0.422, 0.065, `${label} window descent`);
  }
  return output.min.some((value, index) => output.max[index] - value > 1e-6);
}

function validate(data, name) {
  const collision = basename(name) === 'mustang-collision.glb';
  const { gltf, binary } = readGlb(data);
  const accessors = readAccessors(gltf, binary);
  const meshes = readPrimitives(gltf, accessors, collision);
  const scene = readScene(gltf, meshes);
  const [width, height, length] = scene.max.map((value, axis) => value - scene.min[axis]);
  let clips = 0;
  if (collision) {
    assert(scene.triangles <= 512 && scene.degenerate === 0 && (gltf.animations?.length ?? 0) === 0,
      `collision requires at most 512 valid triangles and no animations, got ${scene.triangles} triangles (${scene.degenerate} degenerate)`);
    const root = scene.nodes.get('Collision');
    assert(root && root.parent === undefined && root.node.mesh === undefined, 'collision root must be an empty scene root');
    for (const name of ['Hull_Lower', 'Hull_Nose', 'Hull_Cab']) {
      const hull = scene.nodes.get(name);
      assert(hull?.parent === 'Collision' && Number.isInteger(hull.node.mesh), `missing collision mesh ${name}`);
      const primitives = meshes[hull.node.mesh];
      assert.equal(primitives.length, 1, `${name} requires one collision surface`);
      checkConvexHull(primitives[0], name);
    }
    assert(length > 4 && length < 4.85 && width > 1.4 && width < 1.95 && height > 0.7 && height < 1.43,
      'collision body bounds do not cover the car');
  } else {
    checkRig(scene.nodes, gltf.materials);
    clips = checkAnimations(gltf, accessors, scene);
    for (const [dimension, value] of Object.entries({ length, width, height, ground: scene.min[1] })) {
      const [minimum, maximum] = ranges[dimension];
      assert(value >= minimum && value <= maximum, `${dimension} ${value.toFixed(4)} m is outside [${minimum}, ${maximum}] m`);
    }
    assert(scene.degenerate / scene.triangles < 0.005, `${scene.degenerate} of ${scene.triangles} triangles are degenerate`);
  }
  return { bytes: data.length, clips, width, height, length, scene };
}

const paths = process.argv.slice(2);
const results = new Map();
for (const path of paths.length ? paths : files.map((file) => new URL(`../assets/${file}`, import.meta.url))) {
  const name = basename(path instanceof URL ? path.pathname : path);
  try {
    const result = validate(await readFile(path), name);
    results.set(name, result.scene.triangles);
    const { width, height, length, scene, clips, bytes } = result;
    const dimensions = [length, width, height].map((value) => value.toFixed(3)).join(' × ');
    console.log(`${name.padEnd(23)} ${dimensions} m · ${scene.triangles.toLocaleString('en-US')} tris · ${scene.primitives} primitives · ${clips} clips · ${(bytes / 1_048_576).toFixed(2)} MiB · ${scene.degenerate} degenerate`);
  } catch (error) {
    console.error(`${name} FAILED — ${error.message}`);
    process.exitCode = 1;
  }
}
for (let index = 1; index < 4; index++) {
  const previous = results.get(files[index - 1]);
  const current = results.get(files[index]);
  if (current !== undefined && previous !== undefined && current >= previous) {
    console.error(`${files[index]} FAILED — ${current} triangles must be fewer than ${files[index - 1]} (${previous})`);
    process.exitCode = 1;
  }
}
