import {
  CatmullRomCurve3, CylinderGeometry, Group, Mesh, MeshStandardMaterial, TubeGeometry, Vector3,
  type Object3D,
} from "three"

const UP = new Vector3(0, 1, 0)
const points = Array.from({ length: 89 }, (_, index) => {
  const t = index / 88
  return new Vector3(Math.cos(t * Math.PI * 14) * .064, .044 + t * .265, Math.sin(t * Math.PI * 14) * .064)
})
const spring = new TubeGeometry(new CatmullRomCurve3(points), 88, .007, 6, false)
const rod = new CylinderGeometry(.015, .015, 1, 10)
rod.translate(0, .5, 0)
const sleeve = new CylinderGeometry(.03, .03, .176, 10)
sleeve.translate(0, .104, 0)
const steel = new MeshStandardMaterial({ color: 0xc5c9d0, metalness: .82, roughness: .27 })
const black = new MeshStandardMaterial({ color: 0x212327, metalness: .55, roughness: .36 })
const springPaint = new MeshStandardMaterial({ color: 0x9e2219, metalness: .24, roughness: .38 })

export class Shock {
  private readonly group = new Group()
  private readonly mount: Vector3
  private readonly wheel: Object3D
  private readonly coil = new Mesh(spring, springPaint)
  private readonly piston = new Mesh(rod, steel)
  private readonly top = new Vector3()
  private readonly direction = new Vector3()

  constructor(parent: Group, wheel: Object3D) {
    this.wheel = wheel
    const { x, z } = wheel.position
    this.mount = new Vector3(x * .70, .67, z)
    this.group.add(this.coil, this.piston, new Mesh(sleeve, black))
    parent.add(this.group)
  }

  update(chassis: Object3D) {
    const { x, y, z } = this.wheel.position
    this.group.position.set(x * .80, y + .018, z)
    this.top.copy(this.mount).applyQuaternion(chassis.quaternion).add(chassis.position)
    this.direction.subVectors(this.top, this.group.position)
    const length = this.direction.length()
    this.group.quaternion.setFromUnitVectors(UP, this.direction.divideScalar(length))
    this.coil.scale.y = length / .34
    this.piston.scale.y = length
  }
}
