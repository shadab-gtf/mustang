import assert from 'node:assert/strict';

const componentTypes = new Map([
  [5120, [1, 'readInt8']], [5121, [1, 'readUInt8']],
  [5122, [2, 'readInt16LE']], [5123, [2, 'readUInt16LE']],
  [5125, [4, 'readUInt32LE']], [5126, [4, 'readFloatLE']],
]);
const elementWidths = { SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4 };
const identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];

function getItem(items, index, label) {
  assert(Number.isInteger(index) && items?.[index] !== undefined, `${label} refers to missing item ${index}`);
  return items[index];
}

function readGlb(file) {
  assert(file.length >= 28, 'GLB is shorter than its headers');
  assert.equal(file.toString('ascii', 0, 4), 'glTF', 'GLB magic');
  assert.equal(file.readUInt32LE(4), 2, 'GLB version');
  assert.equal(file.readUInt32LE(8), file.length, 'GLB total length');
  const jsonLength = file.readUInt32LE(12);
  const binHeader = 20 + jsonLength;
  assert(jsonLength % 4 === 0 && binHeader + 8 <= file.length, 'JSON chunk length or alignment');
  assert.equal(file.toString('ascii', 16, 20), 'JSON', 'first chunk type');
  const gltf = JSON.parse(file.toString('utf8', 20, binHeader));
  const binLength = file.readUInt32LE(binHeader);
  assert(binLength % 4 === 0 && binHeader + 8 + binLength === file.length, 'BIN chunk length or alignment');
  assert.equal(file.readUInt32LE(binHeader + 4), 0x004e4942, 'second chunk type');
  assert.equal(gltf.asset?.version, '2.0', 'glTF asset version');
  assert.equal(gltf.buffers?.length, 1, 'GLB requires one embedded buffer');
  const [buffer] = gltf.buffers;
  assert(!buffer.uri && buffer.byteLength <= binLength && binLength - buffer.byteLength <= 3, 'BIN buffer bounds');
  return { gltf, binary: file.subarray(binHeader + 8, binHeader + 8 + buffer.byteLength) };
}

function readAccessors(gltf, binary) {
  for (const [index, view] of gltf.bufferViews.entries()) {
    const offset = view.byteOffset ?? 0;
    assert(view.buffer === 0 && Number.isInteger(offset) && offset >= 0 &&
      Number.isInteger(view.byteLength) && view.byteLength > 0 && offset + view.byteLength <= binary.length,
    `bufferView ${index} is outside the binary buffer`);
  }
  return gltf.accessors.map((accessor, index) => {
    const label = `accessor ${index}`;
    assert(!accessor.sparse, `${label} is sparse, which this export does not use`);
    const view = getItem(gltf.bufferViews, accessor.bufferView, label);
    const component = componentTypes.get(accessor.componentType);
    const width = elementWidths[accessor.type];
    assert(component && width && Number.isInteger(accessor.count) && accessor.count > 0, `${label} has an invalid format`);
    const [bytes, read] = component;
    const offset = accessor.byteOffset ?? 0;
    const stride = view.byteStride ?? (bytes * width);
    const start = (view.byteOffset ?? 0) + offset;
    assert(Number.isInteger(offset) && offset >= 0 && offset % bytes === 0 && start % bytes === 0 &&
      Number.isInteger(stride) && stride >= bytes * width && stride % bytes === 0 &&
      offset + (accessor.count - 1) * stride + bytes * width <= view.byteLength, `${label} exceeds its bufferView`);
    const values = new Float64Array(accessor.count * width);
    const min = Array(width).fill(Infinity);
    const max = Array(width).fill(-Infinity);
    for (let index = 0; index < accessor.count; index++) {
      for (let axis = 0; axis < width; axis++) {
        const value = binary[read](start + index * stride + axis * bytes);
        assert(Number.isFinite(value), `${label} has a non-finite value at element ${index}`);
        values[index * width + axis] = value;
        min[axis] = Math.min(min[axis], value);
        max[axis] = Math.max(max[axis], value);
      }
    }
    for (const [key, values] of [['min', min], ['max', max]]) {
      if (accessor[key] === undefined) continue;
      assert(accessor[key].length === width && values.every((value, axis) =>
        Math.abs(value - accessor[key][axis]) <= Math.max(1e-6, Math.abs(value) * 1e-7)), `${label} ${key} disagrees with binary values`);
    }
    return { ...accessor, values, min, max };
  });
}

function checkUnitVectors(accessor, width, label) {
  const { values } = accessor;
  for (let index = 0; index < values.length; index += width) {
    let lengthSquared = 0;
    for (let axis = 0; axis < width; axis++) lengthSquared += values[index + axis] ** 2;
    assert(Math.abs(lengthSquared - 1) < 0.015, `${label} has a non-unit vector at element ${index / width}`);
  }
}

function readPrimitives(gltf, accessors, collision) {
  const checkedNormals = new Set();
  return gltf.meshes.map((mesh, meshIndex) => mesh.primitives.map((primitive, index) => {
    const label = `${mesh.name ?? `mesh ${meshIndex}`} primitive ${index}`;
    const attributes = primitive.attributes;
    const position = getItem(accessors, attributes.POSITION, label);
    assert(position.type === 'VEC3' && position.componentType === 5126, `${label} has an invalid POSITION`);
    assert(gltf.accessors[attributes.POSITION].min && gltf.accessors[attributes.POSITION].max, `${label} lacks POSITION bounds`);
    if (!collision) {
      const normal = getItem(accessors, attributes.NORMAL, `${label} NORMAL`);
      const uv = getItem(accessors, attributes.TEXCOORD_0, `${label} TEXCOORD_0`);
      assert(normal.type === 'VEC3' && normal.componentType === 5126, `${label} has an invalid NORMAL`);
      assert(uv.type === 'VEC2' && uv.componentType === 5126, `${label} has an invalid TEXCOORD_0`);
      getItem(gltf.materials, primitive.material, `${label} material`);
      if (!checkedNormals.has(attributes.NORMAL)) {
        checkUnitVectors(normal, 3, `${label} NORMAL`);
        checkedNormals.add(attributes.NORMAL);
      }
    }
    for (const attribute of Object.values(attributes)) {
      assert.equal(getItem(accessors, attribute, `${label} attribute`).count, position.count, `${label} attribute count`);
    }
    assert.equal(primitive.mode ?? 4, 4, `${label} must use TRIANGLES`);
    const indices = primitive.indices === undefined ? null : getItem(accessors, primitive.indices, label);
    if (indices) {
      assert(indices.type === 'SCALAR' && [5121, 5123, 5125].includes(indices.componentType) && !indices.normalized,
        `${label} index format`);
      const maximum = { 5121: 255, 5123: 65_535, 5125: 4_294_967_295 }[indices.componentType];
      assert(indices.max[0] < Math.min(position.count, maximum), `${label} has an index outside its positions`);
    }
    const vertices = indices?.count ?? position.count;
    assert(vertices % 3 === 0, `${label} triangle count is fractional`);
    return { positions: position.values, indices: indices?.values, triangles: vertices / 3 };
  }));
}

function localMatrix(node) {
  if (node.matrix) {
    assert(node.matrix.length === 16 && node.matrix.every(Number.isFinite) &&
      !node.translation && !node.rotation && !node.scale, `${node.name} has an invalid transform matrix`);
    return node.matrix;
  }
  const position = node.translation ?? [0, 0, 0];
  const rotation = node.rotation ?? [0, 0, 0, 1];
  const scale = node.scale ?? [1, 1, 1];
  assert(position.length === 3 && rotation.length === 4 && scale.length === 3 &&
    [...position, ...rotation, ...scale].every(Number.isFinite) && scale.every((value) => value !== 0) &&
    Math.abs(Math.hypot(...rotation) - 1) < 1e-4, `${node.name} has an invalid transform`);
  const [x, y, z, w] = rotation;
  const [sx, sy, sz] = scale;
  return [
    (1 - 2 * (y * y + z * z)) * sx, 2 * (x * y + z * w) * sx, 2 * (x * z - y * w) * sx, 0,
    2 * (x * y - z * w) * sy, (1 - 2 * (x * x + z * z)) * sy, 2 * (y * z + x * w) * sy, 0,
    2 * (x * z + y * w) * sz, 2 * (y * z - x * w) * sz, (1 - 2 * (x * x + y * y)) * sz, 0,
    ...position, 1,
  ];
}

function multiply(parent, local) {
  return local.map((_, index) => {
    const row = index % 4;
    const column = index - row;
    return parent[row] * local[column] + parent[row + 4] * local[column + 1] +
      parent[row + 8] * local[column + 2] + parent[row + 12] * local[column + 3];
  });
}

function readScene(gltf, meshes) {
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  const nodes = new Map();
  const visited = new Set();
  const stats = { primitives: 0, triangles: 0, degenerate: 0 };

  function visit(index, parent, world) {
    const node = getItem(gltf.nodes, index, 'scene node');
    assert(!visited.has(index), `node ${node.name} has multiple parents or a cycle`);
    visited.add(index);
    const matrix = multiply(world, localMatrix(node));
    if (node.name) {
      assert(!nodes.has(node.name), `duplicate node name ${node.name}`);
      nodes.set(node.name, { index, parent, position: matrix.slice(12, 15), node });
    }
    for (const primitive of node.mesh === undefined ? [] : getItem(meshes, node.mesh, node.name)) {
      inspectMesh(primitive, matrix, min, max, stats);
    }
    for (const child of node.children ?? []) visit(child, node.name, matrix);
  }

  const scene = getItem(gltf.scenes, gltf.scene ?? 0, 'default scene');
  for (const index of scene.nodes ?? []) visit(index, undefined, identity);
  assert(stats.triangles > 0 && min.every(Number.isFinite) && max.every(Number.isFinite), 'scene has no bounded geometry');
  return { ...stats, min, max, nodes };
}

function inspectMesh(primitive, matrix, min, max, stats) {
  const { positions, indices, triangles } = primitive;
  stats.primitives++;
  stats.triangles += triangles;
  for (let vertex = 0; vertex < positions.length; vertex += 3) {
    const x = positions[vertex];
    const y = positions[vertex + 1];
    const z = positions[vertex + 2];
    for (let axis = 0; axis < 3; axis++) {
      const value = matrix[axis] * x + matrix[axis + 4] * y + matrix[axis + 8] * z + matrix[axis + 12];
      min[axis] = Math.min(min[axis], value);
      max[axis] = Math.max(max[axis], value);
    }
  }
  for (let triangle = 0; triangle < triangles; triangle++) {
    const offset = triangle * 3;
    const a = (indices?.[offset] ?? offset) * 3;
    const b = (indices?.[offset + 1] ?? (offset + 1)) * 3;
    const c = (indices?.[offset + 2] ?? (offset + 2)) * 3;
    const abX = positions[b] - positions[a];
    const abY = positions[b + 1] - positions[a + 1];
    const abZ = positions[b + 2] - positions[a + 2];
    const acX = positions[c] - positions[a];
    const acY = positions[c + 1] - positions[a + 1];
    const acZ = positions[c + 2] - positions[a + 2];
    const areaSquared = (abY * acZ - abZ * acY) ** 2 + (abZ * acX - abX * acZ) ** 2 + (abX * acY - abY * acX) ** 2;
    if (areaSquared <= 1e-22) stats.degenerate++;
  }
}

function near(actual, expected, tolerance, label) {
  assert(Math.abs(actual - expected) <= tolerance, `${label} is ${actual.toFixed(5)} m, expected ${expected} ± ${tolerance} m`);
}

export { checkUnitVectors, getItem, near, readAccessors, readGlb, readPrimitives, readScene };
