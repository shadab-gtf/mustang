"""Render a turntable and mechanical reveal from the Mustang Blender scene."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from math import floor
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

import bpy
from mathutils import Matrix, Vector


Point = tuple[float, float, float]


@dataclass(frozen=True)
class CameraPose:
    origin: Point
    target: Point
    lens: float


@dataclass(frozen=True)
class Motion:
    node: str
    strip: str
    start: float
    stop: float


@dataclass(frozen=True)
class Shot:
    duration: float
    start: CameraPose
    end: CameraPose
    motions: tuple[Motion, ...] = ()


SHOTS = (
    Shot(
        2.5,
        CameraPose((-4.05, 6.61, 2.31), (0, 0.10, 0.67), 55),
        CameraPose((-5.95, 4.85, 2.15), (0, 0.03, 0.67), 55),
    ),
    Shot(
        2.4,
        CameraPose((-3.22, 0.03, 1.58), (-0.25, -0.02, 0.75), 44),
        CameraPose((-3.58, -1.15, 1.77), (-0.28, 0.06, 0.75), 46),
        (Motion("Window_L", "Windows", 0.06, 0.44), Motion("Door_L", "Doors", 0.31, 0.88)),
    ),
    Shot(
        2.6,
        CameraPose((-3.16, 4.57, 2.05), (0, 1.13, 0.67), 50),
        CameraPose((-2.32, 3.44, 2.96), (0, 1.22, 0.70), 52),
        (Motion("Hood", "Hood", 0.10, 0.70),),
    ),
)


def sample_motion(scene: bpy.types.Scene, motion: Motion, progress: float) -> Matrix:
    node = bpy.data.objects[motion.node]
    track = node.animation_data.nla_tracks[motion.strip]
    strip = track.strips[0]
    normalized = min(1.0, max(0.0, (progress - motion.start) / (motion.stop - motion.start)))
    # The first 24 source frames go from closed to the held inspection pose.
    source_frame = strip.frame_start + 24 * normalized
    integral = floor(source_frame)
    scene.frame_set(integral, subframe=source_frame - integral)
    return node.matrix_basis.copy()


def camera_pose(shot: Shot, progress: float) -> CameraPose:
    eased = progress * progress * (3 - 2 * progress)
    return CameraPose(
        tuple(Vector(shot.start.origin).lerp(Vector(shot.end.origin), eased)),
        tuple(Vector(shot.start.target).lerp(Vector(shot.end.target), eased)),
        shot.start.lens + eased * (shot.end.lens - shot.start.lens),
    )


def stage_camera(scene: bpy.types.Scene) -> bpy.types.Object:
    camera = bpy.data.objects.new("Motion camera", bpy.data.cameras.new("Motion camera"))
    scene.collection.objects.link(camera)
    scene.camera = camera
    light = bpy.data.lights.new("Motion cabin softbox", "AREA")
    light.color = (0.88, 0.93, 1.0)
    light.energy = 270
    light.shape = "RECTANGLE"
    light.size = 2.4
    light.size_y = 1.65
    fill = bpy.data.objects.new(light.name, light)
    scene.collection.objects.link(fill)
    fill.location = (-2.7, -0.94, 2.08)
    fill.rotation_euler = (Vector((-0.22, -0.08, 0.64)) - fill.location).to_track_quat("-Z", "Y").to_euler()
    return camera


def settings(scene: bpy.types.Scene, args: argparse.Namespace) -> None:
    scene.render.engine = "BLENDER_EEVEE_NEXT" if args.engine == "eevee" else "CYCLES"
    if args.engine == "eevee":
        scene.eevee.taa_render_samples = args.samples
        scene.eevee.shadow_ray_count = 2
        scene.eevee.use_raytracing = True
    else:
        scene.cycles.samples = args.samples
        scene.cycles.use_denoising = True
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.compression = 12


def render_frames(scene: bpy.types.Scene, directory: Path, fps: int, probe: bool) -> None:
    actor_names = {motion.node for shot in SHOTS for motion in shot.motions}
    scene.frame_set(1)
    neutral = {name: bpy.data.objects[name].matrix_basis.copy() for name in actor_names}
    staged = []
    for shot in SHOTS:
        frame_count = round(shot.duration * fps)
        samples = (0, frame_count - 1) if probe else range(frame_count)
        for index in samples:
            progress = index / (frame_count - 1)
            poses = {motion.node: sample_motion(scene, motion, progress) for motion in shot.motions}
            staged.append((camera_pose(shot, progress), poses))

    scene.frame_set(1)
    for name in actor_names:
        bpy.data.objects[name].animation_data_clear()
    camera = stage_camera(scene)
    for frame, (pose, actors) in enumerate(staged):
        for name, matrix in (neutral | actors).items():
            bpy.data.objects[name].matrix_basis = matrix
        camera.location = pose.origin
        camera.rotation_euler = (Vector(pose.target) - camera.location).to_track_quat("-Z", "Y").to_euler()
        camera.data.lens = pose.lens
        scene.render.filepath = str(directory / f"frame-{frame:04d}.png")
        bpy.ops.render.render(write_still=True)
        print(f"Mustang motion frame {frame + 1}/{len(staged)}", flush=True)


def encode(ffmpeg: str, frames: Path, output: Path, fps: int) -> None:
    intermediate = output.with_name(f".{output.stem}.partial.mp4")
    try:
        subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-framerate", str(fps),
             "-i", str(frames / "frame-%04d.png"), "-c:v", "libx264", "-preset", "medium", "-crf", "18",
             "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(intermediate)],
            check=True,
        )
        intermediate.replace(output)
    finally:
        intermediate.unlink(missing_ok=True)


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "renders" / "mustang-motion.mp4")
    cli.add_argument("--engine", choices=("eevee", "cycles"), default="eevee")
    cli.add_argument("--fps", type=int, default=24)
    cli.add_argument("--samples", type=int, default=16)
    cli.add_argument("--width", type=int, default=1280)
    cli.add_argument("--height", type=int, default=720)
    cli.add_argument("--probe", type=Path, help="Write the first and last frame of each shot to this directory.")
    args = cli.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    if args.fps < 2 or args.samples < 1 or min(args.width, args.height) < 2 or args.width % 2 or args.height % 2:
        cli.error("Use at least two frames per second, positive samples, and even video dimensions.")

    scene = bpy.context.scene
    settings(scene, args)
    if args.probe:
        output = args.probe.resolve()
        output.mkdir(parents=True, exist_ok=True)
        render_frames(scene, output, args.fps, probe=True)
        return

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        cli.error("FFmpeg must be available on PATH.")
    output = args.out.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="mustang-motion-") as directory:
        frames = Path(directory)
        render_frames(scene, frames, args.fps, probe=False)
        encode(ffmpeg, frames, output, args.fps)
    print(f"Mustang motion preview: {output}", flush=True)


if __name__ == "__main__":
    main()
