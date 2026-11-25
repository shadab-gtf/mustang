"""Studio lighting and inspection render presets for the jet-black Mustang."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import bpy

DIRECTORY = Path(__file__).resolve().parent
if str(DIRECTORY) not in sys.path:
    sys.path.insert(0, str(DIRECTORY))

from geometry import box
from materials import pbr
from studio import area, camera


VIEWS = {
    "front": "Jet black | front three-quarter",
    "rear": "Jet black | rear three-quarter",
    "detail": "Jet black | front wheel and fascia",
}
REAR_TARGET = (-0.25, -0.25, 0.55)
REAR_LENS = 57


def floor_finish() -> bpy.types.Material:
    material = pbr("Black studio | graphite floor", (0.044, 0.049, 0.057), 0.57)
    tree = material.node_tree
    shader = tree.nodes.get("Principled BSDF")
    coordinates = tree.nodes.new("ShaderNodeTexCoord")
    grain = tree.nodes.new("ShaderNodeTexNoise")
    grain.inputs["Scale"].default_value = 72
    grain.inputs["Detail"].default_value = 2
    bump = tree.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.16
    bump.inputs["Distance"].default_value = 0.005
    tree.links.new(coordinates.outputs["Object"], grain.inputs["Vector"])
    tree.links.new(grain.outputs["Fac"], bump.inputs["Height"])
    tree.links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    return material


def build_black_studio() -> None:
    """Light a ground-aligned car facing along positive Y, with its center at the origin."""
    scene = bpy.context.scene
    box("Black studio | seamless graphite floor", (0, 0, -0.055), (260, 260, 0.10), floor_finish(), None, radius=0)
    world = bpy.data.worlds.new("Black studio | cool ambient")
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.24, 0.27, 0.32, 1)
    background.inputs["Strength"].default_value = 0.29
    scene.world = world

    area("Black studio | roof strip", (1.06, -0.26, 4.68), (0, 0, 0.42), 400, (0.95, 0.97, 1), 0.77, 6.6)
    area("Black studio | driver belt strip", (-4.28, -0.81, 2.55), (0, -0.24, 0.48), 380, (0.89, 0.95, 1), 5.1, 0.70)
    area("Black studio | nose key", (3.48, 4.27, 4.20), (0, 0.70, 0.45), 505, (0.97, 0.99, 1), 2.6, 1.85)
    area("Black studio | rear rim", (3.50, -4.70, 2.75), (0, -0.83, 0.52), 325, (0.81, 0.90, 1), 4.2, 0.62)
    area("Black studio | fascia fill", (-0.55, 5.80, 2.38), (0, 1.45, 0.47), 185, (1, 0.93, 0.86), 3.2, 1.1)
    area("Black studio | rear fascia fill", (-2.04, -5.34, 2.37), (0, -1.73, 0.50), 210, (1, 0.95, 0.9), 3.0, 1.05)

    scene.camera = camera(VIEWS["front"], (-4.37, 6.11, 2.51), (0.11, 0.17, 0.53), 59)
    camera(VIEWS["rear"], (4.66, -5.91, 2.56), REAR_TARGET, REAR_LENS)
    camera(VIEWS["detail"], (-2.93, 3.72, 1.42), (-0.61, 1.51, 0.59), 67)

    scene.render.engine = "CYCLES"
    scene.cycles.samples = 32
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = 0.0


def configure_cycles_device(scene: bpy.types.Scene, renderer: str) -> None:
    scene.render.engine = "CYCLES"
    if renderer == "cpu":
        scene.cycles.device = "CPU"
        return
    preferences = bpy.context.preferences.addons["cycles"].preferences
    backend = renderer.upper()
    preferences.compute_device_type = backend
    preferences.refresh_devices()
    if not any(device.type == backend for device in preferences.devices):
        raise RuntimeError(f"No {backend} device is configured for Cycles.")
    for device in preferences.devices:
        device.use = device.type == backend
    scene.cycles.device = "GPU"


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("views", nargs="+", choices=VIEWS)
    cli.add_argument("--out", type=Path, default=DIRECTORY.parent / "renders")
    cli.add_argument("--scale", type=int, default=100)
    cli.add_argument("--samples", type=int, default=32)
    cli.add_argument("--device", choices=("cpu", "cuda", "optix"), default="cpu")
    args = cli.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    if not 1 <= args.scale <= 100 or args.samples < 1:
        cli.error("Scale must be between 1 and 100 and samples must be positive.")
    scene = bpy.context.scene
    if any(VIEWS[view] not in bpy.data.objects for view in args.views):
        cli.error("Open assets/mustang-jet-black.blend before running this render script.")
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=True)
    configure_cycles_device(scene, args.device)
    scene.render.resolution_percentage = args.scale
    scene.cycles.samples = args.samples
    for view in args.views:
        scene.frame_set(1)
        scene.camera = bpy.data.objects[VIEWS[view]]
        scene.render.filepath = str(output / f"mustang-jet-black-{view}.png")
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
