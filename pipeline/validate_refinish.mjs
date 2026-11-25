import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { basename } from 'node:path';
import { checkUnitVectors, getItem, near, readAccessors, readGlb, readPrimitives, readScene } from './gltf_checks.mjs';

const vehicle = new URL('../assets/mustang-jet-black.glb', import.meta.url);
const source = 'https://sketchfab.com/3d-models/ford-mustang-john-bowe-1969-wwwvecarzcom-91a5454aaf02492a9c7e959b8eb6db9f';
const license = 'https://creativecommons.org/licenses/by/4.0/';
const corners = ['FL', 'FR', 'RL', 'RR'];
const clips = {
  Driver_Window: { Window_L: 'translation' },
  Passenger_Window: { Window_R: 'translation' },
  Driver_Door: { Door_L: 'rotation' },
  Passenger_Door: { Door_R: 'rotation' },
  Hood: { Hood: 'rotation' },
  Trunk: { Trunk: 'rotation' },
  Steering: { Steer_FL: 'rotation', Steer_FR: 'rotation' },
  Suspension: Object.fromEntries(corners.map((corner) => [`Suspension_${corner}`, 'translation'])),
  Wheel_Rotation: Object.fromEntries(corners.map((corner) => [`Wheel_${corner}`, 'rotation'])),
  Turntable: { Vehicle: 'rotation' },
};

function validateRig(gltf, { nodes }) {
  function requireNode(name, parent, geometry = false) {
    const entry = nodes.get(name);
    assert(entry, `missing pivot ${name}`);
    assert.equal(entry.parent, parent, `${name} parent`);
    if (geometry) {
      assert(entry.node.children?.some((index) => Number.isInteger(gltf.nodes[index].mesh)), `${name} has no directly attached geometry`);
    }
    return entry;
  }

  const root = requireNode('Vehicle', undefined);
  const extras = root.node.extras;
  assert.equal(extras?.sourceModel, source, 'original model attribution');
  assert.equal(extras?.sourceLicense, license, 'source license attribution');
  assert.match(extras?.sourceAuthor ?? '', /vecarz/i, 'source author attribution');
  assert(extras?.modifications?.length > 0, 'modifications are undocumented');
  requireNode('Chassis', 'Vehicle');
  for (const [index, side] of ['L', 'R'].entries()) {
    const door = requireNode(`Door_${side}`, 'Chassis', true);
    requireNode(`Window_${side}`, `Door_${side}`, true);
    near(door.position[0], index === 0 ? -0.811 : 0.811, 0.01, `${side} door hinge lateral position`);
    near(door.position[2], -0.690, 0.01, `${side} door hinge longitudinal position`);
  }
  const hood = requireNode('Hood', 'Chassis', true);
  const trunk = requireNode('Trunk', 'Chassis', true);
  assert(hood.position[2] < -0.8 && trunk.position[2] > 1.7, 'hood and trunk hinges are out of position');
  for (const panel of [hood, trunk]) {
    const materials = new Set(panel.node.children.flatMap((index) => {
      const child = gltf.nodes[index];
      return gltf.meshes[child.mesh]?.primitives.map((primitive) => gltf.materials[primitive.material].name) ?? [];
    }));
    assert(materials.has('Satin black trim and chassis') && materials.has('Polished nickel brightwork'),
      `${panel.node.name} is missing attached original trim and hardware`);
  }

  for (const corner of corners) {
    const suspension = requireNode(`Suspension_${corner}`, 'Vehicle');
    const steer = requireNode(`Steer_${corner}`, `Suspension_${corner}`);
    const wheel = requireNode(`Wheel_${corner}`, `Steer_${corner}`, true);
    const [x, y, z] = wheel.position;
    near(x, corner.endsWith('L') ? -0.74161 : 0.74161, 0.014, `${corner} axle track`);
    near(y, 0.29770, 0.009, `${corner} axle height`);
    near(z, corner.startsWith('F') ? -1.40262 : 1.29214, 0.012, `${corner} axle length`);
    near(wheel.node.extras?.rollingRadiusMeters, y, 0.002, `${corner} rolling radius`);
    wheel.position.forEach((value, axis) => {
      near(steer.position[axis], value, 0.002, `${corner} steering and wheel center`);
      near(suspension.position[axis], value, 0.002, `${corner} suspension and wheel center`);
    });
  }

  const wheelbase = nodes.get('Wheel_RL').position[2] - nodes.get('Wheel_FL').position[2];
  near(wheelbase, 2.69476, 0.02, 'supplied car wheelbase');
  near(extras.wheelbaseMeters, wheelbase, 0.002, 'wheelbase metadata');
  return wheelbase;
}

function validateFinishes(gltf) {
  const materials = new Map(gltf.materials.map((material) => [material.name, material]));
  function texture(info, label) {
    const definition = getItem(gltf.textures, info?.index, label);
    const image = getItem(gltf.images, definition.source, label);
    getItem(gltf.bufferViews, image.bufferView, label);
  }
  for (const material of materials.values()) {
    const alpha = material.pbrMetallicRoughness?.baseColorFactor?.[3] ?? 1;
    assert(alpha >= 0 && alpha <= 1 && ['OPAQUE', 'BLEND', 'MASK'].includes(material.alphaMode ?? 'OPAQUE'),
      `${material.name} has an invalid alpha`);
  }
  const paint = materials.get('Jet black lacquer');
  const pbr = paint?.pbrMetallicRoughness;
  const color = pbr?.baseColorFactor;
  const coat = paint?.extensions?.KHR_materials_clearcoat;
  assert(color?.length === 4 && color.slice(0, 3).every((value) => value >= 0 && value < 0.015) &&
    color[3] === 1 && (paint.alphaMode ?? 'OPAQUE') === 'OPAQUE', 'body paint must be opaque jet black');
  assert(coat?.clearcoatFactor > 0.8 && coat.clearcoatRoughnessFactor < 0.18, 'paint must have a smooth clearcoat');
  texture(paint.normalTexture, 'paint normal texture');
  assert(paint.normalTexture.scale > 0 && paint.normalTexture.scale < 0.15,
    'paint normal strength must preserve smooth clearcoat reflections');
  texture(pbr.metallicRoughnessTexture, 'paint roughness texture');

  const glass = materials.get('Clear automotive glass');
  const transmission = glass?.extensions?.KHR_materials_transmission?.transmissionFactor;
  assert(transmission > 0.8 && glass.pbrMetallicRoughness?.roughnessFactor < 0.2,
    'door and windshield glass must be clear and transmissive');
  const lights = [
    'HeadlightEmission', 'HighBeamEmission', 'TailEmission', 'BrakeEmission', 'ReverseEmission',
    'FrontIndicator_L', 'FrontIndicator_R', 'RearIndicator_L', 'RearIndicator_R',
  ];
  for (const name of lights) {
    assert(materials.get(name)?.emissiveFactor?.some((value) => value > 0), `missing emissive light material ${name}`);
  }
}

function rotationDistance(samples, first, second) {
  let dot = 0;
  for (let axis = 0; axis < 4; axis++) dot += samples[first + axis] * samples[second + axis];
  return 2 * Math.acos(Math.min(1, Math.abs(dot)));
}

function validateMotion(name, node, path, output) {
  const { values, min, max } = output;
  const rotation = path === 'rotation';
  assert(min.some((value, axis) => max[axis] - value > 0.001), `${name} has no visible motion`);
  if (rotation) {
    checkUnitVectors(output, 4, name);
    assert(rotationDistance(values, 0, values.length - 4) < 0.03, `${name} does not return to its initial orientation`);
    if (name === 'Turntable' || name === 'Wheel_Rotation') {
      let distance = 0;
      for (let index = 4; index < values.length; index += 4) distance += rotationDistance(values, index - 4, index);
      const target = name === 'Turntable' ? 2 * Math.PI : 4 * Math.PI;
      assert(Math.abs(distance - target) < 0.16, `${name} rotates ${distance.toFixed(3)} rad, expected ${target.toFixed(3)} rad`);
    }
  } else {
    for (let axis = 0; axis < 3; axis++) {
      const base = node.translation?.[axis] ?? 0;
      near(values[axis], base, 0.0015, `${name} starting position`);
      near(values[values.length - 3 + axis], base, 0.0015, `${name} ending position`);
    }
    if (name.endsWith('_Window')) {
      near(values[1] - min[1], node.extras?.travelMeters ?? 0.365, 0.005, `${name} vertical travel`);
      near(max[0] - min[0], node.extras?.outwardMeters ?? 0.030, 0.004, `${name} guide travel`);
    }
  }
}

function validateClips(gltf, accessors, scene) {
  const animations = new Map();
  for (const animation of gltf.animations ?? []) {
    assert(animation.name && !animations.has(animation.name), `duplicate or empty animation ${animation.name}`);
    animations.set(animation.name, animation);
  }
  for (const [name, expected] of Object.entries(clips)) {
    const animation = animations.get(name);
    assert(animation, `missing animation ${name}`);
    const channels = new Set();
    for (const channel of animation.channels) {
      const node = getItem(gltf.nodes, channel.target.node, name);
      const path = channel.target.path;
      assert(scene.nodes.has(node.name) && !node.matrix && !channels.has(node.name), `${name} has an invalid or duplicate target`);
      channels.add(node.name);
      const extraSteeringWheel = name === 'Steering' && node.name === 'SteeringWheel' && path === 'rotation';
      assert(expected[node.name] === path || extraSteeringWheel, `${name} unexpectedly targets ${node.name}.${path}`);

      const sampler = getItem(animation.samplers, channel.sampler, name);
      const input = getItem(accessors, sampler.input, name);
      const output = getItem(accessors, sampler.output, name);
      assert(input.type === 'SCALAR' && input.componentType === 5126 && input.count > 1 &&
        input.values.every((time, index) => index === 0 ? time >= 0 : time > input.values[index - 1]), `${name} has invalid sample times`);
      assert((sampler.interpolation ?? 'LINEAR') === 'LINEAR' && output.componentType === 5126 &&
        output.type === (path === 'rotation' ? 'VEC4' : 'VEC3') && output.count === input.count, `${name} has invalid sample values`);
      validateMotion(name, node, path, output);
    }
    for (const target of Object.keys(expected)) assert(channels.has(target), `${name} does not include ${target}`);
  }
  return animations.size;
}

const path = process.argv[2] ?? vehicle;
const name = basename(typeof path === 'string' ? path : path.pathname);
try {
  const asset = await readFile(path);
  const { gltf, binary } = readGlb(asset);
  const accessors = readAccessors(gltf, binary);
  const scene = readScene(gltf, readPrimitives(gltf, accessors, false));
  const [width, height, length] = scene.max.map((value, axis) => value - scene.min[axis]);
  near(length, 4.6747, 0.075, 'supplied car length');
  near(width, 1.8415, 0.075, 'supplied car width');
  near(height, 1.2482, 0.075, 'supplied car height');
  near(scene.min[1], 0, 0.019, 'tire contact plane');
  const wheelbase = validateRig(gltf, scene);
  validateFinishes(gltf);
  const animations = validateClips(gltf, accessors, scene);
  assert(scene.degenerate / scene.triangles < 0.002, 'geometry has too many degenerate triangles');
  console.log(`${name} · ${[length, width, height].map((value) => value.toFixed(3)).join(' × ')} m · wheelbase ${wheelbase.toFixed(3)} m`);
  console.log(`${scene.triangles.toLocaleString('en-US')} triangles · ${scene.primitives} primitives · ${animations} clips · ${scene.degenerate} degenerate · ${(asset.length / 1_048_576).toFixed(2)} MiB`);
} catch (error) {
  console.error(`${name} FAILED — ${error.message}`);
  process.exitCode = 1;
}
