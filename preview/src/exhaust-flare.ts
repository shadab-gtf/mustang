import {
  AdditiveBlending, BufferAttribute, BufferGeometry, Color, DynamicDrawUsage, Group, Mesh,
  Points, ShaderMaterial, SphereGeometry, Vector3,
} from "three"

const CAPACITY = 48
const UP = new Vector3(0, 1, 0)
const FLASH_DURATION = .17

function flameMaterial(tint: number) {
  return new ShaderMaterial({
    uniforms: { tint: { value: new Color(tint) }, intensity: { value: 0 } },
    transparent: true, depthWrite: false, blending: AdditiveBlending,
    vertexShader: `
      varying vec3 surfaceNormal;
      varying vec3 eye;
      varying float reach;
      void main() {
        vec4 view = modelViewMatrix * vec4(position, 1.0);
        surfaceNormal = normalize(normalMatrix * normal);
        eye = -view.xyz;
        reach = position.y;
        gl_Position = projectionMatrix * view;
      }
    `,
    fragmentShader: `
      uniform vec3 tint;
      uniform float intensity;
      varying vec3 surfaceNormal;
      varying vec3 eye;
      varying float reach;
      void main() {
        float edge = max(0.0, dot(normalize(surfaceNormal), normalize(eye)));
        float tail = 1.0 - smoothstep(.0, 1.0, reach);
        gl_FragColor = vec4(tint, intensity * pow(edge, 1.55) * tail);
        #include <colorspace_fragment>
      }
    `,
  })
}

interface Ember {
  position: Vector3
  velocity: Vector3
  age: number
  life: number
  radius: number
}

export class ExhaustFlare {
  readonly group = new Group()
  private readonly positions = new BufferAttribute(new Float32Array(CAPACITY * 3), 3).setUsage(DynamicDrawUsage)
  private readonly life = new BufferAttribute(new Float32Array(CAPACITY * 2), 2).setUsage(DynamicDrawUsage)
  private readonly embers: Ember[] = Array.from({ length: CAPACITY }, () => ({
    position: new Vector3(), velocity: new Vector3(), age: 1, life: 1, radius: 0,
  }))
  private readonly flash = new Group()
  private readonly glow = flameMaterial(0xff670c)
  private readonly core = flameMaterial(0xffd392)
  private flashTime = 0
  private next = 0

  constructor() {
    const geometry = new BufferGeometry()
    geometry.setAttribute("position", this.positions)
    geometry.setAttribute("emberLife", this.life)
    const points = new Points(geometry, new ShaderMaterial({
      transparent: true, depthWrite: false, blending: AdditiveBlending,
      vertexShader: `
        attribute vec2 emberLife;
        varying float heat;
        void main() {
          heat = emberLife.x;
          vec4 view = modelViewMatrix * vec4(position, 1.0);
          gl_Position = projectionMatrix * view;
          gl_PointSize = max(1.0, emberLife.y / max(1.0, -view.z));
        }
      `,
      fragmentShader: `
        varying float heat;
        void main() {
          vec2 uv = gl_PointCoord * 2.0 - 1.0;
          float radius = length(uv);
          float halo = 1.0 - smoothstep(.15, 1.0, radius);
          vec3 tint = mix(vec3(1.0, .055, .003), vec3(1.0, .33, .027), heat);
          float core = 1.0 - smoothstep(.06, .48, radius);
          tint = mix(tint, vec3(1.0, .77, .38), core * heat);
          gl_FragColor = vec4(tint, heat * halo * halo);
          #include <colorspace_fragment>
        }
      `,
    }))
    points.frustumCulled = false
    points.renderOrder = 4
    const sphere = new SphereGeometry(1, 18, 10)
    const envelope = new Mesh(sphere, this.glow)
    envelope.scale.set(.043, .16, .043)
    envelope.position.y = .153
    const hotCenter = new Mesh(sphere, this.core)
    hotCenter.scale.set(.025, .086, .025)
    hotCenter.position.y = .08
    envelope.renderOrder = hotCenter.renderOrder = 3
    this.flash.add(envelope, hotCenter)
    this.flash.visible = false
    this.group.add(this.flash, points)
  }

  burst(outlet: Vector3, direction: Vector3, random: () => number) {
    this.flash.position.copy(outlet)
    this.flash.quaternion.setFromUnitVectors(UP, direction)
    this.flashTime = FLASH_DURATION
    for (let index = 0; index < 12; index++) {
      const ember = this.embers[this.next]
      this.next = (this.next + 1) % CAPACITY
      const core = index < 4
      ember.position.copy(outlet).addScaledVector(direction, .018 + random() * .062)
      ember.velocity.copy(direction).multiplyScalar(1.5 + random() * 4.2)
      ember.velocity.x += (random() - .5) * .95
      ember.velocity.y += (random() - .35) * .64
      ember.velocity.z += (random() - .5) * .56
      ember.age = 0
      ember.life = core ? .13 + random() * .08 : .16 + random() * .14
      ember.radius = core ? 77 + random() * 55 : 9 + random() * 16
    }
  }

  reset() {
    for (const ember of this.embers) ember.age = ember.life
    this.flashTime = 0
  }

  update(delta: number) {
    this.flashTime = Math.max(0, this.flashTime - delta)
    const intensity = this.flashTime / FLASH_DURATION
    this.flash.visible = intensity > 0
    this.flash.scale.setScalar(.72 + intensity * .52)
    this.glow.uniforms.intensity.value = intensity * .78
    this.core.uniforms.intensity.value = intensity * .91
    for (const [index, ember] of this.embers.entries()) {
      ember.age = Math.min(ember.life, ember.age + delta)
      const heat = 1 - ember.age / ember.life
      if (heat > 0) {
        ember.velocity.y -= delta * 2.2
        ember.position.addScaledVector(ember.velocity, delta)
        this.positions.setXYZ(index, ember.position.x, ember.position.y, ember.position.z)
      }
      this.life.setXY(index, heat, ember.radius * (.46 + heat * .60))
    }
    this.positions.needsUpdate = this.life.needsUpdate = true
  }
}
