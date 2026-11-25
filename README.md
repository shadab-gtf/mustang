# 1969 Mustang in jet black

The editable Blender project and animated GLB use the supplied **Ford Mustang John Bowe 1969** by vecarz. The refinish adds deep black lacquer with a glossy clearcoat, restored transparency in the cabin and lamp glass, distinct nickel, machined alloy and rubber finishes, tire valve hardware, and a single rear-left exhaust with a short rolled steel outlet. [Original model](https://sketchfab.com/3d-models/ford-mustang-john-bowe-1969-wwwvecarzcom-91a5454aaf02492a9c7e959b8eb6db9f) · [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)

| File | Use |
| --- | --- |
| [mustang-jet-black.blend](assets/mustang-jet-black.blend) | Editable geometry, packed material maps, studio, cameras and animation timeline. |
| [mustang-jet-black.glb](assets/mustang-jet-black.glb) | Full-detail glTF 2.0 asset with ten playback clips. |
| [Compressed Mustang GLB](preview/public/models/mustang.glb) | 4.99 MB preview model with Meshopt compression and all ten clips. |
| [Studio renders](renders) | Exterior and detail renders from the Blender scene. |
| [Studio orbit](renders/mustang-jet-black-turntable.mp4) | Camera sweep across the finish, side profile and rear brightwork. |
| [Browser preview](preview) | Orbit, operate the moving panels, switch lighting and drive on the test pad. |
| [1967 reference board](docs/references.md) | Photo references and model listings collected for the initial film-car brief. |

## Animation

The clips are `Driver_Door`, `Passenger_Door`, `Driver_Window`, `Passenger_Window`, `Hood`, `Trunk`, `Steering`, `Suspension`, `Wheel_Rotation` and `Turntable`. The two door skins carry their source glass and separated trim. Each tire and rim turns on its own axle. The front wheels steer and all four suspension nodes travel vertically. The exported rig uses meters, +Y up, and −Z forward. Wheelbase measures 2.695 m.

The trunk lid carries the original MUSTANG lettering, inner ribs, and hinges. Both front doors swing 62 degrees on front hinges and carry their fitted trim, window mechanisms, and indicator mirrors. Steering moves the front wheels and the cabin steering wheel. The driving test pad uses a simplified vehicle dynamics model.

## Local preview

Use Node.js 22.18 or newer.

```sh
cd preview
npm ci
npm run prepare:model
npm run dev
```

Use the showroom controls to operate the panels and lights. In Drive, use **W/S** to accelerate and brake, **A/D** to steer and **Space** for the handbrake. **Fullscreen** expands the driving view with the speed display and touch controls. The selector also offers manual gears, neutral, and reverse.

Drive opens on the circuit traced from the reference map. The minimap highlights the route ahead and shows the next turn when it is within range. Rough runoff reduces grip. Barrier impacts can bend panels, reduce engine power, and overturn the car in a severe side impact. **Restart race** restores the car and returns it to the start. Choose **Speed test pad** for an open straight where the automatic transmission reaches 300 km/h with the default tuning.

**Cabin**, **Engine**, and **Trunk view** open the corresponding panel for inspection. The exterior camera orbits from above the car.

The preview softens the dampers and increases suspension travel under rear slip. Forward acceleration transfers load to the rear axle and extends the front suspension. **Drag launch setup** simulates a higher-torque build on a prepared surface. A straight first-gear launch can lift the front tires when the acceleration moment exceeds the gravitational moment about the rear contact patch. In Inspect, **Rev engine** demonstrates smoke and brief high-RPM flashes at the exhaust outlet. The stripe palette applies red, orange, violet, light gray, white, cream, or pista green to either layout. The three-strip layout also supports a mixed red and orange set.

## Rebuild

Use Blender 4.5 LTS and the original supplied GLB. On Windows, pass the full path to Blender if it is outside your PATH.

The preview preparation command uses FFmpeg on PATH to downsample the procedural finish maps before Meshopt compression. The shipped preview GLB is ready to load.

```sh
blender --background --factory-startup --python-exit-code 1 --python pipeline/refinish.py -- --source "D:/Downloads/ford_mustang_john_bowe_1969__www.vecarz.com.glb"
node pipeline/validate_refinish.mjs
blender --background assets/mustang-jet-black.blend --python pipeline/black_studio.py -- front rear detail
blender --background assets/mustang-jet-black.blend --python pipeline/black_turntable.py -- --fps 10 --encoded-fps 20 --seconds 5.5 --width 1088 --height 680 --samples 8
cd preview
npm run prepare:model
npm test
npm run build
```
